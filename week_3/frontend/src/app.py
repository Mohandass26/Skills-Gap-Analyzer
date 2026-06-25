import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Load variables from a .env file (BACKEND_URL, etc.) into the environment
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# The backend's address. Defaults to the docker-compose service name;
# override in .env for local (non-Docker) runs, e.g. http://localhost:8001
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8001")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared async client for the lifetime of the app, instead of
    # opening/closing a new connection on every single request.
    app.state.http_client = httpx.AsyncClient(timeout=120.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="Resume Helper Frontend", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "chat_page.html", {})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/send")
async def send(request: Request):
    """
    Receives the chat message as plain JSON from the browser. Any PDF
    text has already been extracted client-side (via pdf.js) before this
    is called, so this route just forwards the payload straight to the
    backend's /chat endpoint -- no PDF parsing happens here.
    """
    payload = await request.json()

    client: httpx.AsyncClient = request.app.state.http_client
    try:
        response = await client.post(f"{BACKEND_URL}/chat", json=payload)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            {"error": f"Backend returned an error: {exc.response.status_code}"},
            status_code=502,
        )
    except httpx.RequestError as exc:
        return JSONResponse(
            {"error": f"Could not reach the backend: {exc}"},
            status_code=502,
        )