# Kaggle competitions and datasets for a document-review / critique agent

A self-contained research note on which Kaggle competitions and datasets, plus a few adjacent
non-Kaggle resources, can serve as:

- (a) external benchmarks or evaluation data for a document-review agent,
- (b) labelled data for an LLM-as-judge or rubric grader,
- (c) sources of proven techniques.

Research date: 2026-10-02. Full per-candidate records with sources: [candidates.md](candidates.md).

**Project it was written for:** the SIT AI Engineering Lab Exercise (Sept 2026). The agent reads a
technical design artefact (PDF), "assess[es] whether the design is fit for purpose, identif[ies] strengths,
risks and gaps, and recommend[s] refinements only when supported by evidence". For every refinement it must
"state the issue, rationale, supporting evidence and expected benefit", and it is evaluated by humans
(assignment PDF §1.2, §2.3, §5.4). Nothing below depends on that project except the "Use in this project" notes.

## Verification legend

- **[GH]**: read directly from the GitHub file during this research.
- **[S]**: taken from a web-search snippet pointing at the cited URL. The page itself was blocked.
- **UNVERIFIED**: not confirmed.

## TL;DR

1. **No Kaggle competition has ever targeted peer review, design or architecture review, requirements quality, or
   technical-document QA**, as far as searches could find (see "Searched, not found" at the end of candidates.md §2).
   Kaggle's value for this problem is **techniques, not domain data**.
2. The most transferable Kaggle family is **human-preference prediction for LLM outputs**
   ([LMSYS Chatbot Arena 2024](https://www.kaggle.com/competitions/lmsys-chatbot-arena),
   [WSDM Cup 2025](https://www.kaggle.com/competitions/wsdm-cup-multilingual-chatbot-arena)). These are, in effect,
   competitions in building an LLM judge that agrees with humans. Their top solutions have public, readable code
   covering position-bias debiasing, verbosity bias, log-prob calibration, truncation and distillation.
3. The best Kaggle data for **claim and evidence quality** is
   [Feedback Prize - Predicting Effective Arguments](https://www.kaggle.com/competitions/feedback-prize-effectiveness)
   and its open superset [PERSUADE 2.0](https://github.com/scrosseye/persuade_corpus_2.0) (CC BY-NC-SA 4.0 [GH]).
   It has expert Effective / Adequate / Ineffective ratings for Claims, Evidence, Counterclaims and Rebuttals,
   but in grade 6-12 essays.
4. The best **domain** data is not on Kaggle. It is peer-review critique data:
   [RevUtil](https://github.com/bodasadallah/RevUtil) has 1,430 human-rated review comments on
   **Actionability, Grounding & Specificity, Verifiability, Helpfulness** [GH], which line up almost one-to-one with
   SIT's "issue, rationale, evidence, benefit". [ReviewCritique](https://github.com/jiangshdd/ReviewCritique) has
   expert "deficient segment" labels, but it is eval-only and training is forbidden [GH].
5. Inter-reviewer agreement among human experts is modest: two ICLR reviewers' scores correlate at **0.40** [GH]
   ([berenslab ICLR dataset](https://github.com/berenslab/iclr-dataset)). Measure the human ceiling before
   optimising a grader.

## Ranked top 5

Ranking criteria, in order:

1. How directly the item improves an LLM grader or review agent whose output is judged by humans.
2. Whether the evidence could be checked first-hand ([GH] beats [S]).
3. Licence usability.
4. Effort to reuse.

| Rank | Item | Kind | Use | Why it ranks here |
|---|---|---|---|---|
| **1** | **Chatbot Arena preference competitions**, [LMSYS 2024](https://www.kaggle.com/competitions/lmsys-chatbot-arena) and [WSDM Cup 2025](https://www.kaggle.com/competitions/wsdm-cup-multilingual-chatbot-arena), treated as one family | Kaggle competitions | (c) mainly, some (b) | See "Why each ranks where it does" below. |
| **2** | **[RevUtil](https://github.com/bodasadallah/RevUtil)** (EMNLP 2025) | Non-Kaggle dataset + rubric + models | (a) + (b) | See below. |
| **3** | **[Feedback Prize - Predicting Effective Arguments](https://www.kaggle.com/competitions/feedback-prize-effectiveness)** + **[PERSUADE 2.0](https://github.com/scrosseye/persuade_corpus_2.0)** | Kaggle competition + open corpus | (b) + (c) | See below. |
| **4** | **[ReviewCritique](https://github.com/jiangshdd/ReviewCritique)** (EMNLP 2024) | Non-Kaggle eval set | (a) only | See below. |
| **5** | **[Learning Agency Lab - Automated Essay Scoring 2.0](https://www.kaggle.com/competitions/learning-agency-lab-automated-essay-scoring-2)** (URL slug UNVERIFIED) | Kaggle competition | (c) methodology | See below. |

### Why each ranks where it does

**1. Chatbot Arena preference competitions.** They are the only Kaggle competitions whose explicit objective is
"make an LLM judge agree with human raters". Top-solution code is public and was read first-hand.

- The 4th-place repo [GH] shows swap-debias (score A/B both ways and average). Its small judge flipped its verdict
  on **29.2 %** of pairs when the order changed, and the repo also models ties as their own class.
- The WSDM 5th-place repo [GH] shows a single-token verdict with a log-prob margin, head+tail truncation, and a
  measured verbosity bias ("longer wins" alone gets **58.4 %**).
- The WSDM 1st-place repo [GH] shows a large-teacher to small-student distillation recipe.
- Weak point: the domain is chat answers, not design reviews.

**2. RevUtil.** It is the closest public rubric to the SIT required output. It has three-rater human labels,
10k synthetic labels with rationales, and released 8B scorer models. Licence is CC BY-NC-SA 4.0 [GH].

- Weak point: its labels are about scientific-paper review comments, not architecture reviews.
- It ranks below #1 only because it is not a Kaggle item and gives fewer engineering techniques.

**3. Feedback Prize (Effectiveness) + PERSUADE 2.0.** It is the only Kaggle dataset with expert **quality**
labels on individual Claims, Evidence, Counterclaims and Rebuttals. That is structurally our
"finding + evidence + rationale" judging problem. It was double-blind rated with full adjudication [S]
([paper](https://www.sciencedirect.com/science/article/pii/S1075293524000588)).

- The 1st-place insight transfers directly: score all elements of one document jointly in a single pass, which
  improved accuracy "significantly" [S].
- Weak point: student essays. The domain gap is large.

**4. ReviewCritique.** It is the best benchmark for "can the reviewer (or grader) catch a factually wrong,
misinterpreting or non-constructive critique point?", which is what our agent's self-verification must do.
LLM reviews had 13.97 % deficient sentences against 6.27 % for humans [S].

- Weak point: research-only, **no training allowed** [GH], and only 100 + 20 papers.

**5. Automated Essay Scoring 2.0.** It provides the methodology for an ordinal rubric grader: QWK as the agreement
metric, and the 1st-place lesson that **two label sources graded to different standards** must be detected and
reconciled. The winner went from 619th public to 1st private [S]. That is a direct warning for an LLM grader vs
SIT evaluators.

- Weak point: none of the data is usable for our domain.

**Honourable mentions (not top 5):**

- [LLMs - You Can't Please Them All](https://www.kaggle.com/competitions/llms-you-cant-please-them-all): a Kaggle
  competition on *attacking* an LLM-judge panel. It is a good threat model for our grader, but no labelled data
  exists and no winning writeup could be read.
- [Eedi](https://www.kaggle.com/competitions/eedi-mining-misconceptions-in-mathematics): a retrieve then cascade-rerank
  pattern for mapping findings onto a standards or risk taxonomy [S].
- [kaggle-benchmarks SDK](https://github.com/Kaggle/kaggle-benchmarks) (Apache-2.0 [GH]): infrastructure to publish
  our eval as a reproducible Kaggle benchmark.
- [MAP 2025](https://www.kaggle.com/competitions/map-charting-student-math-misunderstandings): multi-seed validation for
  small, noisy eval sets [S].
- [PURE](https://www.kaggle.com/datasets/computerscience3/public-requirementspure-dataset): 79 real requirements
  documents, usable as seed inputs for synthetic test artefacts [S].

**Explicitly low fit** (checked and rejected; reasons in candidates.md):

- CommonLit Readability
- AI4Code
- PII Data Detection
- LLM Detect AI Generated Text
- Feedback Prize ELL
- LLM Science Exam (as data)
- Konwinski Prize (as data)
- Kaggle Standardized Agent Exams

## Recommendations: how to reuse this in a design-review agent and grader

These are concrete, evidence-backed practices, each traceable to a source above.

1. **Grader rubric.** Score every recommendation the agent makes on RevUtil-style dimensions, mapped to SIT §2.3:

   | SIT element | RevUtil-style dimension |
   |---|---|
   | Issue | Grounding & Specificity: is it anchored to a section or requirement of the design document? |
   | Evidence | Verifiability: is the claim supported by a cited source or by reasoning? |
   | Refinement | Actionability: is the change concrete? |
   | Expected benefit | Helpfulness: does it serve the stated objectives? |

   Add a separate **deficiency check** in the spirit of ReviewCritique: flag findings that misstate the document or
   are not constructive. Sources: [RevUtil](https://github.com/bodasadallah/RevUtil),
   [ReviewCritique](https://github.com/jiangshdd/ReviewCritique).
2. **Judge everything in one pass, with the document.** Present all findings of a review together, each with an ID
   marker, alongside the design-document context. Do not grade findings in isolation. This lets the grader penalise
   duplicates and contradictions. Source: FP2 1st place [S]
   ([writeup](https://www.kaggle.com/competitions/feedback-prize-effectiveness/writeups/team-hydrogen-team-hydrogen-1st-place-solution)).
3. **Debias pairwise comparisons.** When comparing two reviews (agent versions, ablations, v1 vs updated artefact):
   - Run both orders and average.
   - Report the **position flip rate** as a grader-quality metric.
   - Allow "tie".

   Source: [4th place LMSYS / pairjudge](https://github.com/DaoyuanLi2816/Kaggle-4th-Place-Solution-LMSYS-Chatbot-Arena-Human-Preference-Predictions) [GH].
4. **Control verbosity bias explicitly.** Human and LLM judges reward length: 58.4 % "longer wins" on 48k
   human-labelled pairs [GH] ([WSDM 5th place](https://github.com/datahubber/wsdm-cup-5th-place-llm-judge)). Two checks:
   - Regress grader preference on length difference, and report it.
   - Include length-matched pairs in grader validation.

   For the agent, this argues for a concise review in which every finding carries evidence, not a padded one.
5. **Calibrated scores.** Where the grader model exposes log-probs, take the expected score over the rating tokens,
   or the A/B log-prob margin, instead of the argmax. Gate any fallback heuristic to near-ties only. Source: WSDM
   5th place [GH].
6. **Long-input truncation.** When a document or review exceeds the context budget, keep the head and tail of each
   section rather than the head only (WSDM 5th place, 15/5 % and 30/10 % budgets [GH]), or truncate from the
   middle (WSDM 1st place [S]). For 20-30-page design PDFs, prefer section-level retrieval over blind truncation.
7. **Agreement metrics and ceiling.**
   - Report grader-vs-human agreement with **QWK** for ordinal rubric scores ([AES 2.0](https://www.kaggle.com/competitions/learning-agency-lab-automated-essay-scoring-2) [S]).
   - Compare it with **human-human** agreement on the same items. ICLR reviewer-pair correlation is only 0.40 [GH].
   - Check for systematic rubric differences between label sources (AES 2.0 1st place [S]).
8. **Small-eval-set hygiene.**
   - Report mean ± spread over repeated runs or seeds. Single runs mislead (MAP 2025 1st place [S]).
   - Keep a hold-out of artefacts written after the agent is frozen (Konwinski Prize's post-deadline test
     collection [S]).
9. **Red-team the grader.** Before trusting grader scores, check that it is not moved by jargon, formatting tricks,
   fabricated citations or embedded instructions. Source:
   [LLMs - You Can't Please Them All](https://www.kaggle.com/competitions/llms-you-cant-please-them-all) [S], and the
   technique list in [this community repo](https://github.com/zixi-liu/LLMs-You-Cant-Please-Them-All) [GH].
10. **Evidence retrieval pattern.**
    - Use several retrievers, then judge each claim against its retrieved context (LLM Science Exam 1st place [S]).
    - To map findings onto a fixed catalogue (ISO/IEC 25010 attributes, control frameworks), retrieve the top-k
      entries and rerank them in a cascade, pointwise and then listwise (Eedi 1st place [S]).

### What is *not* recommended

- Fine-tuning a grader on Kaggle essay or chat data and expecting it to transfer to architecture reviews.
  The domain gap is large, and nothing found measures transfer to this domain.
- Training on ReviewCritique. Its licence forbids it [GH].
- Treating PeerRead or ICLR accept/reject labels as "design quality" labels. They measure venue acceptance,
  not fitness for purpose.

## Licences at a glance

| Resource | Licence | Status |
|---|---|---|
| PERSUADE 2.0 | CC BY-NC-SA 4.0 | [GH] |
| RevUtil | CC BY-NC-SA 4.0 | [GH] |
| ReviewCritique | Research only, no training | [GH] |
| ASAP-Review | Apache-2.0 | [GH] ([ReviewAdvisor](https://github.com/neulab/ReviewAdvisor)) |
| kaggle-benchmarks | Apache-2.0 | [GH] |
| pairjudge (LMSYS 4th place) | MIT | [GH] |
| WSDM 5th-place code | MIT | [GH] |
| NLPEERv2 | CC BY-NC 4.0 | [S] |
| All Kaggle competition data | Competition rules | UNVERIFIED: kaggle.com blocked. Kaggle competition data is commonly restricted to competition or non-commercial use. Check each "Rules" tab before use. |
| Arena-55k on HuggingFace | Not checked | UNVERIFIED |

## Method and what could not be verified

**Network:** From this environment, kaggle.com, huggingface.co, arxiv.org / export.arxiv.org, web.archive.org,
r.jina.ai, the-learning-agency-lab.com, hippocampus-garden.com and nebius.com were **blocked by the egress
proxy** (HTTP 403 on CONNECT, or "EGRESS_BLOCKED" on fetch). Each was tried once or twice, then abandoned.
Two routes worked:

1. A web search tool. Snippets are cited as [S] with the URL each one points to.
2. raw.githubusercontent.com. READMEs and source files of winning-solution and dataset repos are cited as [GH].
   The GitHub REST API (`gh api`) was not enabled for arbitrary repos in this session.

**Queries run** (abridged):

- AES 2.0 1st place
- LMSYS / WSDM winning solutions
- Feedback Prize (all three)
- CommonLit (both)
- LLM Science Exam
- Eedi
- AI4Code
- PII
- LLM-as-judge Kaggle 2025
- Kaggle 2026 agent / long-context
- Kaggle peer review competition
- requirements datasets on Kaggle
- PeerRead
- ICLR reviews on Kaggle
- software architecture review datasets
- requirements ambiguity benchmarks
- Jigsaw Agile Community Rules
- LLMs You Can't Please Them All
- Konwinski Prize
- Kaggle Community Benchmarks
- MAP 2025
- RevUtil
- ReviewCritique
- NLPeer
- DISAPERE
- PRISM
- ASAP-Review

**Not verified (treat with care):**

- Official metrics, dates and data licences on every Kaggle competition page. Where stated, they come from [S]
  snippets or solution READMEs.
- The LMSYS 1st-place method (distillation 70B→9B, LoRA averaging), from a social-media summary and a review blog [S].
- The 1st-place techniques for AES 2.0, FP2, CommonLit Readability, LLM Science Exam, Eedi and MAP, all from
  snippets of writeups or blogs [S]. FP2, FP3, CLRP and PII repos were opened [GH], but their discussion writeups
  were not.
- The winning approaches for Jigsaw Agile Community Rules 2025 and LLMs - You Can't Please Them All. **No writeup
  found.**
- The Kaggle URL slug for AES 2.0.
- The availability of PRISM data and of the ADR corpora.

**How to re-verify quickly** (from a network with Kaggle access):

1. Open each competition's Overview, Data and Rules tabs, and the top three entries under "Writeups".
2. For HF datasets, read the dataset cards linked in candidates.md.
3. Update the [S] tags to [verified] in candidates.md.

## How to reuse this note in another project

- Keep the **verification legend**. It lets a reader know which facts are first-hand.
- Re-rank with the same four criteria, changing only "how directly it helps" for the new task. For a
  summarisation grader, for example, CommonLit Summaries rises. For a code-review agent, Konwinski Prize and code
  review benchmarks rise.
- The practices in "Recommendations" 3-9 are domain-independent LLM-judge hygiene and can be copied as-is.
