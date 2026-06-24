from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(request, "chat_page.html", {})