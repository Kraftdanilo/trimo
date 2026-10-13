"""HyperFrames — serveur FastAPI.

À partir d'un script ou d'une idée : génère des scènes HTML/CSS/JS animées
(IA), synthétise une voix off (edge-tts), permet l'édition complète dans une
interface web, et exporte une vidéo MP4 (Playwright + ffmpeg).
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import router as ai_router
from .projects import router as projects_router
from .scenes import router as scenes_router
from .tts import router as tts_router, voices_router as tts_voices_router
from .render import router as render_router
from .assets import router as assets_router
from .versions import router as versions_router
from .script import SCRIPT_ROUTER as script_router

app = FastAPI(title="HyperFrames", version="0.1.0")

API = Path(__file__).resolve().parent
ROOT = API.parent
WEB = ROOT / "web"

app.include_router(ai_router)
app.include_router(projects_router)
app.include_router(scenes_router)
app.include_router(tts_router)
app.include_router(tts_voices_router)
app.include_router(render_router)
app.include_router(assets_router)
app.include_router(versions_router)
app.include_router(script_router)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
