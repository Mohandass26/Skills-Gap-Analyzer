# Week 2 : AI Component

# Feature Engineering and LLM Integration

## Project Overview

This module is the AI layer of the Resume Skill Gap Analyzer. It enriches a SQLite job listings database with extracted tech stacks, then compares a candidate's resume against that database to surface missing skills.

Four scripts make up the pipeline:

| File | Role |
|------|------|
| `db_server.py` | A [FastMCP](https://gofastmcp.com/) server exposing the jobs table as tools (query, fetch-untagged, update, count). |
| `tag.py` | Reads untagged jobs (via `db_server.py` over MCP), extracts a tech stack per job using a cheap regex pass first and Gemini as the fallback, and writes results back to the DB. |
| `find_skill_gaps.py` | Aggregates `tech_stack` values across all tagged jobs, extracts skills from a resume (Gemini, cached for determinism), and returns the set difference as a `SkillGapResult`. |
| `prompt_model.py` | A small standalone CLI for sending one prompt to either a local Ollama model or a Gemini model. **Note:** `tag.py` and `find_skill_gaps.py` each call the Gemini SDK directly — they do not currently route through this module. |

---

## Setup Instructions

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | **3.14+** |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest |
| Ollama | running on `localhost:11434` — only required if you call `prompt_model.py` with an Ollama model |

### Install

```bash
git clone [github_repo_link] [folder_name]
cd [folder_name]

uv python install 3.14
uv sync          # installs fastmcp, google-genai, ollama, python-dotenv, ruff from pyproject.toml
```

### Configure environment variables

Create a `.env` file at the project root (never commit this):

```
GEMINI_API_KEY=your_key_here
```

`google-genai`'s `Client()` picks this up automatically (`GOOGLE_API_KEY` also works). No key is needed to run `find_skill_gaps.py` against a resume that's already cached, or to call an Ollama model via `prompt_model.py`.

### Before your first run

The rate-limit file must be named **`rate_limits.txt`** (plural) at the project root — `tag.py` reads `Path("./rate_limits.txt")`. Rename it if it was provided as `rate_limit.txt`. Format, one model per line:

```
gemini-2.5-flash 5 250000 20
gemini-2.5-flash-lite 10 250000 20
gemini-3-flash-preview 5 250000 20
gemini-3.1-flash-lite 15 250K 500
```
(`<model> <RPM> <TPM> <RPD>` — `K`/`M` suffixes are supported.)

Expected layout:

```
.
├── tag_data.py
├── find_skill_gaps.py
├── db_server.py
├── prompt_model.py
├── rate_limits.txt
├── pyproject.toml
└── data/
    ├── jobs_d1.db
    └── resume_d3.txt
```

`tag_data.py` launches `db_server.py` as a subprocess (`PythonStdioTransport("db_server.py", ...)`), so run it from the directory that contains `db_server.py`. Two files are created automatically on first run and should not be committed: `usage_state.json` (per-day, per-model request counts) and `skill_gap_cache.json` (cached resume skill extractions).

---

## Usage

```bash
# Stage 0 — send one prompt to a named model
uv run prompt_model.py <model> "<prompt>"
# With no/wrong args, prints usage + the list of supported model names

# Stage 1 — tag every untagged job in the database
uv run tag_data.py data/jobs_d1.db
# defaults to data/jobs_d1.db if the path is omitted

# Stage 2 — compare a resume against the tagged database
uv run find_skill_gaps.py data/resume_d3.txt data/jobs_d1.db
# defaults to data/resume_d3.txt and data/jobs_d1.db (falls back to data/job.db)
```

**`tag_data.py` stdout (typical):**
```
Analyzed Job 91397216: Python, SQL, MySQL, Tableau
Analyzed Job 91347112: Java, PyTorch, TensorFlow, Git, CI/CD
Total tokens used: 2044, took 19305.595ms
```
If every row already has a `tech_stack`, it prints `No data to tag` and exits.

**`find_skill_gaps.py` stdout:**
```
gaps=['aws', 'docker', 'kubernetes'] time=1.42 tokens=186
```

### Code formatting
```bash
uv run ruff format .
uv run ruff check .
```

---

## API / Function Reference

### `prompt_model.py` — `prompt_model(llm_model: str, prompt: str) -> str | None`
Routes a prompt to Ollama (`llama3.1`, `phi3`, `deepseek-r1:1.5b`, `gemma3:1b`) or Gemini (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite`) based on the model name. Returns `None` only when `model` or `prompt` is empty; an unrecognized model name or an API exception instead returns a descriptive `"[Error] ..."` string, so callers should check for both `None` and an `[Error]`-prefixed string.

### `db_server.py` — MCP tools (called over stdio by `tag_data.py`)
| Tool | Purpose | Returns |
|------|---------|---------|
| `query_db(sql_query)` | Run any read-only SQL against the jobs DB | `list[dict]`, or `[{"error": ...}]` |
| `get_untagged_jobs(limit, offset)` | Page through rows where `tech_stack` is null/empty | `list[dict]` of `source_id`, `job_title`, `company`, `description` |
| `update_tech_stack(source_id, tech_stack)` | Write a comma-separated tech stack to one row | `{"success", "source_id", "rows_affected"}` |
| `count_untagged_jobs()` | How many rows still need tagging | `{"untagged_count": int}` |

### `tag_data.py` — `async def tag_data(db_url: str) -> None`
Spawns `db_server.py` and loops until `count_untagged_jobs` returns 0. Each round: pulls a pool of jobs, resolves what it can with a single regex pass (~50 hand-curated tech patterns — a job is resolved without the LLM once ≥2 terms match), sends the remainder to Gemini in batches sized from `rate_limits.txt` (TPM/RPM × 0.8 safety margin, capped at 20/batch), and retries **only the still-missing rows** within a batch rather than the whole batch. If a model fails twice it's marked exhausted for the day and the next model in the Gemini cascade (`gemini-3.1-flash-lite → gemini-2.5-flash-lite → gemini-2.5-flash → gemini-3-flash-preview`) takes over. Always prints a final `Total tokens used: …, took …ms` line; returns `None`.

### `find_skill_gaps.py` — `find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult`
```python
class SkillGapResult(BaseModel):
    gaps: List[str]   # sorted, lowercase
    tokens: int        # 0 on a cache hit
    time: float        # seconds
```
Reads `tech_stack` directly from SQLite (no MCP here), aggregates it into a skill set via `parse_skills()`, extracts the resume's skills with one Gemini call (temperature 0, cached by `sha256(model + resume_text)` so repeat runs are free and identical), and returns the set difference. If Gemini is unreachable after 3 retries, it falls back to a deterministic word-boundary substring match against the raw resume text instead — the function never raises; file-not-found and DB errors are caught and return an empty `SkillGapResult` with a printed message.

`parse_skills(text) -> Set[str]` — lowercases input, protects `a/b testing` and `ci/cd` from the `/`-split (via temporary placeholder tokens), splits everything else on `/`, drops certifications (`certifi(ed|cation)` regex) and a hardcoded soft-skills set, and special-cases `c/c++` so it always yields **both** `c` and `c++`.

---

## Data / Assumptions

- `jobs` table: `source_id`, `job_title`, `company`, `description`, `tech_stack` (nullable until tagged).
- `resume.txt` is plain UTF-8 text — no PDF/DOCX parsing.
- `rate_limits.txt` drives both batch sizing and retry delay for `tag_data.py`; missing/wrong entries fall back to conservative defaults (5 RPM / 250k TPM).
- `usage_state.json` and `skill_gap_cache.json` are created and read automatically; deleting them resets daily quota tracking and the resume-skill cache respectively.
- Tagging is **not** required to be deterministic (LLM temperature/sampling may vary run to run); gap detection **is**, enforced via the resume-skill cache plus set-difference logic rather than asking an LLM to reason about gaps directly.

---

## Testing

| Scenario | How to run | Expected result |
|---|---|---|
| Full tagging run | `uv run tag.py data/jobs_d1.db` on a fresh DB | Each tagged job printed; `tech_stack` populated; final token/time line; no traceback |
| No-op run | Run `tag_data.py` again on the same DB | `No data to tag` |
| Model cascade | Temporarily point to an invalid Gemini model name in `rate_limits.txt` / induce repeated failures | `[model] failed (...)` then `giving up on this model for today, trying the next one...` |
| Regex fast path | Tag a job description containing ≥2 well-known terms (e.g. "Python, Docker") | Tagged without consuming Gemini tokens for that row |
| Determinism | `uv run find_skill_gaps.py resume.txt jobs_d1.db` twice in a row | Identical `gaps` list both times; `tokens=0` on the second run (cache hit) |
| Slash-splitting | DB contains `AWS/Azure/GCP`, resume has none of them | Gaps include `aws`, `azure`, `gcp` as three separate entries |
| Exceptions | DB contains `A/B testing` and `CI/CD` | Both appear intact, never split into `a`/`b testing` or `ci`/`cd` |
| Direct match | Resume contains `C/C++` | Neither `c` nor `c++` appear in gaps, however the DB stored it |
| Soft-skill/cert filter | DB contains `leadership` or `AWS Certified Solutions Architect` | Neither appears in `gaps` |
| Graceful failure | Point `find_skill_gaps.py` at a missing resume or DB path | Printed `Error: ...` message, empty `SkillGapResult`, no traceback |

---

## Limitations

- **`prompt_model.py` is not actually wired into the pipeline.** Both `tag_data.py` and `find_skill_gaps.py` instantiate their own `genai.Client()` and call it directly instead of going through `prompt_model()`, so the "single routing layer" only exists as a standalone CLI utility today.
- **Ollama is unused by the pipeline itself.** Only `prompt_model.py` can reach local models; tagging and gap analysis are Gemini-only, so the project doesn't currently get the offline/privacy benefit the dual-model setup was meant to provide.
- **Inconsistent data access.** `tag_data.py` reaches the database only through the `db_server.py` MCP tools; `find_skill_gaps.py` connects to SQLite directly. Future changes to the DB layer need to be made in two places.
- **`query_db`'s arbitrary SQL tool** has no statement allow-list — fine for a local single-user MCP server, but not something to expose beyond this trusted setup.
- **Regex coverage is fixed.** The fast path only recognizes the ~50 terms hand-coded into `tag_data.py`; anything outside that list always falls through to the LLM, and a description with exactly 1 recognizable term still goes to the LLM even though the regex partially "saw" it.
- **Daily usage tracking is a local JSON file** (`usage_state.json`), not safe against concurrent processes tagging the same machine at once.
- **`prompt_model()` has no retries and no `temperature`/`top_p` parameters** — failures and unknown models return an error string on the first attempt rather than retrying or returning `None`.
- Skill-gap accuracy is bounded by tagging accuracy and by the hardcoded soft-skill list in `find_skill_gaps.py` — any soft skill not in that set will not be filtered.

---

## Architecture Reflection

### Design Choices
`tag_data.py` and `db_server.py` are split across an MCP boundary deliberately: `db_server.py` owns all writes/reads to the jobs table behind four narrow tools, so the tagging logic in `tag_data.py` never needs a raw SQL connection. `find_skill_gaps.py` only needs a single read-aggregate query, so it talks to SQLite directly instead of paying the subprocess/MCP overhead for one `SELECT`. Inside `tag_data.py`, a regex pass runs before any LLM call — most job descriptions mention a handful of well-known tools by name, and resolving those locally avoids spending tokens (and rate-limit headroom) on the easy cases, leaving the LLM for jobs the regex can't confidently parse. `find_skill_gaps.py` caches resume-skill extraction by a hash of the model name and resume text specifically so the determinism requirement is met by *avoiding* a second LLM call on repeat runs rather than by hoping `temperature=0` is perfectly reproducible.

### Trade-offs
`tag_data.py` trades a more complex batching/cascade scheme for predictable costs: rate limits drive both batch size and retry delay, and a model that keeps failing is benched for the day rather than retried indefinitely, so one quota-exhausted model degrades the pipeline instead of stalling it. `find_skill_gaps.py` trades the "ask an LLM what's missing" approach for a deterministic set-difference: the LLM is only ever used for the part that genuinely needs natural-language understanding (turning free-text resume content into a skill list), with a non-LLM substring-match fallback if Gemini is unreachable, so the function always returns a usable result rather than raising.

### Improvements
Given more time: route `tag_data.py` and `find_skill_gaps.py` through `prompt_model.py` so model selection is actually centralized as originally intended; add an Ollama fallback path for `tag_data.py` so tagging can continue offline once the Gemini daily quota is exhausted rather than stopping; align the rate-limit filename and add a startup check that fails fast (with a clear message) if `rate_limits.txt` is missing or malformed; and add a skill-alias table (`sklearn` ↔ `scikit-learn`, `JS` ↔ `JavaScript`) to reduce false-positive gaps caused by naming differences between resumes and job listings.