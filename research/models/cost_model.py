# Cost model for research/models/README.md section 3. Prices USD/MTok as of 2026-10-02; non-Claude prices partly UNVERIFIED.
# Tuple: (input, cache_write, cache_read, output[, long_ctx_threshold, long_in, long_write, long_read, long_out])
# price: (in, cache_write, cache_read, out, long_threshold, long_in, long_write, long_read, long_out)
P = {
 "claude-fable-5-1":   (10,12.5,0.25,50, None,),
 "claude-opus-5-5":    (4,5,0.20,20, None,),
 "claude-sonnet-5-5":  (2,2.5,0.20,10, None,),
 "claude-haiku-4-5":   (1,1.25,0.10,5, None,),
 "gpt-6-astra":        (10,12.5,1.00,50, 272e3,20,25,2.0,75),
 "gpt-6.1-sol":        (2,2.5,0.10,10, 272e3,4,5,0.20,15),
 "gpt-6-luna":         (0.10,0.10,0.01,0.50, None,),
 "gemini-3.1-pro-preview": (2,2,0.20,12, 200e3,4,4,0.40,18),
 "gemini-3.8-flash (intro)": (0.75,0.75,0.075,3.75, None,),
 "gemini-3.8-flash (2027)":  (1.5,1.5,0.15,7.5, None,),
}
def run(p, N, base=65e3, research=150e3, out=20e3, cache=True):
    inn,w,r,o = p[:4]; th = p[4] if len(p)>4 else None
    per_new = (research+out)/N
    cost=0; tot_in=0
    for i in range(N):
        ctx = base + i*per_new
        tot_in += ctx
        new = base if i==0 else per_new
        old = ctx-new
        if th and ctx>th: inn_,w_,r_,o_ = p[5],p[6],p[7],p[8]
        else: inn_,w_,r_,o_ = inn,w,r,o
        if cache: cost += new*w_/1e6 + old*r_/1e6
        else: cost += ctx*inn_/1e6
        cost += (out/N)*o_/1e6
    return cost, tot_in
print("model | floor(210k in once) | N=20 cached | N=20 no-cache | N=15 cached | N=25 cached | N=20 cached, 60k out")
for m,p in P.items():
    floor = 210e3*p[0]/1e6 + 20e3*p[3]/1e6
    c20,t = run(p,20); n20,_=run(p,20,cache=False); c15,_=run(p,15); c25,_=run(p,25); c20o,_=run(p,20,out=60e3)
    print(f"{m} | {floor:.2f} | {c20:.2f} | {n20:.2f} | {c15:.2f} | {c25:.2f} | {c20o:.2f}")
print("cum input tokens N=20:", run(P['claude-opus-5-5'],20)[1])
# mixed: Opus orchestrator 8 calls holding doc+distilled notes; Sonnet subagents read raw research
def mixed(main, sub, main_calls=10, sub_calls=12):
    # subagents: each reads doc summary 10k + 12.5k raw research, outputs 1.5k (incl thinking), no cache reuse beyond own
    s = sub_calls*((10e3+12.5e3)*P[sub][0]/1e6 + 1.5e3*P[sub][3]/1e6)
    # main: doc 65k cached + distilled notes 3k per sub result ~ 36k total, output 20k
    c,_ = run(P[main], main_calls, base=65e3, research=36e3, out=20e3)
    return s, c, s+c
for main,sub in [("claude-opus-5-5","claude-sonnet-5-5"),("claude-opus-5-5","claude-haiku-4-5"),("claude-sonnet-5-5","claude-haiku-4-5")]:
    print("mixed",main,sub,["%.2f"%x for x in mixed(main,sub)])
# grader: per review: rubric+instructions 4k, review 10k, doc 65k (for grounding), out 4k (thinking+verdict). absolute 3 samples (doc cached)
def grade(m, samples=3, with_doc=True):
    p=P[m]; ctx = 14e3 + (65e3 if with_doc else 0)
    first = ctx*p[1]/1e6 + 4e3*p[3]/1e6
    rest = (samples-1)*(ctx*p[2]/1e6 + 4e3*p[3]/1e6)
    return first+rest
for m in ["claude-sonnet-5-5","claude-opus-5-5","gpt-6.1-sol","gemini-3.1-pro-preview","gpt-6-astra","gemini-3.8-flash (intro)"]:
    print("grade",m, "%.3f"%grade(m), "%.3f"%grade(m,with_doc=False))

# ---------------------------------------------------------------------------
# ALL-OPUS SECTION (added 2026-10-02 after the user decision: every agent call
# uses claude-opus-5-5; no Sonnet/Haiku sub-tasks). Feeds docs/BUDGET.md and
# section 3 of README.md. Run: python3 cost_model.py
# Token base is still UNVERIFIED (audit U3): re-run with measured count_tokens
# values once the SIT PDF has been counted on the laptop.
# ---------------------------------------------------------------------------
OP = "claude-opus-5-5"
BATCH = 0.5  # Message Batches: 50% off every token incl. cache reads/writes (claude-api skill)

def opus_run(N=20, base=65e3, research=150e3, out=20e3):
    return run(P[OP], N, base=base, research=research, out=out)[0]

print("\n== ALL-OPUS: per-run agent cost (USD) ==")
SCEN = {
    "central (65K base, 150K research, 20 calls, 20K out)": dict(),
    "hybrid ingestion (+13K canonical text in cached prefix)": dict(base=78e3),
    "hybrid + heavy thinking (60K out)": dict(base=78e3, out=60e3),
    "text-only ingestion (20K base)": dict(base=20e3),
    "large PDF (100K base)": dict(base=100e3),
    "25 calls, hybrid": dict(N=25, base=78e3),
}
for k, kw in SCEN.items():
    print(f"  {k}: {opus_run(**kw):.2f}")
s, c, t = mixed(OP, OP)
print(f"  Opus orchestrator + Opus readers (reader pattern kept, all Opus): readers {s:.2f} + main {c:.2f} = {t:.2f}")

# Per-condition agent cost, all Opus, hybrid ingestion base (78K). Shapes are
# planning assumptions, not measurements.
B = 78e3
COND = {
    "FULL":  opus_run(N=20, base=B),
    "B0 (single call, ~15K out)": (B + 5e3) * P[OP][0] / 1e6 + 15e3 * P[OP][3] / 1e6,
    "B0-$ (cost-matched to FULL)": opus_run(N=20, base=B),
    "A1 no research (12 calls)": opus_run(N=12, base=B, research=0, out=18e3),
    "A2 no iteration (12 calls, 100K research)": opus_run(N=12, base=B, research=100e3, out=16e3),
    "A3 no verification (17 calls)": opus_run(N=17, base=B, out=17e3),
    "A4e effort low (FULL shape, ~12K out)": opus_run(N=18, base=B, out=12e3),
    "A5 tools disabled (= A1 shape)": opus_run(N=12, base=B, research=0, out=18e3),
}
print("\n== ALL-OPUS: per-condition cost per run (USD) ==")
for k, v in COND.items():
    print(f"  {k}: {v:.2f}")

# Grading pipeline per review (grading/README.md section 6.1), audit C25.
# Calls: segment (13K in, 3K out, no doc); Pass A x2 (4K rubric + doc + 10K findings, 4K out);
# Pass B x2 (4K rubric + doc + 10K review + 3K PassA table, 5K out); 3rd-sample
# adjudication with prob 0.3 (one Pass A + one Pass B). Doc (65K) cached after first write.
# Key-aware mode is diagnostic only and excluded.
def grade_pipeline(m, doc=65e3, adj_p=0.3, batch=False):
    inn, w, r, o = P[m][:4]
    cost = 13e3 * inn / 1e6 + 3e3 * o / 1e6                     # segment
    calls = [(4e3 + doc, 10e3, 4e3)] * 2 + [(4e3 + doc, 13e3, 5e3)] * 2
    first = True
    for pref, fresh, out in calls:
        cost += pref * (w if first else r) / 1e6 + fresh * inn / 1e6 + out * o / 1e6
        first = False
    cost += adj_p * ((4e3 + doc) * r / 1e6 * 2 + 23e3 * inn / 1e6 + 9e3 * o / 1e6)
    return cost * (BATCH if batch else 1)

# Matcher + judges per agent run (methodology/metrics.md 2.3, 5.1-5.2): 14 flaws;
# listwise shortlist 1 call/flaw (findings list 10K cached + 0.5K flaw, 0.3K out);
# pairwise 3 candidates x 3 samples per flaw (1.5K in, 0.3K out); adjudicate ~8
# unmatched findings (2K in, 0.3K out); G3/citation judge ~20 findings (2K in, 0.3K out).
def matcher_judges(m, flaws=14, batch=False):
    inn, w, r, o = P[m][:4]
    c = 10e3 * w / 1e6 + (flaws - 1) * 10e3 * r / 1e6 + flaws * (0.5e3 * inn + 0.3e3 * o) / 1e6
    c += flaws * 9 * (1.5e3 * inn + 0.3e3 * o) / 1e6
    c += 8 * (2e3 * inn + 0.3e3 * o) / 1e6
    c += 20 * (2e3 * inn + 0.3e3 * o) / 1e6
    return c * (BATCH if batch else 1)

print("\n== Grading cost per review and matcher+judges per run (USD) ==")
for m in ["gpt-6.1-sol", "gemini-3.1-pro-preview", "claude-sonnet-5-5", OP]:
    b = m.startswith("claude")
    print(f"  {m}: grade {grade_pipeline(m):.2f} (batch {grade_pipeline(m, batch=True) if b else float('nan'):.2f}); "
          f"matcher+judges {matcher_judges(m):.2f} (batch {matcher_judges(m, batch=True) if b else float('nan'):.2f})")

# Budget matrix (docs/BUDGET.md). Run counts per line item.
FULL, B0 = COND["FULL"], COND["B0 (single call, ~15K out)"]
ABL = ["B0-$ (cost-matched to FULL)", "A1 no research (12 calls)", "A2 no iteration (12 calls, 100K research)",
       "A3 no verification (17 calls)", "A4e effort low (FULL shape, ~12K out)", "A5 tools disabled (= A1 shape)"]
items = [
    ("1 development iteration on S-dev (FULL)", 60 * FULL, 60),
    ("2 S-dev pilot: FULL vs B0, k=3, 3 docs", 9 * FULL + 9 * B0, 18),
    ("3 primary: FULL + B0, k=5, 12 docs", 60 * FULL + 60 * B0, 120),
    ("4 ablations: 6 conditions, k=3, 6 held-out/blind docs", sum(COND[a] for a in ABL) * 18, 108),
    ("5 v2 re-review: FULL, k=3, 4 v2 docs", 12 * FULL, 12),
    ("6 S-heldout milestone checks: 2 extra accesses x 2 docs x k=3", 12 * FULL, 12),
    ("7 overfitting probes: paraphrase+reorder, 3 docs, k=3", 18 * FULL, 18),
    ("8 robustness L1 (gate subset): ~15 scenarios x k~4", 60 * FULL, 60),
    ("9 L2 rehearsals + cassette recording + fresh clone", 25 * FULL, 25),
]
agent_total = sum(c for _, c, _ in items)
graded_reviews = 120 + 108 + 12 + 12 + 30  # eval-matrix reviews graded once (3 samples inside pipeline) + ~30 grader meta-validation (V1-V13) grades
matched_runs = 120 + 108 + 12 + 12 + 18 + 18 + 60 + 60  # eval matrix + pilot + overfitting probes + dev iteration + robustness L1 (C31)
print("\n== Budget matrix, all-Opus agent (USD) ==")
for name, c, n in items:
    print(f"  {name}: runs={n} cost={c:.0f}")
print(f"  agent subtotal: runs={sum(n for *_, n in items)} cost={agent_total:.0f}")
print(f"  graded reviews={graded_reviews}, matched runs={matched_runs}")
branches = [
    ("A  cross-family key: grader + matcher + judges on gpt-6.1-sol (UNVERIFIED price)", "gpt-6.1-sol", False, "gpt-6.1-sol", False),
    ("B1 Anthropic-only: Sonnet 5.5 grader (batch), matcher+judges local open-weight ($0 API)", "claude-sonnet-5-5", True, None, False),
    ("B2 Anthropic-only: Opus 5.5 grader (batch), matcher+judges local ($0 API)", OP, True, None, False),
    ("B3 worst case: Opus 5.5 grader + local model fails U8, matcher+judges on Opus 5.5 (batch)", OP, True, OP, True),
]
for label, gm, gb, mm, mb in branches:
    g = graded_reviews * grade_pipeline(gm, batch=gb)
    mj = matched_runs * matcher_judges(mm, batch=mb) if mm else 0.0
    tot = agent_total + g + mj
    print(f"  [{label}] grader {g:.0f} + matcher/judges {mj:.0f}; total {tot:.0f}; x1.3 = {tot * 1.3:.0f}")
