"""The LangGraph variant of the orchestrator (``docs/COMPARISON_LANGGRAPH.md``).

The same run, expressed as a LangGraph ``StateGraph`` whose nodes call the same phase objects, the
same gateways, the same checkpoint and manifest writers and the same progress sink as
:class:`sit_review_agent.orchestrator.Orchestrator`. Selected by ``sit-review run --orchestrator
langgraph``; absent the flag the product is the custom loop, unchanged.

Graph (``dra`` prints the custom loop's stage table; ``<run>/langgraph/graph.mmd`` holds this one)::

    START -> ingest -> stage1_open -> [fan-out: Send(stage1_chain), Send(assess_shard, k) ...]
                                          stage1_chain = subgraph: START -> understand, plan
                                                                   [understand, plan] -> gate -> research
                                      -> merge -> (refine | verify) -> verify -> report -> END

* Stage 1 is one LangGraph superstep: the fan-out sends the ``stage1_chain`` subgraph and one
  ``assess_shard`` node per shard of ``AssessSettings.shards_for``; they run concurrently and
  ``merge`` runs when the superstep ends. Research's dependency on understand and plan is a join edge
  inside the subgraph (``STAGE_1_DEPENDS``), which is why the chain is a subgraph: a join edge at the
  top level would wait for the assess shards too (Pregel steps are barriers).
* The run state stays on the :class:`RunContext` (the gateways, ledger and registry are not
  serialisable through the framework's channels); the graph state is the control state only: which
  stage 1 members ended and how, which shards produced a result, and why the run stops early.
  Members run on isolated copies and are merged back by the same ``phases._isolation`` code.
* The bookkeeping the custom loop does around a phase (checkpoint with ordinal, ``elapsed_s``,
  milestones, the stage 1 close with the merge in shard order, the cap skips with their disclosures,
  the cut and skipped fallbacks) is the custom loop's own code, reused by subclassing
  :class:`Orchestrator`; only the scheduling is the framework's. That keeps the comparison about
  the loop, not about two copies of the bookkeeping.
* What the framework has no primitive for is written here by hand and listed in the comparison
  note: a per-node time limit on the run clock (``_member``), stopping the sibling nodes when one
  fails (``_cancel_others``), a cap decision that must disclose itself inside an edge function
  (``_route_refine``), and a process fault around the whole assess member (not reproduced: the
  shards are separate nodes).
"""

from __future__ import annotations

import asyncio
import operator
from collections.abc import Mapping
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from sit_review_agent.context import RunContext
from sit_review_agent.errors import AgentError, AssessShardsFailed, RunInterrupted, StageCrash
from sit_review_agent.orchestrator import STAGE_1, Orchestrator, _cut_shard, _deadline_active
from sit_review_agent.orchestrator_langgraph.saver import LANGGRAPH_DIR, RunDirSaver
from sit_review_agent.phases.base import Phase
from sit_review_agent.progress import bind_run_clock, emit_event
from sit_review_agent.rundir import write_json_atomic
from sit_review_agent.states import STAGE_ON_CAP, MemberOutcome, PhaseName, Stage, stage1_close

#: Node names of the top-level graph.
NODE_INGEST, NODE_OPEN, NODE_CHAIN = "ingest", "stage1_open", "stage1_chain"
NODE_SHARD, NODE_ASSESS = "assess_shard", "assess"
NODE_MERGE, NODE_REFINE, NODE_VERIFY, NODE_REPORT = "merge", "refine", "verify", "report"
#: Sentinel a member node returns when the stage 1 backstop stopped it.
CUT = object()


def _union(a: dict[str, str], b: dict[str, str]) -> dict[str, str]:
    return {**a, **b}


class GraphState(TypedDict, total=False):
    """The control state LangGraph carries (and checkpoints through :class:`RunDirSaver`)."""

    ended: Annotated[dict[str, str], _union]        #: stage 1 member -> ``done`` or ``cut``
    shards: Annotated[list[int], operator.add]      #: assess shards that ended with a result in this run
    stop: Annotated[list[str], operator.add]        #: reasons the run stops after stage 1 (``plan_only``)
    index: int                                      #: ``Send`` payload of one ``assess_shard`` node


class LangGraphOrchestrator(Orchestrator):
    """``Orchestrator.run`` re-expressed as a LangGraph graph; every other method is inherited."""

    def __init__(self, phases: Mapping[PhaseName, Phase] | None = None) -> None:
        super().__init__(phases)
        self._ctx: RunContext | None = None
        self._shard_results: dict[int, Any] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._fired = False
        self._merge_only = False
        self._failed = False
        self._cut: set[int] = set()
        self._assess_t: list[float] = []
        self.saver: RunDirSaver | None = None
        self.mermaid: str = ""

    # ------------------------------------------------------------------ entry

    async def run(self, ctx: RunContext, *, start_at: PhaseName = PhaseName.INGEST) -> RunContext:
        if not ctx.state.completed_phases and ctx.state.budget.started_monotonic == 0.0:
            ctx.state.budget.started_monotonic = ctx.clock.monotonic()
        bind_run_clock(ctx.progress, ctx.elapsed_s)
        self._ctx = ctx
        self._fired = self._merge_only = self._failed = False
        self._tasks = {}
        self._cut = set()
        self._assess_t = []
        self._shard_results = self._load_shards(ctx) if self._sharded() else {}
        self.saver = RunDirSaver(ctx.run_dir.root)
        graph = self.build(ctx, start_at)
        app = graph.compile(checkpointer=self.saver)
        self._write_variant_files(ctx, app)
        ended = {p.value: "done" for p in STAGE_1 if p in ctx.state.completed_phases}
        emit_event(ctx.progress, "run", "orchestrator: langgraph variant (same phases, gateways and writers)",
                   event="orchestrator", name="langgraph", start_at=start_at.value)
        try:
            await app.ainvoke({"ended": ended, "shards": [], "stop": []},
                              config={"configurable": {"thread_id": ctx.state.run_id}})
        except AgentError:
            raise
        except (KeyboardInterrupt, asyncio.CancelledError) as exc:
            self._flush_state(ctx)
            emit_event(ctx.progress, "run", "interrupted; state flushed (resume continues from the last checkpoint)",
                       "warn", event="interrupted", where=ctx.state.current_phase.value if ctx.state.current_phase
                       else "run")
            raise RunInterrupted("interrupted") from exc
        except Exception as exc:  # noqa: BLE001 - an error the graph machinery itself raised
            self._flush_state(ctx)
            raise StageCrash(ctx.state.current_phase.value if ctx.state.current_phase else "run", exc) from exc
        ctx.state.current_phase = None
        return ctx

    def _write_variant_files(self, ctx: RunContext, app: Any) -> None:
        """``<run>/langgraph/graph.mmd`` (the framework's own drawing) and ``variant.json``."""
        from importlib.metadata import PackageNotFoundError, version

        d = ctx.run_dir.root / LANGGRAPH_DIR
        try:
            self.mermaid = app.get_graph(xray=True).draw_mermaid()
        except Exception as exc:  # noqa: BLE001 - the drawing is a reader's aid
            self.mermaid = f"%% draw_mermaid failed: {type(exc).__name__}"
        versions: dict[str, str] = {}
        for name in ("langgraph", "langgraph-checkpoint", "langgraph-prebuilt", "langgraph-sdk"):
            try:
                versions[name] = version(name)
            except PackageNotFoundError:
                versions[name] = "not installed"
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "graph.mmd").write_text(self.mermaid + "\n", encoding="utf-8")
            write_json_atomic(d / "variant.json", {"orchestrator": "langgraph", "versions": versions})
        except OSError:
            pass

    # ------------------------------------------------------------------ the graph

    def build(self, ctx: RunContext, start_at: PhaseName) -> StateGraph:
        g: StateGraph = StateGraph(GraphState)
        g.add_node(NODE_INGEST, self._single_node(PhaseName.INGEST))
        g.add_node(NODE_OPEN, self._open)
        g.add_node(NODE_CHAIN, self._chain(ctx).compile())
        g.add_node(NODE_SHARD, self._shard_node)
        g.add_node(NODE_ASSESS, self._member_node(PhaseName.ASSESS))
        g.add_node(NODE_MERGE, self._merge)
        g.add_node(NODE_REFINE, self._single_node(PhaseName.REFINE))
        g.add_node(NODE_VERIFY, self._single_node(PhaseName.VERIFY))
        g.add_node(NODE_REPORT, self._single_node(PhaseName.REPORT))
        entry = {PhaseName.INGEST: NODE_INGEST, PhaseName.REFINE: NODE_REFINE, PhaseName.VERIFY: NODE_VERIFY,
                 PhaseName.REPORT: NODE_REPORT}.get(start_at, NODE_OPEN)
        g.add_edge(START, entry)
        g.add_edge(NODE_INGEST, NODE_OPEN)
        g.add_conditional_edges(NODE_OPEN, self._fan_out,
                                [NODE_CHAIN, NODE_SHARD, NODE_ASSESS, NODE_MERGE, NODE_VERIFY])
        g.add_edge(NODE_CHAIN, NODE_MERGE)
        g.add_edge(NODE_SHARD, NODE_MERGE)
        g.add_edge(NODE_ASSESS, NODE_MERGE)
        g.add_conditional_edges(NODE_MERGE, self._route_refine, [NODE_REFINE, NODE_VERIFY, END])
        g.add_edge(NODE_REFINE, NODE_VERIFY)
        g.add_edge(NODE_VERIFY, NODE_REPORT)
        g.add_edge(NODE_REPORT, END)
        return g

    def _chain(self, ctx: RunContext) -> StateGraph:
        """The subgraph of understand, plan and research: the members not yet ended, research
        behind a join of the two it depends on (``STAGE_1_DEPENDS``) and the plan-only gate."""
        done = set(ctx.state.completed_phases)
        enabled = ctx.config.agent.phases.enabled
        sub: StateGraph = StateGraph(GraphState)
        heads = [p for p in (PhaseName.UNDERSTAND, PhaseName.PLAN) if p not in done and enabled(p)]
        for p in heads:
            sub.add_node(p.value, self._member_node(p))
            sub.add_edge(START, p.value)
        sub.add_node("gate", lambda state: {})
        sub.add_edge([p.value for p in heads] if heads else START, "gate")
        research = PhaseName.RESEARCH not in done and enabled(PhaseName.RESEARCH)
        if research:
            sub.add_node(PhaseName.RESEARCH.value, self._member_node(PhaseName.RESEARCH))
            sub.add_conditional_edges("gate", self._route_research, [PhaseName.RESEARCH.value, END])
            sub.add_edge(PhaseName.RESEARCH.value, END)
        else:
            sub.add_edge("gate", END)
        return sub

    # ------------------------------------------------------------------ routers (pure, read the context)

    def _route_research(self, state: GraphState) -> str:
        ctx = self._ctx
        assert ctx is not None
        return END if ctx.plan_only or self._fired else PhaseName.RESEARCH.value

    def _fan_out(self, state: GraphState) -> str | list[Send]:
        """After ``stage1_open``: the cap skip, the merge-only path, or the ``Send``s of stage 1."""
        ctx = self._ctx
        assert ctx is not None
        if "cap" in state.get("stop", []):
            return NODE_MERGE if self._shard_results else NODE_VERIFY
        ended = state.get("ended", {})
        sends: list[Send] = []
        chain_has_work = any(p.value not in ended for p in (PhaseName.UNDERSTAND, PhaseName.PLAN, PhaseName.RESEARCH))
        if chain_has_work:
            sends.append(Send(NODE_CHAIN, {}))
        if PhaseName.ASSESS.value not in ended and not ctx.plan_only:
            if self._sharded():
                plan = self.phases[PhaseName.ASSESS].shards(ctx)  # type: ignore[attr-defined]
                todo = [i for i in range(1, len(plan) + 1) if i not in self._shard_results]
                if todo:
                    self._assess_started(ctx, plan, todo)
                    sends += [Send(NODE_SHARD, {"index": i}) for i in todo]
            else:
                sends.append(Send(NODE_ASSESS, {}))
        return sends or NODE_MERGE

    def _route_refine(self, state: GraphState) -> str:
        """After merge: END after the plan, verify on a cap or a disabled refine (disclosed here,
        inside the edge function, as the custom loop discloses it before the stage), else refine."""
        ctx = self._ctx
        assert ctx is not None
        if "plan_only" in state.get("stop", []):
            return END
        if not ctx.config.agent.phases.enabled(PhaseName.REFINE):
            emit_event(ctx.progress, PhaseName.REFINE.value, "skipped (disabled in config/agent.yaml)",
                       event="phase_skipped", reason="disabled", stage=Stage.REFINE.value)
            return NODE_VERIFY
        cap = self._cap(ctx, Stage.REFINE)
        if cap is not None:
            self._skip_on_cap(ctx, Stage.REFINE, cap)
            return NODE_VERIFY
        return NODE_REFINE

    # ------------------------------------------------------------------ nodes

    def _single_node(self, p: PhaseName) -> Any:
        async def node(state: GraphState) -> dict[str, Any]:
            assert self._ctx is not None
            await self._single(self._ctx, p)
            return {}

        node.__name__ = p.value
        return node

    async def _open(self, state: GraphState) -> dict[str, Any]:
        """Open stage 1: the cap check (a cap before any work skips to verify; with finished shards
        on disk it merges them and starts nothing new) and the disabled members."""
        ctx = self._ctx
        assert ctx is not None
        ended = dict(state.get("ended", {}))
        cap = self._cap(ctx, Stage.STAGE_1)
        if cap is not None:
            if not self._shard_results:
                self._skip_on_cap(ctx, Stage.STAGE_1, cap)
                return {"stop": ["cap"]}
            if ctx.state.stop_reason is None:
                ctx.state.stop_reason = cap
            emit_event(ctx.progress, "stage_1", f"stop rule {cap.code} fired; merging the finished shards only", "warn",
                       event="stop_rule", code=cap.code, detail=cap.detail, stage=Stage.STAGE_1.value, to="merge",
                       shards_kept=sorted(self._shard_results))
            self._merge_only = True
            return {"stop": ["cap"]}
        skipped: dict[str, str] = {}
        for p in STAGE_1:
            if p.value not in ended and not ctx.config.agent.phases.enabled(p):
                skipped[p.value] = "done"
                emit_event(ctx.progress, p.value, "skipped (disabled in config/agent.yaml)", event="phase_skipped",
                           reason="disabled", stage=Stage.STAGE_1.value)
        return {"ended": skipped}

    def _assess_started(self, ctx: RunContext, plan: list[Any], todo: list[int]) -> None:
        """What ``AssessPhase.run_shards`` announces when it starts the shards (it is not called here)."""
        from sit_review_agent.phases.assess import known_criteria

        emit_event(ctx.progress, PhaseName.ASSESS.value, "started", event="phase_started", stage=Stage.STAGE_1.value)
        done = sorted(self._shard_results)
        emit_event(ctx.progress, PhaseName.ASSESS.value,
                   f"assessing {len(known_criteria(ctx))} criteria in {len(plan)} concurrent shard(s)"
                   + (f"; {len(done)} already finished" if done else ""), event="assess_started",
                   criteria=len(known_criteria(ctx)), shards=len(plan), finished_before=done,
                   groups=[{"index": i, "name": s.name, "criteria": list(s.criteria)}
                           for i, s in enumerate(plan, start=1)])
        self._assess_t = [ctx.clock.monotonic()]

    def _member_node(self, p: PhaseName) -> Any:
        """A stage 1 member (understand, plan, research, or an unsharded assess) on its own copy of
        the run state, bounded by the stage 1 backstop, merged back and checkpointed when it ends."""

        async def node(state: GraphState) -> dict[str, Any]:
            from sit_review_agent.phases._isolation import isolate, merge_member

            ctx = self._ctx
            assert ctx is not None
            iso = isolate(ctx, p)
            t0 = ctx.clock.monotonic()
            emit_event(ctx.progress, p.value, "started", event="phase_started", stage=Stage.STAGE_1.value)
            out, t1 = await self._member(p.value, p, self.phases[p].run(iso.ctx))
            if out is None:                                 # a sibling failed; its error is the run's
                return {}
            seconds = round(t1 - t0, 3)                     # when the member ended, not when it is merged
            if out is CUT:
                self._member_cut(ctx, p, iso, merge_member)
                if p is not PhaseName.ASSESS:
                    self._ended(ctx, p, seconds, " (stopped at the stage 1 limit)")
                return {"ended": {p.value: "cut"}}
            merge_member(ctx, iso)
            if p is PhaseName.ASSESS:                       # merged now, checkpointed at the close
                ctx.state.budget.phase_seconds[p.value] = seconds
            else:
                self._ended(ctx, p, seconds)
            return {"ended": {p.value: "done"}}

        node.__name__ = p.value
        return node

    async def _shard_node(self, state: GraphState) -> dict[str, Any]:
        """One assess shard (``Send`` payload ``index``), through the phase's own shard runner, so a
        crash inside the shard ends that shard only (BEH-29) and a per-shard process fault applies."""
        ctx = self._ctx
        assert ctx is not None
        i = int(state["index"])
        phase = self.phases[PhaseName.ASSESS]
        inner = getattr(phase, "inner", phase)                  # _run_ProcessFault wraps run_shard on the inner
        plan = phase.shards(ctx)  # type: ignore[attr-defined]
        shard = plan[i - 1]
        runner = getattr(inner, "_shard", None)
        if runner is not None:
            coro = runner(ctx, shard, i, len(plan), self._store)
        else:                                                   # a shard runner without the crash guard
            coro = inner.run_shard(ctx, shard, i, len(plan))
        result, t1 = await self._member(f"assess shard {i}", PhaseName.ASSESS, coro)
        self._assess_t.append(t1)
        if result is None:
            return {}
        if result is CUT:
            self._cut.add(i)
            return {}
        self._shard_results[i] = result
        return {"shards": [i]}

    def _store(self, result: Any) -> None:
        self._shard_results[result.index] = result
        self._store_shard(self._ctx, result)  # type: ignore[arg-type]

    async def _merge(self, state: GraphState) -> dict[str, Any]:
        """Close stage 1: the members never started before the limit, the all-shards-failed rule of
        ``run_shards``, the merge in shard order and the closing checkpoint (``_close``)."""
        ctx = self._ctx
        assert ctx is not None
        if ctx.plan_only:
            if PhaseName.PLAN.value in state.get("ended", {}):
                emit_event(ctx.progress, PhaseName.PLAN.value, "--plan-only: stopping after the plan (zero tool calls)",
                           event="plan_only_stop")
            return {"stop": ["plan_only"]}
        ended: dict[PhaseName, MemberOutcome] = {PhaseName(k): v  # type: ignore[misc]
                                                 for k, v in state.get("ended", {}).items()}
        sharded = self._sharded()
        results = self._shard_results
        if sharded and results and PhaseName.ASSESS not in ended:
            ordered = [results[i] for i in sorted(results)]
            errors = [r for r in ordered if r.outcome == "error"]
            if len(errors) == len(ordered) and len(ordered) == len(self.phases[PhaseName.ASSESS].shards(ctx)):  # type: ignore[attr-defined]
                inner = getattr(self.phases[PhaseName.ASSESS], "inner", self.phases[PhaseName.ASSESS])
                ctx.state.current_phase = PhaseName.ASSESS
                self._flush_state(ctx)
                crashes = getattr(inner, "_crashes", {})
                if any(r.index in crashes for r in errors):
                    first = next(r.index for r in errors if r.index in crashes)
                    raise StageCrash(PhaseName.ASSESS.value, crashes[first])
                raise AssessShardsFailed([(r.index, r.name, getattr(inner, "_errors", {})[r.index]) for r in errors])
            if self._cut:                                   # the backstop stopped shards: cut, disclosed once
                self._member_cut(ctx, PhaseName.ASSESS, None, None)
                ended[PhaseName.ASSESS] = "cut"
            elif not self._merge_only:
                ended[PhaseName.ASSESS] = "done"
            seconds = round((self._assess_t[-1] - self._assess_t[0]), 3) if len(self._assess_t) > 1 else 0.0
            ctx.state.budget.phase_seconds[PhaseName.ASSESS.value] = seconds
            emit_event(ctx.progress, PhaseName.ASSESS.value, f"{len(results)} shard(s) ended in {seconds:.1f}s; "
                       "merged when stage 1 closes", event="shards_ended", shards=len(results), seconds=seconds,
                       outcomes={str(i): r.outcome for i, r in sorted(results.items())})
        if self._fired and not self._merge_only:
            for p, how in stage1_close(ended, []).items():
                if how == "skipped" and p not in ended and ctx.config.agent.phases.enabled(p):
                    self._member_skipped(ctx, p)
        self._close(ctx, sharded, results, ended, fired=self._fired or self._merge_only)
        return {"ended": {PhaseName.ASSESS.value: ended[PhaseName.ASSESS]}} if PhaseName.ASSESS in ended else {}

    # ------------------------------------------------------------------ the backstop and the failure path

    async def _member(self, label: str, p: PhaseName, coro: Any) -> Any:
        """Await a member's coroutine as a task; with the deadline rule active, poll the run clock
        and cancel the task ``stage1_grace_s`` after ``stage_1_end`` (the custom loop's backstop,
        here per node: LangGraph has no per-node timeout, and none on a run clock). A failure maps
        to the typed error the custom loop raises, after the sibling nodes are stopped."""
        from sit_review_agent.phases._isolation import MemberInterrupted, guarded

        ctx = self._ctx
        assert ctx is not None
        t1: list[float] = []

        async def timed() -> Any:
            try:
                return await guarded(coro)
            finally:
                t1.append(ctx.clock.monotonic())            # when the member ended, not when it is merged

        task = asyncio.create_task(timed(), name=f"langgraph-{label}")
        self._tasks[label] = task
        try:
            while True:
                watch = not self._fired and _deadline_active(ctx)
                done, _ = await asyncio.wait({task}, timeout=self.stage1_poll_s if watch else None)
                if done:
                    break
                limit = ctx.config.stop_rules.stage_limits_s.stage_1_end
                if ctx.elapsed_s() < limit + self.stage1_grace_s:
                    continue
                if not self._fired:
                    self._fired = True
                    names = sorted(n for n, t in self._tasks.items() if not t.done())
                    emit_event(ctx.progress, "stage_1",
                               f"stage 1 limit passed by {self.stage1_grace_s:.0f} s; stopping {', '.join(names)}",
                               "warn", event="stage_limit_passed", limit="stage_1_end", limit_s=limit,
                               grace_s=self.stage1_grace_s, stopped=names)
                task.cancel()
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            self._tasks.pop(label, None)
        ended_at = t1[0] if t1 else ctx.clock.monotonic()
        if task.cancelled():
            return (CUT if self._fired and not self._failed else None), ended_at
        exc = task.exception()
        if exc is None:
            return task.result(), ended_at
        self._failed = True
        await self._cancel_others(label)
        ctx.state.current_phase = p
        self._flush_state(ctx)
        if isinstance(exc, MemberInterrupted):
            emit_event(ctx.progress, p.value, "interrupted; state flushed (resume re-runs the unfinished members)",
                       "warn", event="interrupted", where=p.value)
            raise RunInterrupted(f"interrupted during {p.value}") from exc
        if isinstance(exc, asyncio.CancelledError):
            raise RunInterrupted(f"interrupted during {p.value}") from exc
        if isinstance(exc, AgentError):
            raise exc
        raise StageCrash(p.value, exc) from exc

    async def _cancel_others(self, label: str) -> None:
        """Stop the other stage 1 nodes' tasks when one fails (the custom loop cancels its sibling
        tasks before re-raising; LangGraph cancels sibling nodes, but only after this node's
        exception has left it, which the flush above must not wait for)."""
        others = [t for n, t in self._tasks.items() if n != label and not t.done()]
        for t in others:
            t.cancel()
        await asyncio.gather(*others, return_exceptions=True)


def cut_shard(ctx: RunContext, index: int, shard: Any, count: int) -> Any:
    """Re-exported for tests: the result of a shard that had not ended when stage 1 closed."""
    return _cut_shard(ctx, index, shard, count)


__all__ = ["CUT", "GraphState", "LangGraphOrchestrator", "STAGE_ON_CAP", "cut_shard"]
