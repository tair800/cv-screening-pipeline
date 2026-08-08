# Problem statement

> Written before any pipeline code. If the problem, the success criteria and the risks
> are not clear on paper, no amount of engineering downstream will make the result
> trustworthy.

> **On the numbers in this document.** This project is scoped against a *modelled*
> mid-size European insurer — roughly 1,200 employees, an in-house recruitment team of
> three, hiring for around 120 openings a year. Every figure below is a stated planning
> assumption used to size the problem and to make the success criteria falsifiable.
> **None of it is measured data, and none of it describes any actual employer.** Where a
> figure would change the design if it were wrong, that is called out.

---

## 1. The problem

High-volume recruitment screening is manual, repetitive, and inconsistent. The first pass
over a CV pile is largely mechanical — does this person have the required skills, roughly
the right amount of experience, the right qualifications — yet it consumes senior
recruiter time and produces results that are hard to reproduce. The same CV reviewed by
two recruiters, or by one recruiter on a Friday afternoon rather than a Monday morning,
does not reliably land in the same pile.

For an insurer the problem has a second edge: the sector is supervised, internal audit
asks how decisions were reached, and "the recruiter had a feeling" is not an answer that
survives that question.

**Baseline — modelled, see note above:**

| Measure | Assumed value | Basis for the assumption |
|---|---|---|
| Open roles per month | ~10 | 120 hires/year spread evenly |
| Applications per role | ~50 | Typical for a corporate role advertised on one job board plus the careers page |
| CVs received per month | **~500** | 10 × 50 |
| First-pass review time per CV | **~6 minutes** | Read, cross-check against requirements, record a yes/no/maybe |
| Total monthly screening effort | **~50 hours** | 500 × 6 min |
| Share of a recruiter's month | **~30% FTE** | 50 h against a ~160 h month |
| Time from posting close to shortlist | ~5–8 working days | Screening is batched around other duties |
| Second review of rejected CVs | **None** | A single reviewer decides; there is no appeal path |
| Inter-reviewer agreement | **Unmeasured** | Nobody currently knows how consistent the process is |

The last two rows matter more than the hours. The cost of the current process is not
only time — it is that **a rejection is invisible, unreviewed, and unexplained.**

---

## 2. What success looks like

A pipeline that produces a ranking is not automatically a pipeline that helps. Success is
defined in terms a recruiter and an auditor would both recognise.

| Criterion | Target | How it is measured |
|---|---|---|
| **Extraction accuracy — required fields** | ≥ 95% | Field-level comparison against generated ground truth (skills, years, education) |
| **Extraction accuracy — all fields** | ≥ 90% | As above, across every field in the schema |
| **Hallucination rate** | 0 invented skills | Any extracted skill absent from the source text is a hard failure |
| **Ranking agreement** | ≥ 80% overlap in top 10 | Pipeline shortlist vs. a recruiter shortlist on the same set |
| **Bias parity** | **0 score difference within a matched pair** | Matched-pair fixtures; any non-zero delta is a defect, not a tolerance |
| **Throughput** | 500 CVs in < 30 minutes | End-to-end wall-clock on the full set |
| **Cost per run** | < €10 per 500 CVs | Token accounting per call, summed |
| **Human control** | 100% of rankings overridable | Override path exercised in tests, not just available |
| **Auditability** | Every score decomposable | Each point traceable to a named requirement and a source line |

**Why "ranking agreement" and not "accuracy".** There is no objective ground truth for
*who should be hired*. The only honest target is agreement with an experienced human on
the shortlist, and even that is a benchmark rather than a definition of correctness. The
80% figure is chosen so that disagreement is expected and inspected, not eliminated —
a pipeline that agreed 100% would be reproducing the recruiter, including their biases.

### Explicit non-goals

Naming these prevents scope creep and sets honest expectations:

- **The pipeline does not reject anyone.** It orders candidates and explains the ordering.
- **The pipeline does not decide.** A recruiter does, and their decision is recorded.
- It does not score personality, "culture fit", or anything inferred from photographs, names, age, gender, nationality, or address.
- It does not replace the ATS, schedule interviews, or contact candidates.
- It does not learn from past hiring outcomes. Doing so would encode historical bias as if it were signal — see §4.

---

## 3. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Bias / disparate treatment** | Names, gender and origin can leak into scores through the model's priors even when never scored explicitly | Matched-pair fixtures; parity test runs on every change; identity fields excluded from scoring input |
| **Proxy discrimination** | Neutral-looking fields carry protected signal — postcode, university, career gaps, language list | Scoring input restricted to an allow-list of competence fields; exclusions documented with reasons in the role definition |
| **Personal data (GDPR)** | CVs are personal data; sending them to a third-party model is a transfer with a legal basis, retention and residency to justify | Synthetic data only in this project. Before any real use: DPIA, EU data residency, retention limits, no training on candidate data |
| **False negatives** | A wrongly down-ranked candidate is never seen again and never complains, so the error is silent | Ranking only, no auto-reject; full audit trail; periodic manual sampling of the bottom of the ranking |
| **LLM non-determinism** | The same CV could extract differently across two runs, which breaks both fairness and reproducibility | Enforced JSON Schema, temperature 0, pinned model version, regression fixtures that fail on drift |
| **Over-trust in the score** | A number reads as objective even when it is an estimate stacked on an extraction that may be wrong | Scores shown decomposed, never as a bare number; confidence surfaced; low-confidence extractions routed to a human |
| **Model or vendor change** | A provider silently updates a model and the ranking shifts underneath the process | Version pinning; regression suite re-run before any model change is accepted |
| **Regulatory exposure** | Recruitment AI is high-risk under EU AI Act Annex III; an insurer is already a supervised entity | Compliance treated as engineering work — see §5 |
| **Works council / employee representation** | In several EU jurisdictions, introducing such a system requires consultation before deployment, not after | Flagged as a deployment prerequisite; out of scope for this repository but recorded so it is not forgotten |
| **Automation of an unexamined process** | Automating a biased manual process makes the bias faster and harder to see | Measure inter-reviewer agreement on the manual baseline *before* claiming the pipeline improves anything |

---

## 4. Why an LLM — and what was rejected

Choosing a tool is an engineering decision and is recorded as one.

| Option | Verdict | Reasoning |
|---|---|---|
| **Do nothing (status quo)** | **Rejected** | The honest baseline, and it has a real advantage: no new regulatory surface, no vendor cost. It is rejected because it does not scale with hiring volume and, more importantly, it produces unreviewable single-person rejections. The problem being solved is consistency at least as much as speed. |
| **Keyword / regex matching** | **Rejected as the primary method — retained as a baseline** | Cheap, instant, fully deterministic, and trivially auditable. It fails because CV language is not standardised: *"built and maintained workflows in n8n"*, *"n8n (advanced)"* and *"low-code automation using n8n"* are the same skill, and a keyword list catches some and misses others. Retained as a comparison baseline, because if the LLM cannot beat regex on measured accuracy, the LLM is not justified. |
| **Classical ML classifier** | **Rejected** | Would need a labelled training set of past hiring decisions. That set does not exist here, and if it did, training on it would encode the historical preferences of past reviewers — the exact bias this project is trying to expose. Rejecting supervised learning on past outcomes is a fairness decision, not a technical one. |
| **LLM structured extraction + rule-based scoring** | **Chosen** | Splits the problem at the right seam. The LLM does what it is good at — reading inconsistent free text and returning a schema-constrained record — and nothing else. Scoring is then plain deterministic code over that record: reproducible, inspectable, and explainable line by line. The known weaknesses (per-call cost, non-determinism, hallucination) are managed explicitly in §3 rather than assumed away. |

**The key design decision** is the split: *the model extracts, the code decides.* Handing
the ranking to the model as well would have been less work and would have produced a
system whose decisions could not be explained to a candidate, a recruiter, or an auditor.

---

## 5. Regulatory context

Under the **EU AI Act, Annex III**, systems that filter job applications and evaluate
candidates are classified **high-risk**. Article 50 transparency duties apply from
**2 August 2026**; the full high-risk obligations for stand-alone Annex III systems apply
from **2 December 2027** following the Digital Omnibus amendment. Deployer penalties
reach **€15M or 3% of global annual turnover**, and can reach deployers established
outside the EU.

Requirements treated as engineering work in this repository:

- [ ] **Risk assessment** — this document
- [ ] **Technical documentation** — README, architecture decisions, role definition with documented exclusions
- [ ] **Bias testing** — matched-pair parity tests, run on every change
- [ ] **Human oversight** — recruiter can override or reverse any output; override is logged with a reason
- [ ] **Transparency** — candidates are told AI assisted the screening and on what criteria; recruiters see the decomposition, not a bare score
- [ ] **Record-keeping** — decision logs retained with inputs, model version and outputs
- [ ] **Monitoring** — drift checks against regression fixtures; periodic sampling of low-ranked candidates

*This is an engineering project, not legal advice. A real deployment needs legal and
compliance sign-off, a DPIA, and — in several EU jurisdictions — works council consultation.*

---

## 6. Open questions

Questions not yet answered. Keeping them visible is deliberate: knowing where the edges
are is part of the work.

- **Employment gaps.** Should `years_experience` count elapsed calendar time or summed employment? Counting elapsed time penalises parental leave, illness and caring responsibilities — a fairness question disguised as a parsing question.
- **Missing fields.** Should an absent field lower a score or be excluded from it? Lowering it penalises candidates for CV formatting; excluding it rewards vagueness. Current leaning: exclude from scoring, surface as "not stated" to the recruiter.
- **Career changers.** Someone with ten years in claims handling and one year in automation may be the strongest hire and will rank poorly on a years-based criterion.
- **Overqualification.** Should it reduce a score? It is a legitimate business consideration and also a common cover for age discrimination. Currently not modelled at all.
- **Non-English CVs.** Extraction quality across languages is unmeasured, and an accuracy gap by language is a fairness gap.
- **Weight validation.** The requirement weights in the role definition are an informed guess. They should be re-derived once ranking agreement has been measured — but tuning weights until the pipeline matches the recruiter risks fitting the pipeline to the recruiter's bias.
- **Baseline consistency.** Inter-reviewer agreement on the manual process has never been measured, so "the pipeline is more consistent than humans" is currently an assumption, not a finding.
