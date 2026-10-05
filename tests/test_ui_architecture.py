"""The Architectural design view of ``dra ui`` (5 Oct 2026): ``ui/architecture.py`` fills the words of
``static/architecture.json`` from the config and the code, ``GET /architecture`` serves them, and ``architecture.js``
draws the diagram whose every box opens a panel with a Simple and an Advanced tab. Offline: the routes through a test
client, the page in a real browser over a small synthetic run directory (``test_ui_stages.make_run``)."""

from __future__ import annotations

import re
import shutil
import threading
import time
import types
from pathlib import Path
from typing import Any, get_args

import pytest
from starlette.testclient import TestClient

from sit_review_agent.config import ConfigOverrides, LLMSettings, load_config
from sit_review_agent.tools import gateway as tool_gateway
from sit_review_agent.ui import architecture
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import UIState, architecture_view, build_app
from test_ui_stages import RUN, _free_port, make_run  # type: ignore[import-not-found]

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "agent" / "sit_review_agent" / "ui" / "static"
JS = (STATIC / "architecture.js").read_text(encoding="utf-8")
CSS = (STATIC / "architecture.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def view() -> dict[str, Any]:
    return architecture_view()


def _strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [s for n in node for s in _strings(n)]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    return []


# ------------------------------------------------------------------ the words: complete, filled, cited


def test_every_topic_has_a_simple_and_an_advanced_account(view: dict[str, Any]) -> None:
    topics = view["topics"]
    assert sorted(view["order"]) == sorted(topics) and len(set(view["order"])) == len(view["order"])
    for key, t in topics.items():
        assert t["title"] and t["kind"], key
        assert len(t["simple"]["lead"]) > 40 and t["simple"].get("points"), key
        assert t["advanced"] and all(b["h"] and b["src"] and (b.get("items") or b.get("shards") or b.get("servers"))
                                     for b in t["advanced"]), key


def test_every_placeholder_is_filled_and_no_study_aid_words_remain(view: dict[str, Any]) -> None:
    text = _strings({k: v for k, v in view.items() if k != "facts"})
    assert not [s for s in text if re.search(r"\{[a-z_0-9]+\}", s)]
    joined = "\n".join(text)
    assert "—" not in joined                                   # no em dash
    for phrase in ("your notes", "Say it like this", "Rehearse", "Show answer", "notes said"):
        assert phrase.lower() not in joined.lower(), phrase


def test_an_unknown_placeholder_is_an_error_not_a_blank(tmp_path: Path) -> None:
    bad = tmp_path / "a.json"
    bad.write_text('{"order": ["x"], "topics": {"x": {"title": "{no_such_fact}"}}}', encoding="utf-8")
    with pytest.raises(KeyError):
        architecture.view(load_config(None), path=bad)


def test_every_cited_path_exists_and_holds_its_symbol(view: dict[str, Any]) -> None:
    content = architecture.load_content()
    assert len(architecture.sources(content)) > 60
    assert architecture.missing_sources(content, REPO) == []


def test_the_source_check_catches_a_missing_file_and_a_missing_symbol(tmp_path: Path) -> None:
    content = {"topics": {"x": {"advanced": [{"src": "config/agent.yaml shards; config/no_such.yaml; "
                                                     "config/agent.yaml no_such_symbol"}]}}}
    bad = architecture.missing_sources(content, REPO)
    assert [b.split(" ", 1)[0] for b in bad] == ["config/no_such.yaml", "config/agent.yaml"]


# ------------------------------------------------------------------ the diagram cannot drift from config or code


def test_the_shards_servers_backends_and_layers_are_read_not_written(view: dict[str, Any]) -> None:
    cfg = load_config(None)
    f = view["facts"]
    groups = cfg.agent.assess.shards_for([c.id for c in cfg.criteria.criteria])
    assert f["shard_count"] == len(groups) and [s["name"] for s in f["shards"]] == [g.name for g in groups]
    assert view["topics"]["assess"]["title"] == f"Assess: {len(groups)} shards"
    assert f["servers"] == [{"name": s.name, "enabled": s.enabled} for s in cfg.tools.servers]
    assert f["backends"] == list(get_args(LLMSettings.model_fields["backend"].annotation))
    assert f["backend_default"] == cfg.agent.llm.backend
    doc_names = re.findall(r"^\s{4}(\w+)\s", tool_gateway.__doc__ or "", flags=re.M)
    assert [n.split(" | ")[0] for n in f["tool_layers"]] == [n for n in doc_names if n != "base"] + ["MCPToolGateway"]
    for layer in f["tool_layers"]:
        for name in layer.split(" | "):
            assert isinstance(getattr(tool_gateway, name), type), name
    demo = load_config(None, ConfigOverrides(profile="demo")).stop_rules
    assert (f["demo_stage_1_end"], f["demo_deadline_s"]) == (demo.stage_limits_s.stage_1_end, demo.deadline_seconds)


def test_a_layer_named_in_the_docstring_but_not_a_class_is_left_out() -> None:
    fake = types.ModuleType("fake_gateway")
    fake.__doc__ = ("Layers, outermost first::\n\n    LoggingToolGateway   writes the log\n    RemovedGateway   gone\n"
                    "    base             MCPToolGateway (live) | GoneGateway\n\nAfter the block.\n")
    fake.LoggingToolGateway = type("LoggingToolGateway", (), {})  # type: ignore[attr-defined]
    fake.MCPToolGateway = type("MCPToolGateway", (), {})  # type: ignore[attr-defined]
    assert architecture.tool_layers(fake) == ["LoggingToolGateway", "MCPToolGateway"]


def test_a_config_with_other_shards_changes_the_words() -> None:
    cfg = load_config(None)
    crit = [c.id for c in cfg.criteria.criteria]
    two = cfg.agent.assess.model_copy(update={"shards": [
        type(cfg.agent.assess.shards[0])(name="first_half", criteria=crit[: len(crit) // 2]),
        type(cfg.agent.assess.shards[0])(name="second_half", criteria=crit[len(crit) // 2:])]})
    other = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"assess": two})})
    v = architecture.view(other)
    assert v["facts"]["shard_count"] == 2 and v["topics"]["assess"]["title"] == "Assess: 2 shards"
    assert "into 2 groups" in v["topics"]["assess"]["simple"]["lead"]


def test_the_robustness_numbers_come_from_the_results_table(tmp_path: Path) -> None:
    rows = architecture.robustness_summary(REPO)
    line = next(ln for ln in (REPO / architecture.ROBUSTNESS_SUMMARY).read_text().splitlines() if ln.startswith("P0"))
    assert [rows[k] for k in ("robust_total", "robust_pass", "robust_fail", "robust_blocked")] == \
        [int(c) for c in (line.split()[i] for i in (1, 2, 3, 5))]
    assert architecture.robustness_summary(tmp_path)["robust_total"] == "not recorded"


# ------------------------------------------------------------------ the static files keep the page's rules


def test_the_script_and_sheet_keep_the_page_rules() -> None:
    code = re.sub(r"//[^\n]*", "", JS)
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS and "document.write" not in JS
    assert set(re.findall(r"(?<![A-Za-z0-9_.#\\-])(\d+(?:\.\d+)?)", code)) <= {"0", "1"}
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", CSS + JS)
    assert "@keyframes" not in CSS and "animation" not in CSS and ".animate(" not in JS
    for decl in re.findall(r"transition:\s*([^;]+);", CSS):
        assert all(p.split()[0] in ("background-color", "border-color") for p in decl.split(",")), decl
    assert "http://" not in JS + CSS and "https://" not in JS + CSS


def test_the_route_serves_the_view() -> None:
    state = UIState(runs_dir=REPO, repo_root=REPO, launcher=Launcher(repo_root=REPO), chat_client=None,  # type: ignore[arg-type]
                    profiles=[], tools=[])
    body = TestClient(build_app(state)).get("/architecture").json()
    assert body["order"][0] == "user" and body["facts"]["shard_count"] >= 1


# ------------------------------------------------------------------ the page, in a real browser


@pytest.fixture
def page(tmp_path: Path):
    uvicorn = pytest.importorskip("uvicorn")
    sync_api = pytest.importorskip("playwright.sync_api")
    runs = tmp_path / "runs"
    make_run(runs)
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO), chat_client=None,
                    profiles=[], tools=[])  # type: ignore[arg-type]
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        yield pg, f"http://127.0.0.1:{port}"
        browser.close()
    server.should_exit = True
    th.join(timeout=5)
    shutil.rmtree(runs, ignore_errors=True)
    assert errors == []


def _open(pg: Any, base: str, query: str = "") -> None:
    pg.goto(f"{base}/?page=architecture{query}")
    pg.wait_for_selector("#arch-diagram .arch-box")


def test_the_rail_item_follows_replay_and_opens_the_view(page) -> None:
    pg, base = page
    pg.goto(base + "/")
    items = pg.locator(".navrail-item").evaluate_all("(els) => els.map((e) => e.dataset.page)")
    assert items[items.index("replay") + 1] == "architecture"
    pg.locator('.navrail-item[data-page="architecture"]').click()
    pg.wait_for_selector("#arch-diagram .arch-box")
    assert "page=architecture" in pg.url
    assert pg.locator('.navrail-item[data-page="architecture"]').get_attribute("class").split().count("active") == 1


def test_every_topic_opens_both_tabs_with_words_and_its_box_stays_marked(page) -> None:
    pg, base = page
    _open(pg, base)
    order = pg.evaluate("ARCH.data.order")
    assert len(order) == pg.evaluate("Object.keys(ARCH.data.topics).length")
    where = ("() => { const r = document.querySelector('.arch-diagram').getBoundingClientRect();"
             " return [r.left, r.top + scrollY, r.width, r.height]; }")
    top = pg.evaluate(where)
    for key in order:
        btn = pg.locator(f'.arch-surface [data-topic="{key}"]').first
        btn.click()
        assert btn.get_attribute("aria-expanded") == "true" and "on" in btn.get_attribute("class").split(), key
        assert pg.evaluate("document.activeElement.id") == "ap-title"
        for tab in ("simple", "advanced"):
            pg.locator(f'#ap-tabs [data-tab="{tab}"]').click()
            assert pg.locator(f'#ap-tabs [data-tab="{tab}"]').get_attribute("aria-selected") == "true"
            assert len(pg.locator("#ap-content").inner_text().strip()) > 60, (key, tab)
        assert pg.evaluate(where) == top, key                       # the open panel never moves the diagram
        pg.keyboard.press("Escape")
        assert pg.locator("#arch-panel").is_hidden() and btn.get_attribute("aria-expanded") == "false"
        assert pg.evaluate("document.activeElement.dataset.topic") == key


def test_the_diagram_draws_the_configured_shards_and_layers(page) -> None:
    pg, base = page
    _open(pg, base)
    f = pg.evaluate("ARCH.data.facts")
    assert pg.locator(".arch-shards .arch-chip").count() == f["shard_count"]
    assert pg.locator(".arch-chips.layers .arch-chip").count() == len(f["tool_layers"])


def test_the_tab_choice_stays_as_the_topics_are_walked(page) -> None:
    pg, base = page
    _open(pg, base, "&topic=understand")
    pg.locator('#ap-tabs [data-tab="advanced"]').click()
    pg.locator('#ap-nav [data-step="next"]').click()
    assert pg.evaluate("ARCH.topic") == "plan"
    assert pg.locator('#ap-tabs [data-tab="advanced"]').get_attribute("aria-selected") == "true"
    _open(pg, base, "&topic=verify")                                 # a new visit keeps it too (localStorage)
    assert pg.locator('#ap-tabs [data-tab="advanced"]').get_attribute("aria-selected") == "true"


def test_the_keyboard_walks_the_pipeline_and_a_hash_opens_a_topic(page) -> None:
    pg, base = page
    pg.goto(base + "/#architecture/plan")
    pg.wait_for_selector("#arch-panel:not([hidden])")
    assert pg.evaluate("ARCH.topic") == "plan" and "topic=plan" in pg.url
    pg.locator("#ap-title").focus()
    pg.keyboard.press("ArrowRight")
    order = pg.evaluate("ARCH.data.order")
    assert pg.evaluate("ARCH.topic") == order[order.index("plan") + 1]
    pg.keyboard.press("ArrowLeft")
    pg.keyboard.press("ArrowLeft")
    assert pg.evaluate("ARCH.topic") == order[order.index("plan") - 1]
    assert pg.locator("#ap-nav").inner_text().startswith("Previous: ")


def test_in_this_run_reads_the_stage_route_and_links_to_the_run_log(page) -> None:
    pg, base = page
    _open(pg, base, "&topic=refine")
    pg.locator('#ap-tabs [data-tab="advanced"]').click()
    pg.wait_for_selector("#ap-inrun .kv")
    assert RUN in pg.locator("#ap-inrun h3").inner_text()
    assert "Findings in" in pg.locator("#ap-inrun").inner_text()
    pg.locator("#ap-inrun .arch-runlink").click()
    pg.wait_for_function("window.SIT.state.panel && window.SIT.state.panel.key === 'refine'", timeout=15000)
