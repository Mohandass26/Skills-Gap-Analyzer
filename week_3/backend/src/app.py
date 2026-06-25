import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from week_2.find_skill_gaps import find_skill_gaps
from week_2.prompt_model import prompt_model

# Load variables from a .env file (GEMINI_API_KEY, etc.) into the environment
load_dotenv()

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

# Where the jobs database lives: prefers jobs.db, falls back to jobs_d1.db
# (matches the same priority used inside week_2/find_skill_gaps.py).
# Override either path with JOBS_DB_PATH if you store it somewhere else.
_WEEK2_DATA_DIR = BASE_DIR / "week_2" / "data"
_DB_PATH_MAIN = _WEEK2_DATA_DIR / "jobs.db"
_DB_PATH_ALT = _WEEK2_DATA_DIR / "jobs_d1.db"
DB_PATH = os.getenv(
    "JOBS_DB_PATH",
    str(_DB_PATH_MAIN if _DB_PATH_MAIN.exists() else _DB_PATH_ALT),
)

# Model used for plain conversational replies (no resume attached).
# Must be a key from OLLAMA_MODELS or GEMINI_MODELS in week_2/prompt_model.py.
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")


class ChatRequest(BaseModel):
    message: str = ""
    pdf_text: str | None = None


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """
    If a resume (pdf_text) was attached, run the Week 2 skill-gap analysis
    against the jobs database and reply with the gaps found.
    Otherwise, treat it as a normal chat message and forward it to the LLM.
    """
    if payload.pdf_text and payload.pdf_text.strip():
        return _handle_resume(payload.pdf_text, payload.message)

    if not payload.message.strip():
        return ChatResponse(reply="Please type a message or attach your resume PDF.")

    answer = prompt_model(DEFAULT_MODEL, payload.message)
    return ChatResponse(reply=answer or "Sorry, I couldn't generate a response.")


def _handle_resume(pdf_text: str, message: str) -> ChatResponse:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(pdf_text)
            tmp_path = tmp.name

        result = find_skill_gaps(tmp_path, DB_PATH)
    finally:
        if tmp_path:
            os.unlink(tmp_path)

    if result.gaps:
        gap_list = ", ".join(result.gaps)
        reply = (
            "Based on your resume, here are skills that show up in job "
            f"postings but aren't in your resume: {gap_list}."
        )
    else:
        reply = "Your resume already covers the skills found in the job postings I checked!"

    if message.strip():
        reply += f'\n\n(You also asked: "{message.strip()}")'

    return ChatResponse(reply=reply)