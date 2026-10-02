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
