# Kaggle (and adjacent) candidates: full per-candidate record

Companion to [README.md](README.md). Research date: 2026-10-02.

## Verification legend

Every row says how the main facts were checked. kaggle.com, huggingface.co, arxiv.org, archive.org,
r.jina.ai and most blogs were blocked by the network egress proxy from this environment (see
README, "What could not be verified"). Only web-search result snippets and raw GitHub files could be read.

| Tag | Meaning |
|---|---|
| **[GH]** | Read directly from the cited GitHub file (raw.githubusercontent.com) during this research. Strongest level available here. |
| **[S]** | Taken from a web-search result snippet that points at the cited URL. The page itself could not be opened. Treat as likely but secondary. |
| **UNVERIFIED** | Not confirmed by either route. It may be from memory or only implied, so check it before relying on it. |

Fit ratings refer to the SIT design-review agent (reads a 20-30 page architecture/design PDF, researches,
judges fitness for purpose, lists strengths/risks/gaps/ambiguities, recommends refinements with
issue + rationale + evidence + expected benefit, graded by human evaluators). Uses: (a) external
benchmark / eval data, (b) labelled data for an LLM-as-judge / rubric grader, (c) transferable technique.

---

## 1. Summary table

| # | Candidate | Kind | Year | Task type | Labels | Fit (a/b/c) | Overall |
|---|---|---|---|---|---|---|---|
| K1 | LMSYS - Chatbot Arena Human Preference Predictions | Kaggle comp | 2024 | Pairwise preference (A / B / tie) | Human votes | a: Low, b: Med, c: **High** | **High** |
| K2 | WSDM Cup - Multilingual Chatbot Arena | Kaggle comp | 2024-25 | Pairwise preference (A / B) | Human votes | a: Low, b: Med, c: **High** | **High** |
| K3 | LLMs - You Can't Please Them All | Kaggle comp | 2024-25 | Adversarial attack on LLM-judge panel | None (judge-scored) | a: Low, b: None, c: Med | Medium |
| K4 | Learning Agency Lab - Automated Essay Scoring 2.0 | Kaggle comp | 2024 | Holistic rubric score 1-6 | Expert scores | a: Low, b: Med, c: Med-High | Medium-High |
| K5 | Feedback Prize - Evaluating Student Writing | Kaggle comp | 2021-22 | Span segmentation of argument elements | Expert spans | a: Low, b: Low, c: Med | Medium-Low |
| K6 | Feedback Prize - Predicting Effective Arguments | Kaggle comp | 2022 | Per-element quality (Effective/Adequate/Ineffective) | Expert ratings | a: Low, b: **Med-High**, c: **High** | **High** |
| K7 | Feedback Prize - English Language Learning | Kaggle comp | 2022 | 6 analytic rubric scores | Expert scores | a: Low, b: Low-Med, c: Med | Medium-Low |
| K8 | CommonLit Readability Prize | Kaggle comp | 2021 | Readability regression | Pairwise-derived score + SE | a: None, b: Low, c: Low-Med | Low |
| K9 | CommonLit - Evaluate Student Summaries | Kaggle comp | 2023 | Score summary vs source (content, wording) | Expert scores | a: Low, b: Low-Med, c: Med | Medium |
| K10 | Kaggle - LLM Science Exam | Kaggle comp | 2023 | MCQ answering with retrieval | Answer key | a: None, b: None, c: Med | Medium-Low |
| K11 | Eedi - Mining Misconceptions in Mathematics | Kaggle comp | 2024 | Retrieve + rerank from a taxonomy | Expert tags | a: None, b: None, c: Med | Medium |
| K12 | MAP - Charting Student Math Misunderstandings | Kaggle comp | 2025 | Classify misconception from explanation | Expert tags | a: None, b: None, c: Low-Med | Low |
| K13 | Jigsaw - Agile Community Rules Classification | Kaggle comp | 2025 | Rule-conditioned violation judgement | Moderator labels | a: Low, b: Low, c: Med (UNVERIFIED) | Medium-Low |
| K14 | Google AI4Code | Kaggle comp | 2022 | Order markdown vs code cells | Ground-truth order | None | Low |
| K15 | Learning Agency Lab - PII Data Detection | Kaggle comp | 2024 | Token-level PII NER | Token labels | a: None, b: None, c: Low | Low |
| K16 | LLM - Detect AI Generated Text | Kaggle comp | 2023-24 | Human vs LLM text | Binary | None | Low |
| K17 | Konwinski Prize | Kaggle comp | 2024-25 | Agent resolves GitHub issues (contamination-free) | Hidden tests | a: None, c: Med (eval design) | Low-Medium |
| K18 | Kaggle Community Benchmarks + `kaggle-benchmarks` SDK | Kaggle platform | 2026 | Custom LLM eval tasks with LLM-judge | User-defined | a: **Med (infra)**, c: Med | Medium |
| K19 | Track3: LLM Automatic Data Annotation in Long-Context Scenarios | Kaggle comp (FlagOS) | 2026 | Long-context ICL annotation | Gold annotations | c: Low-Med (UNVERIFIED) | Low |
| K20 | Kaggle Standardized Agent Exams | Kaggle platform | 2026 | 16-question agent exam | Exam key | None | Low |
| D1 | ICLR 2017 Reviews | Kaggle dataset | - | Papers + reviews + decisions | Decisions, scores | a: Med, b: Med | Medium |
| D2 | ICLR papers and reviews data 2018-2023 | Kaggle dataset | - | Papers + reviews | Scores, decisions | a: Med, b: Med | Medium |
| D3 | ASAP-Review (Kaggle mirror) | Kaggle dataset | - | Aspect-tagged peer reviews | 8 aspect tags | b: Med | Medium |
| D4 | PERSUADE 2.0 (Kaggle mirror) | Kaggle dataset | - | Essays + element effectiveness | Expert | b: Med | Medium (see K6) |
| D5 | ELLIPSE corpus (Kaggle mirror) | Kaggle dataset | - | Essays + 6 analytic scores | Expert | b: Low | Low |
| D6 | PURE (Kaggle mirror) | Kaggle dataset | - | Real requirements documents | Mostly unlabelled | a: **Med (realistic input docs)** | Medium |
| D7 | Software requirements dataset (977 rows) | Kaggle dataset | - | FR / NFR classification | FR/NFR type | b: Low | Low |
| D8 | Software requirements (human vs ChatGPT) | Kaggle dataset | - | FR/NFR + author type | Type, author | Low | Low |
| E1 | RevUtil | Non-Kaggle (EMNLP 2025) | 2025 | Review-comment utility scoring | 4 aspects, 3 raters | a: **High**, b: **High** | **High** |
| E2 | ReviewCritique | Non-Kaggle (EMNLP 2024) | 2024 | Detect deficient review segments | Expert deficiency labels + explanations | a: **High** (eval only) | **High** |
| E3 | PeerRead | Non-Kaggle (NAACL 2018) | 2018 | Accept/reject + aspect scores | Decisions, aspect scores | a: Med, b: Med | Medium |
| E4 | NLPeer / NLPEERv2 | Non-Kaggle (ACL 2023) | 2023+ | Papers, reviews, revisions | Scores, links | a: Med, b: Med | Medium |
| E5 | ICLR dataset (berenslab) | Non-Kaggle | 2024-26 | ICLR submissions 2017-2026 | Scores, decisions | Agreement-ceiling reference | Medium |
| E6 | DISAPERE | Non-Kaggle (NAACL 2022) | 2022 | Review/rebuttal discourse | Sentence labels | b: Low-Med | Low-Medium |
| E7 | PRISM | Non-Kaggle (2026) | 2026 | Multi-dimension eval of LLM reviewers | Pipeline-derived | c: Med (rubric design) | Medium |
| E8 | QuRE / Orchid | Non-Kaggle | 2025 | Requirements quality / ambiguity | Expert labels | a: Med (requirements gaps) | Medium-Low |
| E9 | ADR corpora (~4,300 ADRs) | Non-Kaggle (2026) | 2026 | Architecture decision records | Topic/template | a: Low-Med (realistic decisions) | Low-Medium |

---

## 2. Kaggle competitions

### K1. LMSYS - Chatbot Arena Human Preference Predictions
- **URL:** https://www.kaggle.com/competitions/lmsys-chatbot-arena
- **Year:** 2024. Ran until 5 Aug 2024, $100k prize pool, 1,849 teams [S] ([LMSYS blog](https://www.lmsys.org/blog/2024-05-02-kaggle-competition/)). The 4th-place repo also states "1,849 teams" [GH] ([repo](https://github.com/DaoyuanLi2816/Kaggle-4th-Place-Solution-LMSYS-Chatbot-Arena-Human-Preference-Predictions)).
- **Task:** Predict which of two LLM responses a Chatbot Arena user preferred, or a tie [S] ([LMSYS blog](https://www.lmsys.org/blog/2024-05-02-kaggle-competition/)).
- **Data / size:** About 55k real conversations across 70+ LLMs [S] ([HF dataset card, via search](https://huggingface.co/datasets/lmarena-ai/arena-human-preference-55k)). Columns `prompt`, `response_a`, `response_b` (per-turn lists) and one-hot `winner_*` columns [GH] (4th-place README, "Arena-format CSV").
- **Labels:** winner_model_a / winner_model_b / winner_tie (human votes).
- **Metric:** Log-loss. Implied by the 4th-place README ("worth a measurable amount of log-loss") [GH]; official metric page UNVERIFIED.
- **Licence:** Kaggle competition rules UNVERIFIED (page blocked). HF mirror licence UNVERIFIED (HF blocked). The 4th-place code (`pairjudge`) is MIT [GH].
- **Fit:** The domain (chat answers) is far from design review. The task, though, is exactly building a calibrated LLM judge that agrees with humans, which is what our grader needs. Best value is (c), plus some (b) for warm-starting a pairwise grader.
- **Transferable techniques:**
  1. *Swap-debias test-time augmentation:* score each pair in both orders and average. Measure the position flip rate first. A small judge changed its verdict on **29.2 %** of pairs when the order was swapped [GH] (4th-place README).
  2. *Ties as their own class:* scalar Bradley-Terry rewards cannot represent ties [GH].
  3. *Two-phase soft pseudo-labelling:* human labels, then pseudo-label an unlabeled pool with full probability distributions, then retrain with KL [GH].
  4. *Distillation from a large teacher:* 1st place distilled 70B-class models into Gemma-2-9B and averaged LoRA weights across folds. Many teams started from reward models [S] ([X thread by D. Kłeczek](https://x.com/dk21/status/1826292289930674590), [Nebius review](https://nebius.com/blog/posts/chatbot-arena-competition-review)). 1st-place details UNVERIFIED beyond these snippets.
- **Other code:** https://github.com/tascj/kaggle-lmsys-chatbot-arena is a 3-stage training plus pseudo-label pipeline on Gemma-2/Llama-3 [GH]. Its final rank is UNVERIFIED.

### K2. WSDM Cup - Multilingual Chatbot Arena
- **URL:** https://www.kaggle.com/competitions/wsdm-cup-multilingual-chatbot-arena
- **Year:** 18 Nov 2024 to 10 Mar 2025, $50k, 950 teams [S] ([Medium summary](https://medium.com/@ravikshdikola/wsdm-cup-2025-multilingual-chatbot-arena-predicting-human-preferences-in-ai-conversations-e1d82ef435ac), [WSDM page](https://www.wsdm-conference.org/2025/2025-wsdm-cup-lmsys-multilingual-chatbot-arena/)). The 5th-place repo confirms "5th of 950" [GH].
- **Task:** Binary A/B human preference across many languages [GH] ([5th-place repo](https://github.com/datahubber/wsdm-cup-5th-place-llm-judge)).
- **Data / size:** 48,439 labelled train pairs [GH] (5th-place README). It covers 128 languages, mostly English [S] (Medium summary).
- **Metric:** Accuracy. The 5th-place README reports public/private LB as accuracy, "one row is 0.0001 accuracy" [GH].
- **Licence:** Competition rules UNVERIFIED. The 5th-place code is MIT [GH].
- **Fit:** Same as K1, with stronger and better-documented judge-engineering techniques.
- **Transferable techniques:**
  1. *1st place* ([repo](https://github.com/maxreciprocate/kaggle-lmarena-1st-place) [GH]): stage 1 pretraining, stage 2 teacher training, stage 3 distillation into a student, then merging the students. The README lists datasets such as `lmarena-ai/gpt-4o-mini_battles`. Per the writeup snippet, the student is Qwen2.5-14B, the teacher is Qwen2.5-72B, and over-long inputs are truncated proportionally from the middle [S] ([writeup](https://www.kaggle.com/competitions/wsdm-cup-multilingual-chatbot-arena/writeups/whitefebruary-1st-place-solution)).
  2. *5th place* [GH]:
     - **Single-token judgement with a calibrated log-prob margin.** The judge answers "A" or "B", and the margin is m = log p(A) - log p(B), so P(A) = sigmoid(m).
     - **Head+tail truncation** with a fixed budget split: 15 % + 5 % for the query and 30 % + 10 % for each response, because "readers look at the start and the end".
     - **Uncertainty-gated tie-break.** A heuristic is used only when |m| < τ. It helped a weak judge and was neutral on a strong one.
     - **Bias finding.** "Longer response wins" alone is right **58.4 %** of the time on 48,439 pairs. This is a verbosity bias that a reward model should *not* learn, and length-matched pairs or a length penalty are the recommended controls.
  3. The rubric used in the 5th-place system prompt is public (Apache-2.0, from a public Kaggle notebook) [GH] ([prompt.py](https://github.com/datahubber/wsdm-cup-5th-place-llm-judge/blob/main/src/wsdm_judge/prompt.py)). Its criteria are completeness, accuracy, clarity, conciseness vs detail, examples, tone, reasoning and format.

### K3. LLMs - You Can't Please Them All
- **URL:** https://www.kaggle.com/competitions/llms-you-cant-please-them-all
- **Year:** 3 Dec 2024 to 4 Mar 2025, $50k, 1,692 teams [S] ([overview](https://www.kaggle.com/competitions/llms-you-cant-please-them-all/overview/description), [Kaggle on X](https://x.com/kaggle/status/1864063969985524008)).
- **Task:** Submit ~100-word essays on given topics that **maximise disagreement among three LLM judges**, which score 0-9. Scoring uses horizontal (between-judge) and vertical (within-judge) variance [S].
- **Data:** Essay topics only. No labelled quality data [S].
- **Licence:** UNVERIFIED.
- **Fit:** No training data. Its value is as a **threat model for our own LLM grader**: if grader judges can be pushed apart or inflated by surface features, a high grader score means little.
- **Transferable technique:** Use a red-team checklist on the grader: trigger words and jargon, sentence-length manipulation, odd formatting, contradictions, fabricated citations, tone switching, deliberate ambiguity. These come from a community repo, **not** a winning solution [GH] ([zixi-liu repo](https://github.com/zixi-liu/LLMs-You-Cant-Please-Them-All)). Winning solutions are UNVERIFIED. No public writeup could be read.

### K4. Learning Agency Lab - Automated Essay Scoring 2.0
- **URL:** https://www.kaggle.com/competitions/learning-agency-lab-automated-essay-scoring-2
- **Year:** 2024, concluded 3 July, 2,700+ teams [S] ([competition report](https://hippocampus-garden.com/kaggle_aes2/)).
- **Task:** Holistic essay score 1-6. Metric is quadratic weighted kappa (QWK) [S] (same report).
- **Data / size:** About 17k training essays: ~13k from PERSUADE 2.0 and ~4k "Kaggle-only" essays [S] (same report). Released as ASAP 2.0 [S] ([Learning Agency Lab page](https://the-learning-agency-lab.com/learning-exchange/asap-2-0-dataset/)).
- **Licence:** UNVERIFIED (host page blocked).
- **Fit:** Wrong domain (student essays). The *methodology* fits our grader: an ordinal rubric score, agreement with human raters measured by QWK, and two label sources graded by different standards.
- **Transferable technique (1st place)** [S] (same report). The winner rose from **619th public to 1st private** by spotting that the two data sources had different grading criteria. The recipe:
  1. Pretrain on PERSUADE, then fine-tune on the Kaggle-only set.
  2. Re-label PERSUADE with a Kaggle-only model.
  3. Average 4 DeBERTa-v3-large variants, with thresholds tuned per model and then averaged to avoid overfitting.

  Lesson for us: **check whether our grader's rubric and the SIT evaluators' implicit rubric differ before optimising against the grader.** The huge leaderboard shake-up is also a warning about over-fitting to a small public set.

### K5. Feedback Prize - Evaluating Student Writing (FP1)
- **URL:** https://www.kaggle.com/c/feedback-prize-2021
- **Year:** 2021-22. Exact dates are UNVERIFIED.
- **Task:** Segment essays into argumentative and rhetorical elements and classify them (Lead, Position, Claim, Counterclaim, Rebuttal, Evidence, Concluding Statement). Data is PERSUADE 1.0 [S] ([PERSUADE 1.0 paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9767095/)). Metric (overlap-based F1) is UNVERIFIED.
- **Licence:** UNVERIFIED for the Kaggle copy. PERSUADE 2.0 superset is CC BY-NC-SA 4.0 [GH] (see D4).
- **Fit:** Low as data. Medium as a technique for **long-document span extraction**, comparable to pulling requirements, decisions and assumptions out of a design PDF. Modern LLM extraction largely replaces it.
- **Transferable technique:** Token-level BIO tagging (sliding windows, or Longformer for long inputs), then a **second-stage span/sentence classifier** (LightGBM over token predictions) [S] ([discussion](https://www.kaggle.com/c/feedback-prize-2021/discussion/313177)). Code: [2nd place](https://github.com/ubamba98/feedback-prize) [S], [tascj](https://github.com/tascj/kaggle-feedback-prize-2021) [S].

### K6. Feedback Prize - Predicting Effective Arguments (FP2)
- **URL:** https://www.kaggle.com/competitions/feedback-prize-effectiveness
- **Year:** 2022 [GH] (1st-place repo links the competition). Exact dates are UNVERIFIED.
- **Task:** Rate each discourse element (Lead, Position, Claim, Counterclaim, Rebuttal, Evidence, Concluding Statement) as **Ineffective / Adequate / Effective** [S] ([arXiv 2502.14389](https://arxiv.org/pdf/2502.14389), [complete overview notebook](https://www.kaggle.com/code/lextoumbourou/feedback-prize-the-complete-overview)).
- **Data:** Grade 6-12 argumentative essays [S]. The fuller release is PERSUADE 2.0: 25,996 essays, 15 prompts, double-blind rating with 100 % adjudication [S] ([PERSUADE 2.0 paper](https://www.sciencedirect.com/science/article/pii/S1075293524000588)). It has "over 25,000" essays plus effectiveness scores per element [GH] ([PERSUADE 2.0 repo](https://github.com/scrosseye/persuade_corpus_2.0)).
- **Licence:** PERSUADE 2.0 is **CC BY-NC-SA 4.0** [GH]. The Kaggle competition copy is UNVERIFIED.
- **Fit:** The **closest Kaggle analogue to judging the quality of claims and evidence**, though about student essays, not design reviews. Our required output structure (issue → rationale → evidence → benefit) maps to Claim → Evidence → effectiveness. Useful for (b), as an auxiliary or pre-training signal for a "does this finding's evidence support its claim?" sub-judge, and for (c).
- **Transferable technique (1st place, Team Hydrogen):**
  - Score **all discourse elements of one essay together in a single pass**, with markers, instead of one element at a time. This was faster and "improved accuracy significantly".
  - Multiple rounds of pseudo-labelling, then second-level stacking models. Only deberta-(v3)-large worked as a backbone.
  - Near-perfect CV/LB correlation.

  Sources: [S] ([writeup](https://www.kaggle.com/competitions/feedback-prize-effectiveness/writeups/team-hydrogen-team-hydrogen-1st-place-solution)). The two-stage structure and a separate **efficiency-prize** model are confirmed [GH] ([repo](https://github.com/ybabakhin/kaggle-feedback-effectiveness-1st-place-solution)).

  For us, the analogue is to grade all findings of a review in one prompt with the design-doc context, so the grader can see duplicates, contradictions and relative importance.

### K7. Feedback Prize - English Language Learning (FP3)
- **URL:** https://www.kaggle.com/competitions/feedback-prize-english-language-learning
- **Year:** 2022 [GH] (1st-place repo).
- **Task:** Six analytic scores (cohesion, syntax, vocabulary, phraseology, grammar, conventions), 1.0-5.0 in 0.5 steps. ELLIPSE corpus of grade 8-12 English-learner essays, each double-rated [S] ([ELLIPSE paper](https://www.researchgate.net/publication/378094468_The_English_Language_Learner_Insight_Proficiency_and_Skills_Evaluation_ELLIPSE_Corpus)). Metric (MCRMSE) is UNVERIFIED.
- **Licence:** UNVERIFIED.
- **Fit:** Low. Linguistic proficiency is not design quality. The only relevance is as a multi-criterion analytic rubric.
- **Transferable technique (1st place)** [GH] ([repo](https://github.com/rohitsingh02/kaggle-feedback-english-language-learning-1st-place-solution)): an iterative loop. Pretrain on pseudo labels, fine-tune on true labels, regenerate pseudo labels from a weighted ensemble, and repeat. It also uses **column-wise** (per-criterion) ensemble weights, which supports calibrating each rubric criterion separately.

### K8. CommonLit Readability Prize
- **URL:** https://www.kaggle.com/c/commonlitreadabilityprize
- **Year:** 2021. Uses the CLEAR corpus (~5k excerpts) [S] ([CommonLit blog](https://www.commonlit.org/blog/introducing-the-clear-corpus-an-open-dataset-to-advance-research-28ff8cfea84a/)).
- **Task / labels:** Readability score with a per-item standard error [S].
- **Fit:** Low. Readability is not what SIT grades.
- **Transferable technique (1st place)** [S] ([discussion](https://www.kaggle.com/c/commonlitreadabilityprize/discussion/257844)), with the repo confirmed [GH] ([repo](https://github.com/mathislucka/kaggle_clrp_1st_place_solution)):
  - Use sentence-BERT to retrieve 5 similar external snippets per item, then pseudo-label them.
  - **Discard pseudo labels that deviate from the source item by more than that item's label standard error.** This is a clean way to use rater uncertainty when expanding a small labelled set.

### K9. CommonLit - Evaluate Student Summaries
- **URL:** https://www.kaggle.com/competitions/commonlit-evaluate-student-summaries
- **Year:** Jul-Oct 2023, 2,000+ teams [S] ([LinkedIn recap](https://www.linkedin.com/pulse/our-kaggle-winning-solution-recap-commonlit-evaluate-ivan-isaev--a4bgf)).
- **Task:** Score a student summary **against its source text** on content and wording. Metric is MCRMSE. Data is the CLASSE corpus [S] ([CLASSE paper](https://aclanthology.org/2024.bea-1.9.pdf), [Zenodo](https://zenodo.org/records/11121837)).
- **Licence:** UNVERIFIED.
- **Fit:** Medium-low. It is structurally like scoring whether a review faithfully represents the design document. The data is the wrong domain.
- **Transferable technique:** Top solutions fed the **source/prompt text alongside the summary** (special tokens instead of [SEP]), with custom pooling and a second-stage stacker [S] ([8th-place writeup](https://www.kaggle.com/competitions/commonlit-evaluate-student-summaries/writeups/adam-montgomerie-8th-place-solution), [Japanese summary](https://zenn.dev/chiman/articles/246b309925e65d)). The 1st-place specifics are UNVERIFIED.

### K10. Kaggle - LLM Science Exam
- **URL:** https://www.kaggle.com/c/kaggle-llm-science-exam
- **Year:** 11 Jul to 10 Oct 2023. 200 training MCQs, MAP@3, 2,600+ teams [S] ([competition report](https://hippocampus-garden.com/kaggle_llm/)).
- **Fit:** Low as data. Medium as a technique for **evidence retrieval before judgement**.
- **Transferable technique (1st, H2O LLM Studio)** [S] ([writeup](https://www.kaggle.com/competitions/kaggle-llm-science-exam/writeups/team-h2o-llm-studio-1st-place-solution)):
  - Ensemble retrieval from all of Wikipedia with several embedders (e5, gte, bge). Filtering to science pages did not help, because the embedders were robust to irrelevant pages.
  - Score each answer option with retrieved context as a binary "is this correct?" classifier (7-13B LoRA).
  - For us: retrieve evidence per claim with multiple retrievers, then judge each claim separately.

### K11. Eedi - Mining Misconceptions in Mathematics
- **URL:** https://www.kaggle.com/competitions/eedi-mining-misconceptions-in-mathematics
- **Year:** 2024. Metric MAP@25 [S].
- **Fit:** Medium as a technique, none as data. The task is to map an observed error onto a fixed taxonomy. For us that means mapping a design weakness onto a catalogue (ISO/IEC 25010 quality attributes, a cloud well-architected pillar, an OWASP or NIST control) so that evidence and standards are cited consistently.
- **Transferable technique (1st place)** [S] ([discussion](https://www.kaggle.com/competitions/eedi-mining-misconceptions-in-mathematics/discussion/551402)):
  - Retriever ensemble (e5-mistral-7b, bge-en-icl, Qwen2.5-14B) to get the top 32-64 candidates with dynamic thresholds.
  - Rerank in a **cascade**: 14B pointwise to top 8, 32B pointwise to top 5, then 72B **listwise** over 5.
  - Train on ~1.8k real plus ~10k synthetic examples.

### K12. MAP - Charting Student Math Misunderstandings
- **URL:** https://www.kaggle.com/competitions/map-charting-student-math-misunderstandings
- **Year:** 10 Jul to 15 Oct 2025 [S] ([X, Kaggle](https://x.com/kaggle/status/1945989392583348654)).
- **Fit:** Low.
- **Transferable technique (1st place)** [S] ([writeup](https://www.kaggle.com/competitions/map-charting-student-math-misunderstandings/writeups/1st-place-solution)): single-seed validation scores were "highly unstable and misleading", while **multi-seed ensembles gave trustworthy validation**. This applies directly to our small hand-built eval set: report variance across repeated runs or seeds, not single numbers.

### K13. Jigsaw - Agile Community Rules Classification
- **URL:** https://www.kaggle.com/competitions/jigsaw-agile-community-rules
- **Year:** 23 Jul to 23 Oct 2025, $100k, 2,445 teams [S] ([Kaggle on X](https://x.com/kaggle/status/1948080444655960134), [DOCOMO press release](https://www.docomo.ne.jp/english/info/media_center/pr/2025/1121_00.html)). Column-averaged AUC. Winner listed as Guanshuo Xu with about 0.93 [S] ([CLIST standings](https://clist.by/standings/jigsaw-agile-community-rules-classification-classification-text-social-networks-text-classification-english-custom-metric-60943373/)).
- **Task:** Predict whether a Reddit comment violates a **given rule text** [S].
- **Fit:** Medium in concept: "does this artefact violate this stated principle?" is the shape of a principle-by-principle design check. Low in domain. The exact data fields (for example, per-rule positive and negative examples) are UNVERIFIED, and **no winning technique could be verified**.

### K14. Google AI4Code - Understand Code in Python Notebooks
- **URL:** https://www.kaggle.com/competitions/AI4Code
- **Year:** 2022 [GH] ([2nd-place README](https://github.com/pdima/kaggle_ai4code_solution/blob/main/Readme.md)).
- **Task:** Reconstruct the order of markdown cells relative to code cells [GH].
- **Fit:** Low. The 2nd-place idea of encoding each cell separately and cross-attending code and markdown [GH] is a document-structure technique made largely obsolete by long-context LLMs.

### K15. The Learning Agency Lab - PII Data Detection
- **URL:** https://www.kaggle.com/competitions/pii-detection-removal-from-educational-data
- **Year:** 2024. About 22k student essays, micro F-beta with beta = 5 (recall-weighted) [S] ([PIILO dataset](https://www.kaggle.com/datasets/lburleigh/piilo-dataset)).
- **Fit:** Low. Marginal use: scrubbing names and identifiers from an internal SIT design document before sending excerpts to external search tools.
- **Technique (1st place)** [GH] ([repo](https://github.com/bogoconic1/pii-detection-1st-place)): 5 DeBERTa-v3-large variants (multi-sample dropout, BiLSTM head), knowledge distillation, and name-swap augmentation.

### K16. LLM - Detect AI Generated Text
- **URL:** https://www.kaggle.com/competitions/llm-detect-ai-generated-text
- **Fit:** None for our task. Listed only because it shows up in searches. 1st-place code: https://github.com/rbiswasfc/llm-detect-ai [S] (README fetched [GH]).

### K17. Konwinski Prize
- **URL:** https://www.kaggle.com/competitions/konwinski-prize
- **Year:** Launched Dec 2024. First-round results in July 2025: the winner scored **7.5 %** using an off-the-shelf open model with prompt and pipeline engineering [S] ([TechCrunch](https://techcrunch.com/2025/07/23/a-new-ai-coding-challenge-just-published-its-first-results-and-they-arent-pretty/)).
- **Task:** Offline agent resolves real GitHub issues. The test set is **collected after the submission deadline**, so it is contamination-free [S] ([strategy guide](https://github.com/raymyers/konwinski-prize-strategy-guide)).
- **Fit:** Low as data. Its value is in evaluation design: freeze the agent, then evaluate on artefacts written afterwards. That is what our `eval/blind/` set and the SIT demo-day "new design artefact" do.

### K18. Kaggle Community Benchmarks and the `kaggle-benchmarks` SDK
- **URLs:** https://github.com/Kaggle/kaggle-benchmarks and https://www.kaggle.com/benchmarks
- **Year:** Community Benchmarks launched Jan 2026 [S] ([Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/kaggle-community-benchmarks/)).
- **What it is** [GH]: a Python library for defining eval tasks with `@kbench.task`. It supports structured (pydantic) outputs, tool use, multi-turn conversations and dataset-level runs, and produces Kaggle leaderboards. Licence is **Apache-2.0**. Its built-in LLM-as-judge assertion (`assess_response_with_judge`) is reported only via search [S] (same Google blog).
- **Fit:** Medium, as **infrastructure** for (a). We could publish our design-review eval (synthetic artefacts with sealed answer keys) as a reproducible Kaggle benchmark. It is not a source of data.

### K19. Track3: LLM Automatic Data Annotation in Long-Context Scenarios
- **URL:** https://www.kaggle.com/competitions/track-3-llm-automatic-data-annotation-in-long-context-scenarios
- **Year:** 20 Jan to 20 May 2026. 8 datasets, long-context in-context learning (FlagOS challenge) [S].
- **Fit:** Low-medium, UNVERIFIED. It is the only 2026 Kaggle competition found that explicitly targets ultra-long-context LLM reasoning. No solutions could be read.

### K20. Kaggle Standardized Agent Exams
- **URL:** https://www.kaggle.com/blog/standardized-agent-exams
- **Year:** 2026 [S]. A 16-question reasoning and adversarial-safety exam for agents.
- **Fit:** Low. Generic, and not about document review.

**Searched, not found:** No Kaggle competition was found on **scientific peer review, design or architecture review, requirements quality, or technical-document QA**. Searches: [peer review](https://arxiv.org/pdf/2511.06304) (search returned only surveys), plus the queries listed in the README. The absence is a search result, not a proof.

---

## 3. Kaggle datasets (community uploads)

All of these are community mirrors whose Kaggle pages could not be opened, so the licence on Kaggle is **UNVERIFIED**. Prefer the original source where one is given.

| ID | Dataset | Kaggle URL | Contents | Original / licence | Fit |
|---|---|---|---|---|---|
| D1 | ICLR 2017 Reviews | https://www.kaggle.com/datasets/ahmaurya/iclr2017reviews | ICLR 2017 titles, abstracts, reviews, 4-way decisions [S] | OpenReview; licence UNVERIFIED | Medium: real expert critiques with outcomes |
| D2 | ICLR papers and reviews data 2018-2023 | https://www.kaggle.com/datasets/juanjomontero/iclr-papers-and-reviews-data-2018-2023 | Links, papers, reviews 2018-2023 [S] | OpenReview; UNVERIFIED | Medium |
| D3 | ASAP-Review | https://www.kaggle.com/datasets/jonauskis/asap-review | 28,119 ICLR 2017-20 and NeurIPS 2016-19 reviews. 8 aspects: Summary, Motivation, Originality, Soundness, Substance, Replicability, Meaningful Comparison, Clarity [S] ([paper](https://arxiv.org/pdf/2102.00176)) | https://github.com/neulab/ReviewAdvisor, **Apache-2.0** [GH] | Medium: aspect taxonomy close to design-review dimensions |
| D4 | PERSUADE corpus 2.0 | https://www.kaggle.com/datasets/nbroad/persaude-corpus-2 | See K6 | https://github.com/scrosseye/persuade_corpus_2.0, **CC BY-NC-SA 4.0** [GH] | Medium (claim/evidence quality) |
| D5 | ELLIPSE corpus | https://www.kaggle.com/datasets/mpware/ellipse-corpus | See K7 | [learlab.org/data](https://learlab.org/data/) [S] | Low |
| D6 | PUblic REquirements (PURE) | https://www.kaggle.com/datasets/computerscience3/public-requirementspure-dataset | 79 public natural-language requirements documents, 34,268 sentences [S] ([Ferrari et al.](https://www.semanticscholar.org/paper/PURE:-A-Dataset-of-Public-Requirements-Documents-Ferrari-Spagnolo/a843e41d3658f4aa695406d916a516fc77c04e79)) | https://nlreqdataset.isti.cnr.it/ [S]; licence UNVERIFIED | **Medium for (a):** realistic multi-page specs to seed synthetic design-review test inputs with planted flaws |
| D7 | Software requirements dataset | https://www.kaggle.com/datasets/iamvaibhav100/software-requirements-dataset | 977 rows, Type + Requirement (FR/NFR subtypes) [S] | Derived from PROMISE-style sets [S] ([Zenodo](https://zenodo.org/records/15082900)) | Low: sentence-level classification only |
| D8 | Software requirements (human vs ChatGPT) | https://www.kaggle.com/datasets/goktuggelmis/software-requirements/data | Scenario, Requirement, Type, Author (human/ChatGPT) [S] | UNVERIFIED | Low |

---

## 4. Adjacent non-Kaggle resources

These were found because Kaggle has no peer- or design-review competition. They are the strongest **domain** fits.

### E1. RevUtil: "The Good, the Bad and the Constructive" (EMNLP 2025)
- **URL:** https://github.com/bodasadallah/RevUtil, [paper](https://aclanthology.org/2025.emnlp-main.1476/)
- **Contents** [GH]: **1,430 human-labelled review comments** (three annotators each, with majority label) and **10,000 synthetically labelled comments with rationales**. Aspects: **Actionability, Grounding & Specificity, Verifiability, Helpfulness**, on a 5-point scale (Verifiability adds a binary claim flag [S]). Fine-tuned Llama-3.1-8B scorers are released, and they match or exceed GPT-4o agreement with humans.
- **Licence:** CC BY-NC-SA 4.0 [GH] (badge in README).
- **Fit: High for (a) and (b).** The four aspects line up almost one-to-one with SIT §2.3 ("issue, rationale, supporting evidence and expected benefit"): Grounding is the issue anchored to the doc, Verifiability is the evidence, Actionability is the refinement, and Helpfulness is the benefit. Use the rubric directly in our grader, and use the human split to measure grader-human agreement on critique text.

### E2. ReviewCritique (EMNLP 2024)
- **URL:** https://github.com/jiangshdd/ReviewCritique
- **Contents** [GH]: 100 NLP papers (initial submissions) with human reviews, plus 20 papers with LLM-generated reviews. Experts labelled each review segment as "Deficient" or not, with an explanation. Deficient means a factual error, a misinterpretation, or no constructive feedback [S].
- **Finding** [S]: 13.97 % of LLM-review sentences were deficient, against 6.27 % for human reviews ([paper](https://aclanthology.org/2024.emnlp-main.292.pdf)).
- **Licence:** **Research only; must not be used to train models** [GH].
- **Fit: High for (a), eval-only.** It is the best available benchmark for our agent's **self-verification step** (catching its own factually wrong or non-constructive findings) and for checking whether our grader can spot deficient critique.

### E3. PeerRead (NAACL 2018)
- **URL:** https://github.com/allenai/PeerRead
- **Contents:** Over 14K paper drafts with accept/reject decisions (ACL, NIPS, ICLR) and over 10K expert reviews [GH]. ICLR 2017 has 427 papers and 1,304 reviews, with aspect scores such as clarity, originality and substance [S] ([paper](https://aclanthology.org/N18-1149.pdf)).
- **Licence:** Mixed. Some sections must be downloaded separately "due to licensing constraints" [GH].
- **Fit:** Medium. It is the classic baseline, but its accept/reject prediction is not our task.

### E4. NLPeer / NLPEERv2 (ACL 2023)
- **URL:** https://github.com/UKPLab/nlpeer
- **Contents:** More than 5k papers and 11k reviews from 5 venues, ethically sourced under CC licences [S] ([paper](https://aclanthology.org/2023.acl-long.277/)). v2 adds a contamination-free ARR-EMNLP-2024 set and includes paper PDFs and revisions [GH]. v2 is CC BY-NC 4.0 [S].
- **Fit:** Medium. It is the cleanest-licensed source of full paper + review pairs. Paper revisions mirror the SIT "updated design artefact" re-review scenario.

### E5. ICLR dataset (berenslab)
- **URL:** https://github.com/berenslab/iclr-dataset
- **Contents** [GH]: 55,906 ICLR submissions from 2017-2026, with reviewer scores and decisions. **The correlation between two reviewers' scores of the same paper is 0.40** (24v2 statistics).
- **Fit:** A reference point. Expert reviewers of the *same* document agree only moderately, so an LLM grader that "only" reaches moderate agreement with SIT evaluators may be at the human ceiling. Measure inter-human agreement before chasing grader accuracy.

### E6. DISAPERE (NAACL 2022)
- **URL:** https://aclanthology.org/2022.naacl-main.89/
- **Contents:** 20k sentences in 506 review-rebuttal pairs. Each sentence is labelled for review-action, aspect and polarity, with rebuttal links [S].
- **Fit:** Low-medium. It provides a taxonomy of critique actions (request, evaluative, fact, ...) for structuring findings.

### E7. PRISM (2026)
- **URL:** https://arxiv.org/abs/2605.26730, https://prism-benchmark.github.io/
- **Contents:** Evaluates LLM and human reviews on depth of analysis, novelty assessment, flaw identification and prioritisation, and constructiveness. It uses argument mining, retrieval-augmented verification and consensus scoring over 1,000 papers [S].
- **Fit:** Medium for (c). Its "flaw identification **and prioritisation**" and "retrieval-augmented verification" dimensions are rubric ideas for our grader. Data availability is UNVERIFIED.

### E8. Requirements-quality sets
- **QuRE:** 1,266 annotated Mercedes-Benz requirements (RE'25 workshop) [S].
- **Orchid:** 1,304 tasks with lexical, syntactic, semantic or vagueness ambiguity [S].
- Source: [search summary pointing to arXiv 2604.21505](https://arxiv.org/html/2604.21505v1). For LLM requirements-quality benchmarking, see [arXiv 2609.03230](https://arxiv.org/pdf/2609.03230) [S].
- **Fit:** Medium-low. Useful for testing the "ambiguity" part of our output on requirement sentences. These are not full design documents.

### E9. Architecture Decision Record corpora
- About 4,300 ADRs from about 550 open-source repositories, analysed for concerns, quality attributes and MADR-template compliance [S] ([arXiv 2609.07375](https://arxiv.org/abs/2609.07375)).
- LLM detection of architectural-decision violations [S] ([arXiv 2602.07609](https://arxiv.org/html/2602.07609v1)).
- **Fit:** Low-medium. These are realistic "decision + rationale" texts for seeding synthetic test artefacts. Data access is UNVERIFIED.
