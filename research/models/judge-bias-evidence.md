# Evidence on LLM-as-judge bias: annotated bibliography

Supports the grader design in [`README.md`](README.md) §4–§6. Compiled 2026-10-02.

**How each entry was checked.** arXiv, OpenReview and ACL Anthology could not be fetched directly from the research sandbox (the egress proxy blocks them). Each entry was checked against search-engine abstracts and snippets of the paper's own page. Numbers marked *(snippet)* come from those abstracts and have not been read in the full PDF. Entries marked **UNVERIFIED** need a full-text read before you cite their specific numbers in a submission. The pre-2025 classics (1–6) are well established and their headline numbers match the abstracts.

---

## A. Foundational: LLM judges and their biases

### 1. Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (NeurIPS 2023 Datasets & Benchmarks)
<https://arxiv.org/abs/2306.05685>

This paper established LLM-as-a-judge. Against 3K expert votes and 3K crowd votes, GPT-4 agreed with humans more than 80% of the time, the same level as human–human agreement. It also catalogued the biases that every later paper builds on. **Position bias:** every judge favoured one slot, and GPT-4 was the most consistent at 65% when orders were swapped. **Verbosity bias:** Claude-v1 and GPT-3.5 failed more than 90% of a "repetitive padding" attack; GPT-4 failed 8.7%. **Self-enhancement bias:** judges favoured their own outputs, though the authors could not establish it conclusively with their data. **Takeaway for us:** compare the judge against human agreement as the ceiling (our E5). Always run pairwise judgments in both orders (E2). Test length padding explicitly (E3).

### 2. Wang et al., "Large Language Models are not Fair Evaluators" (ACL 2024)
<https://arxiv.org/abs/2305.17926>

This paper shows how badly position bias can distort results. Simply reordering the pair let Vicuna-13B "beat" ChatGPT on 66 of 80 questions when ChatGPT was the judge. GPT-4 favoured the first slot and ChatGPT the second. The paper proposes Multiple Evidence Calibration (write the reasoning before the score), Balanced Position Calibration (average over both orders) and Human-in-the-Loop calibration (route uncertain items to humans). Together these improved alignment with humans by 9.8% for GPT-4 and 14.3% for ChatGPT. **Takeaway:** our design uses all three ideas: evidence first, both orders, and humans review high-variance items.

### 3. Liu et al., "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment" (EMNLP 2023)
<https://aclanthology.org/2023.emnlp-main.153/> · <https://arxiv.org/abs/2303.16634>

G-Eval has the judge generate evaluation steps (chain of thought) and then fill in a form, optionally weighting scores by token probabilities. It reached a Spearman correlation of 0.514 with humans on summarisation (UniEval had 0.474, GPTScore 0.417). The authors themselves warn that LLM evaluators may be **biased towards LLM-generated text**. **Takeaway:** structured, criterion-by-criterion scoring with reasoning first improves alignment. The bias-toward-LLM-text warning is why judge-free metrics (planted-flaw recall, citation validation) should carry our research claims. Probability-weighted scores are not available on Claude 5.x, which exposes no logprobs; we use 3 samples instead.

### 4. Kim et al., "Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models" (EMNLP 2024); and Prometheus 1 (ICLR 2024)
<https://aclanthology.org/2024.emnlp-main.248/> · <https://arxiv.org/abs/2405.01535> · Prometheus 1: <https://arxiv.org/abs/2310.08491>

Prometheus showed that an evaluator given a **user-defined rubric with score descriptions for each level, plus a reference answer**, tracks human and GPT-4 judgments closely. Prometheus 2 merges weights from a direct-assessment model and a pairwise-ranking model. It reaches the highest human agreement among open judges on 4 direct and 4 pairwise benchmarks and "reduces the performance gap with GPT-4 in half". The weights are open. **Takeaway:** (a) anchored rubrics are the main lever for absolute scoring, which is why our rubric gives a written anchor and exemplar for every level; (b) Prometheus 2 is a candidate **local, cross-family judge** when only one API key is available. Whether it copes with ~10K-token design reviews is **UNVERIFIED**; calibrate it on the human anchor set first.

### 5. Saito et al., "Verbosity Bias in Preference Labeling by Large Language Models" (2023)
<https://arxiv.org/abs/2310.10076>

The paper quantifies how GPT-4 prefers longer answers more than humans do when quality is similar, in the context of RLAIF labelling. **Takeaway:** design reviews invite padding. The grader must be explicitly told that length is not quality, and the score–length correlation must be reported (E3).

### 6. Verga et al., "Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models" (2024)
<https://arxiv.org/abs/2404.18796>

A Panel of LLM evaluators (PoLL) built from three smaller models from **different families** (Command R, GPT-3.5, Claude Haiku) matched human judgments better than a single GPT-4 judge across six datasets. It showed less intra-model bias and cost more than 7x less. **Takeaway:** diversity across families matters more than judge size. This supports a multi-provider panel, reported per judge, over a single big Claude judge.

---

## B. Self-preference specifically

### 7. Panickssery, Bowman & Feng, "LLM Evaluators Recognize and Favor Their Own Generations" (NeurIPS 2024)
<https://arxiv.org/abs/2404.13076> · [NeurIPS PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/7f1f0218e45f5414c79c0679633e47bc-Paper-Conference.pdf)

This is the canonical self-preference result. LLM evaluators score their own outputs higher than other models' outputs that humans rate as equal. Out of the box, GPT-4 and Llama 2 can tell their own text from other models' and humans' text with non-trivial accuracy. Fine-tuning revealed a **linear correlation between self-recognition ability and self-preference strength**, and controlled experiments suggest the link is causal rather than confounded. **Takeaway:** an Opus 5.5 agent judged by a Claude judge is exactly the setting where this bias appears. The mechanism is recognition, so blinding and style normalisation help. Changing the judge's *family* removes the recognition signal most directly.

### 8. Wataoka, Takahashi & Ri, "Self-Preference Bias in LLM-as-a-Judge" (2024)
<https://arxiv.org/abs/2410.21819>

The paper proposes a quantitative self-preference metric and finds GPT-4 had the strongest bias of the models tested (0.520 on their metric, *(snippet)*). Its mechanism: judges give **higher scores to lower-perplexity (more familiar) text than humans do, whether or not they wrote it**. **Takeaway:** self-preference is partly "same-style preference", so a judge from the same family, trained on similar data with a similar house style, should show some of it even if it is a different model. That explains why using Sonnet 5.5 to judge Opus 5.5 only partly mitigates the bias.

### 9. Chen et al., "Do LLM Evaluators Prefer Themselves for a Reason?" (2025)
<https://arxiv.org/abs/2504.03846>

On verifiable tasks (maths, factual QA, code), the paper separates *legitimate* self-preference (the judge's own answer really is better) from *harmful* self-preference (favouring its own wrong answer). Stronger models prefer themselves more, but mostly legitimately. **Harmful self-preference persists when the judge was wrong as a generator, and is more pronounced in stronger models when they err.** Longer chain-of-thought before judging reduces the harmful part. **Takeaway:** the bias matters most on exactly the items where the agent made a mistake, which are the ones a grader most needs to catch. This supports setting judge effort to high with evidence before the verdict, and keeping a cross-family judge.

### 10. "Are LLM Evaluators Really Narcissists? Sanity Checking Self-Preference Evaluations" (2026)
<https://arxiv.org/abs/2601.22548> (**UNVERIFIED**: abstract-level only)

This is a methodological counterweight. Much measured "self-preference" comes from the evaluator being unreliable on questions it cannot solve itself, not from favouring its own authorship. Against a null hypothesis that conditions on evaluator quality, only about 51% of previously reported significant examples stay significant. Those examples cover 89.6% of the self-preference probability mass *(snippet)*. **Takeaway:** self-preference is real but smaller than naive measurements suggest. Our E1 design should hold the author fixed and compare judges, rather than just comparing a judge's scores across authors, which would confound bias with judge competence.

### 11. Yang et al., "Quantifying and Mitigating Self-Preference Bias of LLM Judges" (2026)
<https://arxiv.org/abs/2604.22891> (**UNVERIFIED**: abstract-level only)

The paper builds **equal-quality response pairs** automatically, so bias can be separated from the ability to discriminate quality without human gold labels. A "structured multi-dimensional evaluation" strategy (decomposing the judgment to reduce cognitive load) cut SPB by **31.5% on average** *(snippet)*. **Takeaway:** this supports analytic, per-criterion rubrics over holistic scores, and it is the basis for our E6 style-swap test.

### 12. "Self-Preference Bias in Rubric-Based Evaluation of Large Language Models" (2026)
<https://arxiv.org/abs/2604.06996> (**UNVERIFIED**: abstract-level only)

This is the first study of SPB when judges give **binary per-rubric-item verdicts**, which is closest to our grading format. SPB persists **even for fully objective, programmatically verifiable rubric items**. Among items the generator actually failed, judges were **more than 50% more likely to wrongly mark the item satisfied when the output was their own**. On HealthBench's subjective rubrics, SPB moved scores by **up to 10 points**. Negative rubric items ("does not ...") and subjective areas were most affected. Ensembling judges helped but did not eliminate it *(snippet)*. **Takeaway:** the most directly relevant 2026 result. Analytic rubrics alone do not fix same-family bias. Mechanically checkable items should be checked in code, not by any LLM, and a cross-family judge is still needed.

---

## C. Same-family and related-model bias

### 13. Li et al., "Preference Leakage: A Contamination Problem in LLM-as-a-judge" (ICLR 2026)
<https://arxiv.org/abs/2502.01534>

The paper defines three kinds of relatedness between a data generator and a judge: **the same model, an inheritance relationship (e.g. distillation), and the same model family**. It shows judges are biased toward student models trained on data from related models. This "preference leakage" is pervasive and **harder to detect than previously known judge biases**. **Takeaway:** the bias is not only about a model recognising its own text. A same-family judge such as Sonnet 5.5 judging Opus 5.5 still counts as "related". This is the strongest published argument that a different Claude model is not enough independence for research-grade claims.

### 14. Awuni et al., "Who Judges Matters: Measuring Family-Conditioned Preference in LLM-as-Judge Panels" (2026)
<https://arxiv.org/abs/2609.17857> · code: <https://github.com/AwuniDavid/who-judges-matters> (**UNVERIFIED**: abstract-level only)

This study uses a fully crossed pairwise design (9,312 judgments, four open-weight families: Llama 3.1, Qwen 2.5, Gemma 2, Yi 1.5). **Every family showed a positive same-family lift of 3.4 to 8.4 percentage points.** The global family-preference score was 0.067 (95% CI 0.053–0.084, permutation p = 0.0002), and it survived panel quality controls and a human-consensus anchor *(snippet)*. The paper also provides a corrected estimator that holds the candidate family fixed and compares judges. **Takeaway:** this is our best estimate of what a single-provider setup costs: roughly a 3–8 pp inflation in pairwise win rate. Its estimator and released code are the template for our E1 swap test. Caveat: it covers open-weight 2024-era families, not Claude, GPT or Gemini.

### 15. "Judging the Judges: A Systematic Evaluation of Bias Mitigation Strategies in LLM-as-a-Judge Pipelines" (2026)
<https://arxiv.org/abs/2604.23178> (**UNVERIFIED**: abstract-level only)

The paper compares mitigation strategies head to head. **Position swap** (judge both orders and call a tie if they disagree) is the most common strategy and the only single-call one that significantly helped Gemini Flash (+4.7 pp). It *hurt* GPT-4o (−2.4 pp), **increased verbosity bias** (+0.07) while reducing style bias, and harmed accuracy on adversarial LLMBar items, where a clear winner existed and forcing consensus made the judge second-guess itself *(snippet)*. **Takeaway:** mitigations interact. Always pair position swap with a length control, use pairwise only for A/B ablations, and measure several biases at once (E2 and E3 together) rather than assuming one fix is free.

---

## Synthesis: what this means for an agent and judge from the same family

1. **The direction is consistent.** Every study that measures it (1, 7, 8, 9, 12, 13, 14) finds judges favour their own or related outputs. No study found the bias absent for a same-family setup.
2. **The size is moderate and depends on the task.** Expect a few points on pairwise win rate (3–8 pp, #14) and up to about 10 points on subjective rubrics (#12). Corrected estimates are smaller than naive ones (#10). It is largest exactly where the agent is wrong (#9, #12), which are the cases a grader exists to catch.
3. **A different model from the same family is a partial fix only.** Perplexity and style familiarity (#8) and family relatedness (#13, #14) persist across model sizes within a family.
4. **The mitigations with evidence, ranked:** (a) a judge from a different family (#6, #13, #14); (b) judge-free or programmatic checks for anything objective (#3, #12); (c) analytic, anchored rubrics (#4, #11); (d) reasoning before the verdict (#2, #9); (e) both orders for pairwise judgments plus a length control (#1, #2, #15); (f) multi-family panels reported per judge (#6, #12); (g) a human anchor set (#1).
5. **What we cannot claim.** With 10–20 documents, a non-significant swap-test result does not show there is no bias (power analysis in README §6). Report confidence intervals and present LLM-judge scores as supporting evidence, with judge-free metrics as the primary evidence.

## Not yet read, worth checking if time permits (UNVERIFIED, titles only from search results)

- "Self- and Other-Labels Induce Bidirectional Bias in LLM Judges", <https://arxiv.org/abs/2608.18091>. It suggests that showing the judge authorship labels biases scores in both directions, which argues for blinding.
- "Inside the Unfair Judge: A Mechanistic Interpretability Account of LLM-as-Judge Bias", <https://arxiv.org/abs/2607.11871>.
- "Breaking the Mirror: Activation-Based Mitigation of Self-Preference in LLM Evaluators", <https://arxiv.org/abs/2509.03647>. This needs open weights, so it does not apply to API judges.
- "CyclicJudge: Mitigating Judge Bias Efficiently in LLM-based Evaluation", <https://arxiv.org/abs/2603.01865>.
- "LLM Judges Have Dark Current: A Psychometric Datasheet for LLM-as-a-Judge Evaluation", <https://arxiv.org/abs/2606.15610>.
- Thakur et al., "Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges" (2024), <https://arxiv.org/abs/2406.12624>. From memory, it recommends Cohen's κ over percent agreement; not re-checked this session.
