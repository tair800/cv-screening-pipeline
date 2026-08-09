# Problem statement

> This document is written before any pipeline code. If the problem, the success
> criteria and the risks are not clear on paper, no amount of engineering downstream
> will make the result trustworthy.

---

## 1. The problem

High-volume recruitment screening is manual, repetitive, and inconsistent. The same CV
reviewed by two recruiters — or by one recruiter on two different days — does not
reliably produce the same shortlist.

**Baseline (state the numbers you are working against):**

| Measure | Value |
|---|---|
| CVs received per month | ✍️ *e.g. 500* |
| Manual review time per CV | ✍️ *e.g. 6 minutes* |
| Total monthly effort | ✍️ *e.g. 50 hours* |
| Shortlist produced by | ✍️ *e.g. 1 recruiter, no second review* |

> ✍️ **Fill these in.** Estimates are fine — say they are estimates. A stated,
> defensible number is worth more than a vague claim of "a lot of time".

---

## 2. What success looks like

A pipeline that ranks candidates is not automatically a pipeline that helps. Success is
defined here in terms a recruiter would recognise, not in terms of model metrics alone.

| Criterion | Target | How it is measured |
|---|---|---|
| Extraction accuracy | ✍️ *e.g. ≥ 95% on required fields* | Compared against generated ground truth |
| Ranking agreement | ✍️ *e.g. ≥ 80% overlap in top 10* | Pipeline shortlist vs. human shortlist |
| Bias parity | No score gap within a matched pair | Matched-pair fixtures in the dataset |
| Throughput | ✍️ *e.g. 500 CVs in under 30 min* | End-to-end run time |
| Human control | 100% of decisions overridable | Override flow exercised in tests |

**Explicit non-goals.** Naming these prevents scope creep and sets honest expectations:

- The pipeline does not reject candidates. It orders them and explains the ordering.
- The pipeline does not make the hiring decision. A recruiter does.
- ✍️ *anything else you deliberately exclude*

---

## 3. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Bias / disparate treatment** | Names, gender and origin can leak into scores | Matched-pair fixtures; parity test in CI |
| **Personal data (GDPR)** | CVs are personal data; sending them to a third-party model is a transfer | Synthetic data only in this project; PII handling documented before any real use |
| **False negatives** | A wrongly down-ranked candidate is never seen again | Ranking only, no auto-reject; full audit trail |
| **LLM non-determinism** | The same CV could score differently on two runs | Enforced JSON Schema, low temperature, regression fixtures |
| **Over-trust in the score** | A number looks objective even when it is not | Every score is decomposed into traceable reasons |
| ✍️ *your addition* | | |

---

## 4. Why an LLM — and what was rejected

Choosing a tool is an engineering decision and should be written down as one.

| Option | Verdict | Reason |
|---|---|---|
| **Keyword / regex matching** | ✍️ rejected? | Cheap, fast, fully deterministic — but blind to phrasing. "Built workflows in n8n" and "n8n" are the same skill; keyword matching often disagrees. |
| **Classical ML classifier** | ✍️ rejected? | Needs a labelled training set that does not exist here, and it learns historical hiring bias directly from the labels. |
| **LLM structured extraction** | ✍️ chosen? | Handles free-form phrasing across CV layouts, returns a schema-constrained record, and needs no training data. Costs money per call and is non-deterministic — both are managed, not ignored. |

> ✍️ **Write your own verdict column and one or two sentences of reasoning.**
> This section is the single strongest signal in the whole repository: it shows a
> reviewer *how you think*, not just what you used.

---

## 5. Regulatory context

Under the **EU AI Act, Annex III**, systems that filter job applications and evaluate
candidates are **high-risk**. Article 50 transparency duties apply from **2 August 2026**;
the full high-risk obligations for stand-alone Annex III systems apply from
**2 December 2027** following the Digital Omnibus amendment. Deployer penalties reach
**€15M or 3% of global annual turnover**.

Requirements this project treats as engineering work:

- [ ] Risk assessment — this document
- [ ] Technical documentation — README + architecture decisions
- [ ] Bias testing — matched-pair parity tests
- [ ] Human oversight — recruiter can override or reverse any output
- [ ] Transparency — candidates and recruiters can see that AI was used, and on what basis
- [ ] Monitoring — decision logs and drift checks

*Engineering project, not legal advice.*

---

## 6. Open questions

> ✍️ Keep this list alive. Questions you have not answered yet are not a weakness in a
> portfolio — they are evidence that you know where the edges are.

- How should "years of experience" be counted when employment gaps exist?
- Should a missing field lower a score, or be excluded from scoring entirely?
- ✍️ *yours*
