from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Set, Tuple

from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading is a convenience, not a hard requirement


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "jobs_d1.db"
DB_PATH_ALT = BASE_DIR / "data" / "job.db"
CV_PATH = BASE_DIR / "data" / "resume_d3.txt"

GEMINI_MODELS = ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
MODEL = os.getenv("SKILL_GAP_MODEL", GEMINI_MODELS[0])

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 4.0

CACHE_PATH = BASE_DIR / "skill_gap_cache.json"

CERT_PATTERN = re.compile(r"\bcertifi(ed|cation)\b", re.IGNORECASE)
SOFT_SKILLS = {
    "leadership", "management", "communication", "teamwork", "collaboration",
    "problem solving", "problem-solving", "time management", "mentoring",
    "mentorship", "adaptability", "creativity", "critical thinking",
}


class SkillGapResult(BaseModel):
    gaps: List[str]
    tokens: int
    time: float


# ─── Deterministic Skill-String Parsing ────────────────────────────────────

def is_certification(skill: str) -> bool:
    return bool(CERT_PATTERN.search(skill))


def is_soft_skill(skill: str) -> bool:
    return skill in SOFT_SKILLS


def parse_skills(text: str) -> Set[str]:
    """Split a skill string ('AWS/Azure/GCP', comma/newline separated,
    etc.) into individual lowercase skills. Protects 'a/b testing' and
    'ci/cd' from the '/' split, and drops certifications / soft skills."""
    if not text:
        return set()

    text = text.lower()
    text = text.replace("a/b testing", "ab_testing")
    text = text.replace("ci/cd", "ci_cd")

    skills: Set[str] = set()
    for chunk in text.replace("\n", ",").split(","):
        for part in chunk.split("/"):
            skill = part.strip().replace("ab_testing", "a/b testing").replace("ci_cd", "ci/cd")
            if skill and not is_certification(skill) and not is_soft_skill(skill):
                skills.add(skill)

    # Direct-match protection: 'C/C++' in the source text must register as
    # BOTH 'c' and 'c++', not just whichever the split happens to favor.
    if "c/c++" in text:
        skills.add("c")
        skills.add("c++")

    return skills


def skill_in_resume_text(skill: str, resume_lower: str) -> bool:
    """Direct/exact boundary-safe substring check -- used as the fallback
    path if Gemini is unavailable."""
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(skill).replace(r"\ ", r"\s+") + r"(?![a-z0-9])", re.IGNORECASE)
    return bool(pattern.search(resume_lower))


# ─── Gemini Call + Token Accounting ────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """4 tokens/word -- used only when Gemini doesn't return real usage counts."""
    return len(text.split()) * 4


def call_gemini(prompt: str) -> Tuple[str, int]:
    """Returns (response_text, total_tokens_used). Raises on failure.
    Relies on GEMINI_API_KEY / GOOGLE_API_KEY being set (e.g. via .env +
    load_dotenv()) -- genai.Client() picks it up automatically."""
    from google import genai

    client = genai.Client()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": 0},
    )
    text = response.text or ""

    usage = response.usage_metadata
    if usage is not None and usage.prompt_token_count is not None:
        total_tokens = usage.prompt_token_count + (usage.candidates_token_count or estimate_tokens(text))
    else:
        total_tokens = estimate_tokens(prompt) + estimate_tokens(text)

    return text, total_tokens


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(cache))
    except OSError:
        pass


def extract_resume_skills(resume_content: str) -> Tuple[Set[str], int, bool]:
    """
    Extracts technical skills from free-form resume text via Gemini.
    Returns (skills, tokens_used, success). On repeated failure, success
    is False and the caller falls back to direct-match checks instead.

    Cached by a hash of (model, resume content), so re-running on the same
    resume reuses the cached result -- this is what keeps results
    identical across consecutive runs.
    """
    cache = _load_cache()
    key = hashlib.sha256((MODEL + resume_content).encode("utf-8")).hexdigest()
    if key in cache:
        return set(cache[key]), 0, True

    prompt = f"""\
Extract only technical skills explicitly written in the resume below.

Rules:
- Return ONLY skills found in the resume text.
- Do not infer or add skills that aren't explicitly written.
- Do not include soft skills (e.g. leadership, communication).
- Do not include certifications.
- Return comma-separated values only, nothing else.
- If no technical skills are found, return an empty string.

Resume:
{resume_content[:6000]}
"""

    attempt = 0
    while True:
        try:
            response_text, tokens_used = call_gemini(prompt)
            skills = parse_skills(response_text)
            cache[key] = sorted(skills)
            _save_cache(cache)
            return skills, tokens_used, True
        except Exception as e:
            attempt += 1
            if attempt > MAX_RETRIES:
                print(f"Gemini extraction failed after {attempt - 1} retries ({e}); "
                      f"falling back to direct-match checks against the resume text.")
                return set(), 0, False
            time.sleep(RETRY_DELAY_SECONDS)


# ─── Main Entry Point ───────────────────────────────────────────────────────

def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    start = time.perf_counter()
    db_path = Path(db_url)
    cv_path = Path(input_file_path)

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        return SkillGapResult(gaps=[], tokens=0, time=round(time.perf_counter() - start, 2))

    if not cv_path.exists():
        print(f"Error: Resume file not found: {cv_path}")
        return SkillGapResult(gaps=[], tokens=0, time=round(time.perf_counter() - start, 2))

    try:
        resume_content = cv_path.read_text(encoding="utf-8")
        resume_skills, tokens_used, llm_ok = extract_resume_skills(resume_content)

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND TRIM(tech_stack) != ''"
        )
        rows = cur.fetchall()
        conn.close()

        required_skills: Set[str] = set()
        for (tech_stack,) in rows:
            required_skills.update(parse_skills(tech_stack))

        if llm_ok:
            gaps = sorted(required_skills - resume_skills)
        else:
            resume_lower = resume_content.lower()
            gaps = sorted(s for s in required_skills if not skill_in_resume_text(s, resume_lower))

        return SkillGapResult(gaps=gaps, tokens=tokens_used, time=round(time.perf_counter() - start, 2))

    except Exception as e:
        print(f"Error while finding skill gaps: {e}")
        return SkillGapResult(gaps=[], tokens=0, time=round(time.perf_counter() - start, 2))


if __name__ == "__main__":
    cv_arg = sys.argv[1] if len(sys.argv) > 1 else str(CV_PATH)
    db_arg = sys.argv[2] if len(sys.argv) > 2 else str(DB_PATH if DB_PATH.exists() else DB_PATH_ALT)

    result = find_skill_gaps(cv_arg, db_arg)
    print(f"gaps={result.gaps} time={result.time} tokens={result.tokens}")