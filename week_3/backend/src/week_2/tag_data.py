import re
import sys
import json
import math
import time
import asyncio
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from google import genai
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

load_dotenv()

# ─── CONFIGURATION ───────────────────────────────────────────────────────────

GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
]

RATE_LIMITS_TXT = Path("./rate_limits.txt")
USAGE_STATE_PATH = Path("./usage_state.json")

AVG_DESC_TOKENS = 300
PROMPT_OVERHEAD = 150
MAX_BATCH_SIZE = 20

MAX_RETRIES_PER_MODEL = 2
BACKOFF_BASE_SECONDS = 2.0
MAX_BATCH_RETRIES = 4

TPM_SAFETY_MARGIN = 0.8  # only plan batches against 80% of TPM/RPM
RPD_SAFETY_MARGIN = 0.9  # stop using a model once 90% of its daily RPD is used

REGEX_FAST_PATH_ENABLED = True
REGEX_MIN_MATCHES = 2

FETCH_MULTIPLIER = 3
FETCH_BATCH_CAP = 60

# DB Path
DB_PATH = "data/jobs.db"
DB_PATH_ALT = "data/jobs_d1.db"

# VERBOSE = False keeps the console output minimal: just "Analyzed Job ..."
VERBOSE = False


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────


def main():
    db_url = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    asyncio.run(tag_data(db_url))


# ─── RATE LIMIT PARSING ──────────────────────────────────────────────────────


def _parse_num(s: str) -> int:
    s = s.strip().upper().replace(",", "")
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    if s.endswith("K"):
        return int(float(s[:-1]) * 1_000)
    return int(s)


def _parse_rate_limits(path: Path) -> dict:
    """
    File format, one model per line:  <model_name>  <RPM>  <TPM>  <RPD>
        gemini-2.5-flash        5    250000   20
        gemini-3.1-flash-lite   15   250K     500
    """
    limits = {}
    if not path.exists():
        return limits
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        model, rpm_s, tpm_s, rpd_s = parts[:4]
        limits[model] = {
            "rpm": _parse_num(rpm_s),
            "tpm": _parse_num(tpm_s),
            "rpd": _parse_num(rpd_s),
        }
    return limits


# ─── DAILY USAGE TRACKING ────────────────────────────────────────────────────


def _load_usage() -> dict:
    if not USAGE_STATE_PATH.exists():
        return {}
    try:
        return json.loads(USAGE_STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _save_usage(usage: dict):
    USAGE_STATE_PATH.write_text(json.dumps(usage))


def _requests_today(usage: dict, model: str) -> int:
    return usage.get(str(date.today()), {}).get(model, 0)


def _record_request(usage: dict, model: str):
    today = usage.setdefault(str(date.today()), {})
    today[model] = today.get(model, 0) + 1
    _save_usage(usage)


def _mark_exhausted(usage: dict, model: str, rpd):
    today = usage.setdefault(str(date.today()), {})
    today[model] = rpd if rpd is not None else today.get(model, 0) + 1
    _save_usage(usage)


# ─── MODEL SELECTION & BATCH SIZING ──────────────────────────────────────────


def _select_model(limits: dict, usage: dict):
    """Returns the next usable Gemini model name, or None if every model's
    daily quota is used up. Stops using a model once RPD_SAFETY_MARGIN of
    its daily cap is reached, keeping a small reserve instead of riding the
    quota to the exact edge."""
    for model in GEMINI_MODELS:
        rpd = limits.get(model, {}).get("rpd")
        if rpd is None:
            return model
        safe_cap = max(1, math.floor(rpd * RPD_SAFETY_MARGIN))
        if _requests_today(usage, model) < safe_cap:
            return model
    return None


def _batch_params(limits: dict, model: str):
    m = limits.get(model, {})
    tpm = m.get("tpm", 250_000)
    rpm = m.get("rpm", 5)
    safe_tpm = tpm * TPM_SAFETY_MARGIN
    safe_rpm = max(1, math.floor(rpm * TPM_SAFETY_MARGIN))
    est_tokens_per_job = AVG_DESC_TOKENS + PROMPT_OVERHEAD
    batch_size = max(
        1, min(math.floor(safe_tpm / est_tokens_per_job), safe_rpm, MAX_BATCH_SIZE)
    )
    retry_delay = math.ceil(60 / rpm) if rpm else 6.0
    return batch_size, float(retry_delay)


# ─── PROMPT BUILDING ─────────────────────────────────────────────────────────

_PROMPT_HEADER = [
    "You are a technical recruiter assistant.",
    "For each job listed below, extract its tech stack: the specific",
    "programming languages, frameworks, libraries, tools, platforms, and",
    "methodologies mentioned or clearly implied by the title, company, or description.",
    "",
    "Reply with ONLY one line per job, in exactly this format, and nothing else",
    "(no headers, no markdown, no explanation):",
    "<source_id>: <tag1>, <tag2>, <tag3>",
    "",
    "Rules:",
    "- Tags must be specific tools, languages, or frameworks (e.g. Python, React, MySQL) —",
    "  not generic categories (e.g. 'Programming Language', 'Database').",
    "- Comma-separated. No duplicates, no brackets, no quotes, no markdown.",
    "- If a description is vague but hints at a common stack (e.g. 'web development'",
    "  implies JavaScript, HTML, CSS), make your best reasonable guess — a guess is",
    "  better than leaving a job blank.",
    "- Every source_id below must appear exactly once in your reply, in any order.",
    "",
    "Example:",
    "91397216: Python, SQL, MySQL, MariaDB, Tableau, A/B testing",
    "91347112: Java, Spring Boot, Docker, Kubernetes",
    "",
    "--- JOBS START HERE ---",
]


def _build_prompt(jobs: list) -> str:
    lines = list(_PROMPT_HEADER)
    for job in jobs:
        desc = (job.get("description") or "").replace("\n", " ").strip()
        lines.append(
            f"[{job['source_id']}] {job.get('job_title', '')} @ {job.get('company', '')}\n"
            f"Description: {desc}\n---"
        )
    return "\n".join(lines)


# ─── RESPONSE PARSING ────────────────────────────────────────────────────────


def _parse_response(raw: str, expected_ids: list) -> dict:
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        sid, _, tags = line.partition(":")
        sid = sid.strip().strip("[]\"' ")
        if sid in expected_ids:
            result[sid] = tags.strip().strip("[]\"', ")
    return result


# ─── REGEX FAST PATH ─────────────────────────────────────────────────────────

_TECH_PATTERNS = [
    (re.compile(r"\bPython\b", re.I), "Python"),
    (re.compile(r"\bJava(?!Script)\b", re.I), "Java"),
    (re.compile(r"\bJavaScript\b", re.I), "JavaScript"),
    (re.compile(r"\bTypeScript\b", re.I), "TypeScript"),
    (re.compile(r"C\+\+", re.I), "C++"),
    (re.compile(r"\bC#", re.I), "C#"),
    (re.compile(r"\bGolang\b", re.I), "Go"),
    (re.compile(r"\bRust\b", re.I), "Rust"),
    (re.compile(r"\bRuby\b", re.I), "Ruby"),
    (re.compile(r"\bPHP\b", re.I), "PHP"),
    (re.compile(r"\bSwift\b", re.I), "Swift"),
    (re.compile(r"\bKotlin\b", re.I), "Kotlin"),
    (re.compile(r"\bScala\b", re.I), "Scala"),
    (re.compile(r"\bSQL\b", re.I), "SQL"),
    (re.compile(r"\bHTML5?\b", re.I), "HTML"),
    (re.compile(r"\bCSS3?\b", re.I), "CSS"),
    (re.compile(r"\bReact(?:\.js)?\b", re.I), "React"),
    (re.compile(r"\bAngular\b", re.I), "Angular"),
    (re.compile(r"\bVue(?:\.js)?\b", re.I), "Vue"),
    (re.compile(r"\bDjango\b", re.I), "Django"),
    (re.compile(r"\bFlask\b", re.I), "Flask"),
    (re.compile(r"\bFastAPI\b", re.I), "FastAPI"),
    (re.compile(r"\bSpring ?Boot\b", re.I), "Spring Boot"),
    (re.compile(r"\bNode(?:\.js|JS)?\b", re.I), "Node.js"),
    (re.compile(r"\bExpress(?:\.js)?\b", re.I), "Express"),
    (re.compile(r"\bNext\.js\b", re.I), "Next.js"),
    (re.compile(r"\bTensorFlow\b", re.I), "TensorFlow"),
    (re.compile(r"\bPyTorch\b", re.I), "PyTorch"),
    (re.compile(r"\bPandas\b", re.I), "Pandas"),
    (re.compile(r"\bNumPy\b", re.I), "NumPy"),
    (re.compile(r"\bscikit-learn\b", re.I), "scikit-learn"),
    (re.compile(r"\bMySQL\b", re.I), "MySQL"),
    (re.compile(r"\bPostgre(?:s|SQL)\b", re.I), "PostgreSQL"),
    (re.compile(r"\bMongoDB\b", re.I), "MongoDB"),
    (re.compile(r"\bRedis\b", re.I), "Redis"),
    (re.compile(r"\bMariaDB\b", re.I), "MariaDB"),
    (re.compile(r"\bOracle\b", re.I), "Oracle"),
    (re.compile(r"\bSQLite\b", re.I), "SQLite"),
    (re.compile(r"\bDynamoDB\b", re.I), "DynamoDB"),
    (re.compile(r"\bSnowflake\b", re.I), "Snowflake"),
    (re.compile(r"\bBigQuery\b", re.I), "BigQuery"),
    (re.compile(r"\bAWS\b", re.I), "AWS"),
    (re.compile(r"\bAzure\b", re.I), "Azure"),
    (re.compile(r"\bGCP\b|\bGoogle Cloud\b", re.I), "GCP"),
    (re.compile(r"\bDocker\b", re.I), "Docker"),
    (re.compile(r"\bKubernetes\b|\bK8s\b", re.I), "Kubernetes"),
    (re.compile(r"\bTerraform\b", re.I), "Terraform"),
    (re.compile(r"\bJenkins\b", re.I), "Jenkins"),
    (re.compile(r"\bCI/CD\b", re.I), "CI/CD"),
    (re.compile(r"\bGitHub\b", re.I), "GitHub"),
    (re.compile(r"\bGitLab\b", re.I), "GitLab"),
    (re.compile(r"\bGit\b", re.I), "Git"),
    (re.compile(r"\bExcel\b", re.I), "Excel"),
    (re.compile(r"\bPowerPoint\b", re.I), "PowerPoint"),
    (re.compile(r"\bTableau\b", re.I), "Tableau"),
    (re.compile(r"\bPower ?BI\b", re.I), "Power BI"),
    (re.compile(r"\bJira\b", re.I), "Jira"),
    (re.compile(r"\bLinux\b", re.I), "Linux"),
    (re.compile(r"\bBash\b", re.I), "Bash"),
]


def _regex_extract(description: str) -> list:
    """Single regex pass over a job description, returning the well-known
    tech terms it finds (display-cased, de-duplicated, in first-seen order).
    Returns [] if nothing matches — callers fall through to the LLM."""
    if not description:
        return []
    found, seen = [], set()
    for pattern, display in _TECH_PATTERNS:
        if display not in seen and pattern.search(description):
            found.append(display)
            seen.add(display)
    return found


def _chunked(items: list, size: int):
    size = max(1, size)
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ─── MODEL CALLS (Gemini) ────────────────────────────────────────────────────

_gemini_client_cache = None


def _get_gemini_client():
    global _gemini_client_cache
    if _gemini_client_cache is None:
        _gemini_client_cache = genai.Client()
    return _gemini_client_cache


def _estimate_tokens(prompt: str, text: str) -> int:
    # Rough fallback when a model doesn't report real usage: ~4 tokens/word.
    return (len(prompt.split()) + len(text.split())) * 4


async def _call_model(model: str, prompt: str) -> tuple[str, int]:
    client = _get_gemini_client()
    response = await client.aio.models.generate_content(model=model, contents=prompt)
    text = response.text

    usage = getattr(response, "usage_metadata", None)
    total = getattr(usage, "total_token_count", None) if usage else None
    tokens_used = total if total is not None else _estimate_tokens(prompt, text)
    return text, tokens_used


async def _call_with_fallback(prompt: str, limits: dict, usage: dict):
    """
    Calls the best available Gemini model. If a model keeps failing (or its
    daily quota is hit), marks it exhausted for today and cascades to the
    next Gemini model instead of giving up outright.

    Returns (text, model_name, tokens_used). On total failure, returns
    (None, None, 0).
    """
    fail_counts = {}
    for _ in range(MAX_BATCH_RETRIES):
        model = _select_model(limits, usage)
        if model is None:
            print("  No model available (Gemini quota used up) — skipping.")
            return None, None, 0
        try:
            text, tokens_used = await _call_model(model, prompt)
            _record_request(usage, model)
            return text, model, tokens_used
        except Exception as e:
            fail_counts[model] = fail_counts.get(model, 0) + 1
            print(
                f"  [{model}] failed ({fail_counts[model]}/{MAX_RETRIES_PER_MODEL}): {e}"
            )
            if fail_counts[model] >= MAX_RETRIES_PER_MODEL:
                rpd = limits.get(model, {}).get("rpd")
                _mark_exhausted(usage, model, rpd)
                print(
                    f"  [{model}] giving up on this model for today, trying the next one..."
                )
            else:
                await asyncio.sleep(BACKOFF_BASE_SECONDS ** fail_counts[model])
    return None, None, 0


# ─── MCP HELPERS ─────────────────────────────────────────────────────────────


def _extract_tool_result(call_tool_result):
    if call_tool_result is None:
        return None
    data = getattr(call_tool_result, "data", None)
    if data is not None:
        return data
    content = getattr(call_tool_result, "content", None)
    if content:
        for block in content:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
    return None


# ─── CORE TAG_DATA ───────────────────────────────────────────────────────────


async def tag_data(db_url: str):
    start_time = time.perf_counter()
    total_tokens = 0
    regex_resolved_count = 0
    source_of = {}  # source_id -> "regex" / model name
    source_counts = {}  # source label -> how many jobs it actually tagged

    transport = PythonStdioTransport("db_server.py", args=[db_url])
    mcp_client = Client(transport)

    limits = _parse_rate_limits(RATE_LIMITS_TXT)
    usage = _load_usage()

    rows_updated = 0
    round_num = 0

    async with mcp_client:
        while True:
            count_result = await mcp_client.call_tool("count_untagged_jobs", {})
            total_untagged = (_extract_tool_result(count_result) or {}).get(
                "untagged_count", 0
            )
            if total_untagged == 0:
                break

            model = _select_model(limits, usage)
            if model is None:
                print("No usable model left (Gemini quota used up) — stopping.")
                break
            llm_batch_size, retry_delay = _batch_params(limits, model)

            fetch_size = min(llm_batch_size * FETCH_MULTIPLIER, FETCH_BATCH_CAP)
            fetch_result = await mcp_client.call_tool(
                "get_untagged_jobs", {"limit": fetch_size, "offset": 0}
            )
            pool = _extract_tool_result(fetch_result) or []
            if not pool:
                break

            # --- Regex fast path: resolve what we can without the LLM ---
            parsed = {}
            needs_llm = []
            if REGEX_FAST_PATH_ENABLED:
                for job in pool:
                    terms = _regex_extract(job.get("description") or "")
                    if len(terms) >= REGEX_MIN_MATCHES:
                        sid = str(job["source_id"])
                        parsed[sid] = ", ".join(terms)
                        source_of[sid] = "regex"
                    else:
                        needs_llm.append(job)
            else:
                needs_llm = pool
            regex_resolved_count += len(parsed)

            if VERBOSE:
                print(
                    f"\n[Round {round_num}] pulled {len(pool)} jobs ({total_untagged} left) — "
                    f"{len(parsed)} resolved by regex, {len(needs_llm)} need {model}"
                )

            # --- LLM path: only the jobs regex couldn't resolve, chunked to
            # stay within this model's rate-limit-safe batch size ---
            round_tokens = 0
            for chunk_num, chunk in enumerate(_chunked(needs_llm, llm_batch_size)):
                remaining = chunk
                for _ in range(MAX_RETRIES_PER_MODEL + 1):
                    if not remaining:
                        break
                    expected_ids = [str(j["source_id"]) for j in remaining]
                    prompt = _build_prompt(remaining)
                    raw, used_model, tokens_used = await _call_with_fallback(
                        prompt, limits, usage
                    )
                    round_tokens += tokens_used
                    if raw is None:
                        break
                    llm_parsed = _parse_response(raw, expected_ids)
                    parsed.update(llm_parsed)
                    label = used_model
                    for sid in llm_parsed:
                        source_of[sid] = label
                    remaining = [
                        j for j in remaining if str(j["source_id"]) not in parsed
                    ]
                    if not remaining:
                        break
                    if VERBOSE:
                        print(
                            f"  [Round {round_num} chunk {chunk_num}] {used_model}: "
                            f"still missing {len(remaining)}/{len(chunk)} — retrying just those..."
                        )
                    await asyncio.sleep(retry_delay)
            total_tokens += round_tokens
            if VERBOSE:
                print(f"  [Round {round_num}] tokens used: {round_tokens}")

            for job in pool:
                sid = str(job["source_id"])
                stack = parsed.get(sid, "")
                if not stack:
                    if VERBOSE:
                        print(f"  Job {sid}: no tech stack extracted (skipping).")
                    continue
                update_result = await mcp_client.call_tool(
                    "update_tech_stack",
                    {"source_id": job["source_id"], "tech_stack": stack},
                )
                result_data = _extract_tool_result(update_result) or {}
                if result_data.get("success", True):
                    label = source_of.get(sid, "unknown")
                    suffix = f"   [{label}]" if VERBOSE else ""
                    print(f"Analyzed Job {sid}: {stack}{suffix}")
                    source_counts[label] = source_counts.get(label, 0) + 1
                    rows_updated += 1

            round_num += 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    if rows_updated == 0:
        print("No data to tag")
    elif VERBOSE:
        breakdown = ", ".join(
            f"{label}: {n}" for label, n in sorted(source_counts.items())
        )
        print(
            f"\nDone. Updated {rows_updated} job(s) across {round_num} round(s) "
            f"({regex_resolved_count} resolved without the LLM)."
        )
        print(f"Tagged by — {breakdown}")
    print(f"Total tokens used: {total_tokens}, took {elapsed_ms:.3f}ms")


if __name__ == "__main__":
    main()
