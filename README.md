# Document Agent

An autonomous agent that turns a one-line request into a business document (.docx). It plans its own tasks, runs each one with a tool, reviews its own draft, and returns the document plus a report of what it did, assumed and fixed.

Built for the Fluid AI "Python AI Engineer – Autonomous Agents" assignment. The company data is mock: a made-up bank and insurer with a few records (teams, meeting notes, a voice platform, cost rates, past projects) in `app/mock_data.py`.

## How it works

```
POST /agent {"request": "..."}
  1. lookup      plain Python: records whose tags match the request
  2. plan        1 LLM call → typed Plan (doc type, assumptions, conflicts, 4-8 tasks, a tool per task)
  3. execute     a loop: each task's tool writes one section, seeing the records and the sections before it
  4. self-check  1 LLM review (coverage, consistency, conflicts) → verified issues fixed by re-running the tool that made the section
  5. write       python-docx builds the Word file (no LLM)
  ← summary, task list, assumptions, conflicts, self-check with before/after, download link
GET /documents/{id} → the .docx
```

`app/agent.py` is the whole pipeline in a few lines.

**Tools the planner chooses from:** `lookup_mock_data` (plain Python), `write_section`, `make_table`, `calculate` (the model picks line items, quantities and rates; Python does every sum, adds the contingency and checks the total against the budget).

**The one engineering improvement: reflection (self-check)**, in `app/reviewer.py`. Chosen because, for banks and insurers, the costly failure is a confident document with a wrong number or a missed requirement. Guards on the reviewer itself:
- every reported problem must quote the draft, and code checks the quote exists; otherwise the issue is rejected
- a section is redone by the tool that created it, so a wrong total is recomputed in Python, not reworded
- before/after text is kept for every fix and returned by the API
- after any fix, the summary is refreshed so it can't contradict the fixed sections

**Other decisions**
- Every LLM answer is validated against a Pydantic model (the schema is sent with the prompt; one retry with the error). Tool names are a fixed set, so the model can't invent one.
- Things that must always hold are enforced in code, not left to prompts: lookups run first, one budget section (always `calculate`), totals only from Python, summary written last.
- Guardrails: non-document requests are declined (422); the request is treated as data, and API keys never appear in any prompt.
- One LLM client with a fallback chain: three Groq models, then Gemini; 30 s timeout per call; short waits when every model is rate-limited.

## Run it

Python 3.12. Free API keys from Groq and/or Google AI Studio.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # add GROQ_API_KEY and/or GEMINI_API_KEY
.venv/bin/uvicorn app.api:app --port 8010
```

Open http://localhost:8010/docs → `POST /agent` → Try it out. The examples dropdown has both test inputs:
- **Standard:** "Write meeting minutes for our weekly KYC onboarding sync."
- **Complex:** "Proposal for a voice bot for our insurance claims line: launch in 2 weeks, budget under 5 lakh rupees, must support 6 languages, details to follow." (conflicting and missing information: the agent phases the scope, states its assumptions and checks the budget)

## Tests and evaluation

```bash
.venv/bin/pytest -q              # 37 unit tests, fake models, ~0.2 s
.venv/bin/python -m evals.run    # 8-case eval through the real API (uses free-tier quota)
SELF_CHECK=0 .venv/bin/python -m evals.run   # same cases with the self-check off (ablation)
```

The eval set (`evals/cases.py`) covers standard, vague, conflicting, missing-information, off-topic and prompt-injection requests. Each output is graded by deterministic checks (facts from the records present, assumptions stated, conflict flagged, budget adds up, nothing leaked, decline when expected) and an LLM judge on a different model. Past runs are in `evals/results/`; they're single runs per case on free tiers, so treat them as indicative.

## Known limits and next steps

- Lookup is keyword matching over a handful of records; with real data I'd use hybrid search (keyword + semantic) and pass only relevant chunks.
- The quote check verifies "this is wrong" claims; "this is missing" claims have nothing to quote, so I'd verify those against the records instead.
- One review pass: a fix can introduce a new small error; next would be re-checking only the fixed sections.
- `calculate` supports one percentage (contingency); tax or discounts would be new fields, keeping Python in charge of the maths.
- Requests run synchronously; long documents would go to a job queue and files to object storage.
