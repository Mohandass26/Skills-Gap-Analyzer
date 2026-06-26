# Week 3: System Integration and Application

# Resume Helper Chatbot — Frontend + Backend Containerization

A containerized chat application that lets a user paste resume text or upload a PDF resume, and get back an AI-generated analysis of which skills (drawn from a real jobs database) are missing from their resume. The frontend and backend are two separate FastAPI services, each in its own Docker container, communicating over a shared Docker network.

---

## Project Overview

The goal of this project is to take the Week 2 skill-gap analysis logic and wrap it in a full-stack, containerized chat application:

- **Frontend** — a FastAPI service that serves a Bootstrap-based chat page. The browser extracts any uploaded PDF's text client-side (via `pdf.js`), then sends the message as JSON to the frontend's own `/send` route, which proxies it to the backend. Once a resume has been uploaded, the browser keeps reusing its extracted text for follow-up questions in the same session, without requiring it to be re-attached every time.
- **Backend** — a FastAPI service exposing `POST /chat`. If a resume was attached, it runs the Week 2 `find_skill_gaps()` function against a real jobs database, then asks an LLM to turn the result into a natural-language reply. If no resume was attached, it's a plain conversational reply.
- **AI integration** — Gemini (`google-genai`) powers the skill-gap extraction. For the conversational reply itself (both the plain-chat path and the reply wrapped around resume analysis), either **Gemini or Ollama** can be used, switchable via a single environment variable (`CHAT_PROVIDER`) — see [Bonus: Ollama](#bonus-ollama-as-a-second-llm-provider) below.
- **Secrets handling** — the Gemini API key can be supplied via a Docker secret (a file mounted into the container) instead of a plain environment variable, so it doesn't show up in `docker inspect` output — see [Bonus: Docker secrets](#bonus-docker-secrets-for-the-api-key).

Both services are built from their own `Dockerfile` and orchestrated together with `docker-compose.yml`.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose
- A Google Gemini API key — get one free at [https://aistudio.google.com](https://aistudio.google.com)
- A jobs database (SQLite) with a populated, non-empty `tech_stack` column — this is the Week 1/Week 2 output the skill-gap comparison reads from

Optional:
- A local [Ollama](https://ollama.com/) model, if you want to use the Ollama bonus instead of/alongside Gemini for conversational replies
- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/getting-started/installation/), if you want to run the services without Docker

---

## Setup Instructions

### 1. Project structure

```
week_3/
├── docker-compose.yml
├── .env.example
├── .env                         ← you create this (see step 2)
├── .gitignore
├── secrets/
│   ├── gemini_api_key.txt.example
│   └── gemini_api_key.txt       ← you create this (see step 3, optional but recommended)
├── frontend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── app.py
│       └── templates/
│           └── chat_page.html
└── backend/
    ├── Dockerfile
    ├── pyproject.toml
    └── src/
        ├── app.py
        └── week_2/
            ├── find_skill_gaps.py
            ├── prompt_model.py
            ├── __init__.py
            └── data/
                └── jobs.db        ← your real database goes here
```

### 2. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Edit `week_3/.env` and fill in at least:

```
GEMINI_API_KEY=your_gemini_api_key_here
```

(If you set up the Docker secret in step 3, this value is only used as a fallback — see [Bonus: Docker secrets](#bonus-docker-secrets-for-the-api-key).)

`.env` is never committed (it's listed in `.gitignore`) — only `.env.example` is, so no secrets are exposed in the repository. See `.env.example` for the full list of supported variables (`DEFAULT_MODEL`, `OLLAMA_DEFAULT_MODEL`, `CHAT_PROVIDER`, `SKILL_GAP_MODEL`, `JOBS_DB_PATH`, `OLLAMA_HOST`).

### 3. Set up the Gemini API key as a Docker secret (recommended)

```bash
cp secrets/gemini_api_key.txt.example secrets/gemini_api_key.txt
```

Edit `secrets/gemini_api_key.txt` and replace the placeholder with your real key — just the raw value, no `GEMINI_API_KEY=` prefix. This file is gitignored, same as `.env`. See [Bonus: Docker secrets](#bonus-docker-secrets-for-the-api-key) for why this is preferable to the plain `.env` value.

### 4. Add your jobs database

Place your SQLite database at `backend/src/week_2/data/jobs.db` (or `jobs_d1.db` — the backend checks for `jobs.db` first and falls back to `jobs_d1.db` if that's what you have). It must have a `jobs` table with a `tech_stack` column populated for meaningful gap detection.

---

## Usage

### Run with Docker Compose (recommended)

From the `week_3/` folder:

```bash
docker compose up --build
```

- **Frontend (chat UI):** [http://localhost:8000](http://localhost:8000)
- **Backend API:** [http://localhost:8001](http://localhost:8001)

This starts `frontend` and `backend` only. Ollama is not started by this command — see below.

To stop everything:

```bash
docker compose down
```

### Run with the Ollama bonus enabled

```bash
docker compose --profile ollama up --build
```

This additionally starts an `ollama` container. The first time, pull a model into it:

```bash
docker exec -it resume-ollama ollama pull llama3.1
```

This is a one-time step — the model persists in a named volume across restarts. Set `CHAT_PROVIDER=ollama` in `.env` and recreate the backend (`docker compose up -d --force-recreate backend`) to actually start using it for replies.

### Run locally without Docker

**Terminal 1 — Backend:**

```bash
cd backend
uv sync
uv run uvicorn --app-dir src --host 0.0.0.0 --port 8001 app:app
```

**Terminal 2 — Frontend:**

```bash
cd frontend
uv sync
uv run uvicorn --app-dir src --host 0.0.0.0 --port 8000 app:app
```

When running outside Docker, set `BACKEND_URL=http://localhost:8001` in `frontend`'s environment (Docker Compose sets this automatically to `http://backend:8001` via the service name — see [Docker network communication](#docker-network-communication)).

### Expected inputs and outputs

**Plain text message:**

Type a message with no PDF attached and press Send.

Example input: `What's a good interview question for a data analyst role?`

Example output: a normal conversational reply, generated by whichever provider `CHAT_PROVIDER` currently points at (Gemini by default, Ollama if configured).

**Resume / skill-gap analysis:**

Click the upload icon, select a PDF resume, optionally add a message, and press Send.

Example output:

> Your resume presents a strong profile as a Mid-level Software Engineer... For potential skill gaps, I noticed that many roles in this area often look for experience with cloud platforms like **AWS**, **Azure**, or **GCP**...

The reply is LLM-generated prose (not a raw list) — see [Architecture Reflection](#architecture-reflection) for why.

**Follow-up questions about the same resume:**

After uploading a resume once, you can keep asking about it (e.g. "summarise it", "what's my strongest skill") without re-attaching the PDF — the browser remembers the most recently uploaded resume's text for the rest of the session and resends it automatically. Uploading a different resume replaces the remembered one going forward. See [Data / Assumptions](#assumptions) for exactly what this does and doesn't cover.

---

## Bonus: Ollama as a second LLM provider

`prompt_model.py` supports both Gemini and Ollama models. Both model names stay configured in `.env` at the same time — a single switch decides which one is actually used:

```
DEFAULT_MODEL=gemini-2.5-flash-lite
OLLAMA_DEFAULT_MODEL=llama3.1
CHAT_PROVIDER=gemini          # change to "ollama" to switch
OLLAMA_HOST=http://ollama:11434
```

Flipping `CHAT_PROVIDER` and recreating the backend container switches every conversational reply (plain chat, and the reply wrapped around resume analysis) between providers — without ever losing track of either model name.

**Scope limitation:** this only covers the conversational reply. `find_skill_gaps.py`'s actual skill *extraction* step always uses Gemini, regardless of `CHAT_PROVIDER` — see [Limitations](#limitations).

`ollama` is defined in `docker-compose.yml` behind a Compose profile, so it never starts (and never gets pulled) unless you explicitly request it with `--profile ollama`. This keeps the default Gemini-only workflow fast and avoids downloading a multi-GB image nobody asked for.

---

## Bonus: Docker secrets for the API key

By default, putting `GEMINI_API_KEY` in `.env` means it shows up in plain text in `docker inspect <container>` and `docker compose exec backend env` — visible to anyone who can run those commands, and a common source of accidental leaks (pasted logs, screen-shares, crash reports).

Instead, the key can be provided as a Docker secret: a file mounted into the container at `/run/secrets/gemini_api_key`, never exposed as an environment variable. `prompt_model.py` checks for this file on startup and, if present, reads it and sets it into the process's own environment internally — so the `google-genai` library still picks it up, without it ever being visible via `docker inspect`.

```yaml
# docker-compose.yml
secrets:
  gemini_api_key:
    file: ./secrets/gemini_api_key.txt
```

If `secrets/gemini_api_key.txt` doesn't exist, `docker compose up` will fail to start — the file must exist (see [Setup Instructions](#3-set-up-the-gemini-api-key-as-a-docker-secret-recommended)), even though the `.env` fallback only kicks in once the container is already running.

**Honest scope note:** this prevents *accidental* exposure through Docker's own introspection tools. It does not encrypt the key at rest — `secrets/gemini_api_key.txt` is still plain text on disk, and anyone with file access to the project folder, or shell access to the running container, can still read it directly.

---

## API / Function Reference

### Backend: `POST /chat`

**URL:** `http://localhost:8001/chat` (or `http://backend:8001/chat` from inside the Docker network)

**Request (JSON):**
```json
{
  "message": "What skills am I missing?",
  "pdf_text": "extracted resume text, or omitted/empty if no resume"
}
```

**Response (JSON):**
```json
{
  "reply": "Natural-language reply from the LLM...",
  "skill_gaps": ["aws", "docker", "kubernetes"]
}
```

**How the backend processes a request** (`backend/src/app.py`):
1. If `pdf_text` is present and non-empty:
   - Writes it to a temporary `.txt` file
   - Calls `find_skill_gaps(tmp_path, DB_PATH)` (Week 2), which extracts skills from the resume via Gemini and compares them against the database's `tech_stack` values
   - Deletes the temp file
   - Builds a prompt containing the resume, the user's message, and the computed gaps — wrapped in `<Resume>`/`<Message>` tags with an explicit instruction to treat their contents as data only (prompt-injection defense)
   - Sends that prompt to `prompt_model()` (using whichever provider `CHAT_PROVIDER` selects) and returns the LLM's reply, plus the raw `skill_gaps` list
   - If the LLM call fails, falls back to a plain templated reply listing the gaps directly
2. If no `pdf_text`, wraps the message in the same `<Message>`-tagged prompt and calls `prompt_model()` for a plain conversational reply

### Frontend endpoints (`frontend/src/app.py`)

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the chat page (`chat_page.html`) |
| `/send` | POST | Receives `{message, pdf_text}` as JSON from the browser and proxies it to the backend's `/chat` |
| `/health` | GET | Returns `{"status": "ok"}` |

### Key JavaScript functions (`chat_page.html`)

- **`extractPDFText(file)`** — uses `pdf.js` to read every page of an uploaded PDF and concatenate its text, entirely in the browser. The raw PDF file is never uploaded to any server.
- **`addBubble(text, sender, attachmentName)`** — creates and appends a chat bubble (`user`, `bot`, or `error`) to the scrollable chat history.
- **`showTyping()` / `hideTyping()`** — shows/removes an animated "typing" indicator while waiting for a reply.
- **The form's `submit` handler** — reads the typed message, extracts PDF text if a new file is attached (otherwise reuses `activeResumeText`, the most recently uploaded resume's text — see below), `fetch()`s `POST /send` with the JSON payload, and renders the response (or a graceful error bubble on failure).
- **`activeResumeText`** (module-level variable) — holds the text of the most recently uploaded resume for the rest of the browser session. Updated only when a *new* file is uploaded; otherwise reused as-is on every subsequent message, which is what lets follow-up questions work without re-attaching the PDF each time.

### Docker network communication

Frontend and backend run in separate containers on a shared bridge network (`app-network` in `docker-compose.yml`). The **browser only ever talks to the frontend** (`localhost:8000`) — it never calls the backend directly. The frontend container reaches the backend using Docker's internal DNS, via the service name: `http://backend:8001`, set through the `BACKEND_URL` environment variable in `docker-compose.yml`.

---

## Data / Assumptions

### JSON message structure

```json
{
  "message": "string — user-typed text",
  "pdf_text": "string — extracted PDF content, omitted or empty if no PDF was attached"
}
```

Response:
```json
{
  "reply": "string — natural-language reply",
  "skill_gaps": ["array of strings — only populated when a resume was analyzed"]
}
```

### Data flow

```
User types a message / attaches a PDF
        |
        v
Browser (chat_page.html)
  - pdf.js extracts PDF text client-side, if a NEW file is attached
  - otherwise reuses activeResumeText (last uploaded resume, if any)
  - fetch() POSTs {message, pdf_text} as JSON to /send
        |
        v
Frontend (app.py) -- port 8000
  - /send forwards the JSON, unmodified, to BACKEND_URL/chat
        |
        v
Backend (app.py) -- port 8001
  - If pdf_text present: writes it to a temp file, calls find_skill_gaps()
    (always Gemini, regardless of CHAT_PROVIDER)
  - Builds a prompt (resume + message + gaps, tagged against injection)
  - Calls prompt_model() for the actual reply (Gemini or Ollama,
    depending on CHAT_PROVIDER)
        |
        v
Backend returns { "reply": "...", "skill_gaps": [...] }
        |
        v
Frontend relays the JSON back unmodified
        |
        v
Browser renders the reply as a bot chat bubble
```

### Assumptions

- PDF content is extracted entirely client-side before anything is sent. No raw PDF file is ever uploaded to either server.
- The resume and message are treated strictly as data inside the LLM prompt (`<Resume>`/`<Message>` tags with explicit instructions to ignore embedded directives) — a basic defense against prompt injection via resume content.
- The jobs database must have a populated `tech_stack` column for meaningful gap detection; jobs with a null/empty value are excluded from the comparison.
- **The frontend remembers only the single most recently uploaded resume, client-side, for the rest of the browser session** — not a full conversation history. The backend itself remains stateless: each `/chat` request is handled independently, with no server-side memory of anything. Uploading a second resume completely replaces the first in the browser's memory (there's no way to switch back to an earlier one without re-uploading it). Refreshing the page clears this entirely.
- The backend has no memory of what it previously *said* — only the frontend's re-sent `pdf_text` gives the appearance of continuity across messages.

### Constraints

- PDF size is capped at 10MB client-side (in `chat_page.html`); there's no server-side enforcement of this limit.
- Gemini's API has rate limits; during testing we hit a real `503 UNAVAILABLE` ("high demand") error from Google's servers, surfaced cleanly as an error string rather than a crash.
- Skill matching for the gap list happens through Gemini's own extraction, not exact string matching — but the no-LLM fallback path (used only if Gemini fails repeatedly) falls back to rigid substring matching, which can miss synonyms (e.g. `node.js` vs `nodejs`).
- The Docker secret for `GEMINI_API_KEY` must exist as a file at `secrets/gemini_api_key.txt` for `docker compose up` to start at all, even if you only intend to use the `.env` fallback value.

---

## Testing

### Frontend testing

| Test case | How to reproduce | Expected result |
|---|---|---|
| Send a plain message | Type a message, press Send | Bot bubble with a conversational reply |
| Send with no input | Press Send with an empty field and no PDF | A toast warning, no request sent |
| Upload a PDF | Click the upload icon, select a PDF, send | Text extracted client-side, sent with the message |
| Invalid file type | Select a non-PDF file | Toast: "Please upload a valid PDF file." |
| Oversized file | Select a PDF over 10MB | Toast: "PDF must be under 10 MB." |
| Backend unreachable | Stop the backend container, send a message | Red "error" bubble, not a crash |
| Follow-up after uploading a resume | Upload a resume, then send a message with no new file attached | The previously uploaded resume's text is still sent; the bot answers using it instead of asking you to re-attach |
| Upload a second, different resume | Upload resume A, then upload resume B and send | Subsequent replies (including follow-ups) are based on resume B; resume A is no longer referenced |

### Backend testing

Test `/chat` directly with `curl` (or `Invoke-RestMethod` on Windows PowerShell):

```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "pdf_text": ""}'
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/chat" -Method POST -ContentType "application/json" -Body '{"message": "hello"}'
```

Expected response shape:
```json
{"reply": "...", "skill_gaps": []}
```

### Testing the Ollama bonus

```powershell
# Confirm which provider is active inside the running container
docker compose exec backend env | findstr CHAT_PROVIDER

# Send a plain message and confirm the reply comes from whichever
# provider CHAT_PROVIDER currently points at
Invoke-RestMethod -Uri "http://127.0.0.1:8001/chat" -Method POST -ContentType "application/json" -Body '{"message": "hello"}'
```

Switch `CHAT_PROVIDER` in `.env` between `gemini` and `ollama`, recreate the backend (`docker compose up -d --force-recreate backend`), and repeat — confirms both providers are genuinely reachable, not just configured.

### Testing the Docker secrets bonus

```powershell
# Should print your real key
docker compose exec backend cat /run/secrets/gemini_api_key

# Should print NOTHING -- confirms the key isn't exposed as an env var
docker compose exec backend env | findstr GEMINI_API_KEY

# Should also show no GEMINI_API_KEY entry
docker inspect resume-backend
```

### Docker network communication test

With both containers running via `docker compose up`:

```bash
docker compose exec frontend curl http://backend:8001/health
```

Expected: `{"status":"ok"}` — confirms the frontend container can reach the backend container by its Docker service name over the shared network, not just by coincidence of both being reachable from the host machine.

You can also confirm the mounted database is actually present inside the backend container:

```bash
docker compose exec backend ls /app/src/week_2/data
```

---

## Limitations

- **No real conversation history** — the backend is fully stateless; only the frontend's `activeResumeText` gives the appearance of memory, and only for the single most recently uploaded resume (see [Data / Assumptions](#assumptions)). The bot has no memory of what it previously said, and refreshing the page loses everything.
- **No user authentication** — anyone with the URL can use the app.
- **Gemini dependency for resume analysis is hard** — `find_skill_gaps.py` only has a Gemini code path. Even with `CHAT_PROVIDER=ollama`, uploading a resume always requires a working `GEMINI_API_KEY` for the extraction step itself (the reply *around* that extraction does respect `CHAT_PROVIDER`). Without a working key, gap detection silently degrades to a fragile substring-matching fallback after ~12 seconds of failed retries, rather than failing outright.
- **Gemini rate limits / `503` errors** — confirmed during our own testing; the free tier can return `503 UNAVAILABLE` under high demand. The app surfaces this as a visible error message rather than crashing, but doesn't currently retry automatically.
- **No automated test suite** — testing so far has been manual (`curl`/`Invoke-RestMethod` plus browser testing), not unit or integration tests.
- **PDF extraction quality** — complex PDF layouts (multi-column, tables, scanned images) may extract poorly via `pdf.js`, since it reads raw text positions rather than understanding document structure.
- **Docker secrets file is required to exist** — `docker compose up` won't start at all if `secrets/gemini_api_key.txt` is missing, even for someone who only wants to use the plain `.env` fallback.

---

## Architecture Reflection

### Design Choices

The frontend and backend are split into two independent services because their responsibilities are genuinely different: the frontend's job is presentation and proxying (serve HTML, extract PDF text, remember the active resume, forward requests), while the backend's job is computation (call the LLM, query the database, build prompts). Keeping them separate means either side can change — a new UI, a different LLM provider, a different database — without the other needing to know.

The frontend deliberately never lets the browser talk to the backend directly. Every request goes through the frontend's own `/send` route first, which then reaches the backend over Docker's internal network using the service name (`http://backend:8001`).

The backend always sends the resume and the computed skill gaps to the LLM together, rather than just returning the raw gap list. An earlier version returned a fixed templated string built only from the gap list, never actually asking the LLM anything about the resume. Letting the LLM see both the resume and the gaps produces a much more natural, specific reply — and combined with the frontend remembering the active resume, it also means follow-up questions ("summarise it", "what's missing for a backend role specifically") work without re-uploading anything.

Both bonus features were deliberately kept *additive*, not replacements: `CHAT_PROVIDER` defaults to Gemini and the `ollama` Compose service is profile-gated, so neither bonus changes the default behavior of the mandatory setup. The Docker secret similarly falls back to `.env` if no secret file is present, rather than hard-requiring the new approach.

### Trade-offs

The main trade-off was Gemini versus a fully local model. Gemini gives noticeably better output quality and needs no local hardware, at the cost of an internet dependency and the rate limits/`503`s we hit firsthand during testing. Ollama is now genuinely usable as an alternative for conversational replies (`CHAT_PROVIDER=ollama`), but the resume-analysis extraction step remains Gemini-only — a deliberate scope boundary, not an oversight, since rebuilding that extraction logic around a local model would have been a much larger change to the Week 2 code.

The frontend's resume memory is a lightweight, client-side fix rather than real conversation history. It solves the specific, concrete problem of "why do I have to re-upload my resume for every follow-up question," without taking on the larger task of persistent, multi-resume, server-side session storage. That bigger version remains a documented improvement, not something silently skipped.

The Docker secret for the API key trades a small amount of setup friction (the file must exist for Compose to start) for a real reduction in *accidental* exposure via `docker inspect`. It deliberately doesn't try to be a full secrets-management solution (no encryption at rest, no access control) — that would be a different, heavier tool (Vault, AWS Secrets Manager) for a different context than a coursework project.

### Improvements

Given more time, the following would be worth doing:

- **Extend the Ollama path into `find_skill_gaps.py`** — add a `call_ollama()` extraction function so resume analysis doesn't hard-depend on Gemini, matching the "not Gemini" framing of the Ollama bonus task more completely.
- **Real, server-side conversation/session history** — replace the frontend's single-resume memory with a proper session store (even just SQLite), supporting multiple remembered resumes and the bot's own past replies.
- **Automatic retry on transient Gemini errors** — the `503` we encountered is usually temporary; a short backoff-and-retry would smooth over it without any user-visible failure.
- **Server-side PDF size limits** — the 10MB check currently only exists in the browser; a malicious or buggy client could bypass it.
- **Automated tests** — replace manual `curl`/browser testing with a real test suite (e.g. `pytest` + FastAPI's `TestClient`, which we already used informally during development to verify route logic with mocked LLM calls).