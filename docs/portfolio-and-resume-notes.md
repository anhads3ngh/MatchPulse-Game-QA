# MatchPulse — Portfolio and resume notes

## 30-second project explanation

"MatchPulse is a full-stack, local QA intelligence dashboard for a fictional football game. I can explore synthetic gameplay crash rates, investigate bug reports, get explainable NLP suggestions for duplicate issues, simulate repeatable regression runs, and export stakeholder quality briefings. The implementation uses Python's standard library, SQLite and vanilla JavaScript, with 43 automated unit and API contract tests. It does not connect to a live game."

## Potential resume bullets — verify your contribution before using

- Developed **MatchPulse**, a Python/SQLite and JavaScript game-quality analytics platform modeling **3,000 synthetic gameplay sessions and 104 fictional defect reports** across PC, PlayStation and Xbox; visualized crashes, FPS, desynchronization, regression trends and feature-level risk.
- Implemented an **explainable TF-IDF/cosine-similarity duplicate-report assistant** with searchable defect triage, reproduction steps, status and owner updates, and CSV export to support systematic quality workflows.
- Built **five configurable synthetic test suites** with deterministic seeded execution, per-test pass/fail reporting, SQLite execution history and **43 automated unit/API tests**, plus a GitHub Actions cross-platform CI workflow.
- Documented current-state/future-state QA workflows and acceptance criteria; generated Markdown release briefs connecting observed quality signals to recommended engineering follow-ups.

Use only the bullets that accurately reflect work you have reviewed, implemented, understood and can discuss in interviews. This is an independent simulated project, not an Electronic Arts product.

## Demo talking points

1. Product context: What quality problems are important to players?
2. Data modeling: Why separate sessions, issue reports, test runs and audits?
3. Explainability: Why TF-IDF candidate ranking instead of automatic duplicate merges?
4. Reproducibility: Why save deterministic seeds with scenario runs?
5. Reliability: Which inputs and business rules have regression tests?
6. Future work: How to connect real game instrumentation responsibly with access controls and validated schemas.
