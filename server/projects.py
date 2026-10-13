"""Gestion des projets : projects/{id}/ avec script.json, scenes/, audio/, versions/."""
import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects", tags=["projects"])

ROOT = Path(__file__).resolve().parents[1] / "projects"


def project_dir(pid: str) -> Path:
    if not pid or any(c in pid for c in "/\\.."):
        raise HTTPException(400, "id de projet invalide")
    d = ROOT / pid
    if not d.is_dir():
        raise HTTPException(404, f"projet « {pid} » introuvable")
    return d


def load_script(pid: str) -> dict:
    f = project_dir(pid) / "script.json"
    if not f.exists():
        raise HTTPException(404, "script.json manquant")
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        raise HTTPException(500, "script.json corrompu")


def save_script(pid: str, script: dict) -> None:
    d = project_dir(pid)
    (d / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")


def scene_dir(pid: str, index: int) -> Path:
    """Dossier de la scène — sans création : les lectures ne doivent pas
    avoir d'effet de bord (les écritures font leur propre mkdir)."""
    return project_dir(pid) / "scenes" / f"{index:03d}"


def renumber_scenes(pid: str, from_index: int) -> None:
    """Après insertion/suppression : décale scenes/{idx} au-delà de from_index."""
    d = project_dir(pid)
    scenes_root = d / "scenes"
    if not scenes_root.is_dir():
        return
    dirs = sorted(p for p in scenes_root.iterdir() if p.is_dir() and p.name.isdigit())
    for p in reversed([p for p in dirs if int(p.name) >= from_index]):
        target = scenes_root / f"{int(p.name) + 1:03d}"
        if target.exists():
            shutil.rmtree(target)
        p.rename(target)


class ProjectIn(BaseModel):
    name: str = "nouveau_projet"


@router.get("")
def list_projects():
    ROOT.mkdir(exist_ok=True)
    items = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        sf = d / "script.json"
        meta = {"id": d.name, "scenes": 0, "title": d.name}
        if sf.exists():
            try:
                s = json.loads(sf.read_text(encoding="utf-8"))
                meta["title"] = s.get("title") or d.name
                meta["scenes"] = len(s.get("scenes") or [])
            except ValueError:
                pass
        items.append(meta)
    return items


@router.post("")
def create_project(body: ProjectIn):
    ROOT.mkdir(exist_ok=True)
    pid = uuid.uuid4().hex[:12]
    d = ROOT / pid
    d.mkdir()
    (d / "scenes").mkdir()
    (d / "audio").mkdir()
    (d / "versions").mkdir()
    (d / "assets").mkdir()
    script = {
        "title": body.name or "Nouveau projet",
        "description": "",
        "language": "fr",
        "style": {
            "primary": "#7C5CFF", "secondary": "#0E0E12",
            "font": "Inter", "background": "#0E0E12",
            "aspect": "16:9", "resolution": 1080, "fps": 30,
        },
        "voice": {"name": "fr-FR-HenriNeural", "rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
        "subtitle_style": {"enabled": True, "size": 5, "position": "bottom",
                           "color": "#FFFFFF", "outline": True, "background": True},
        "scenes": [],
    }
    save_script(pid, script)
    return {"id": pid, "script": script}


@router.get("/{pid}")
def get_project(pid: str):
    return {"id": pid, "script": load_script(pid)}


@router.put("/{pid}/script")
def update_script(pid: str, script: dict):
    cur = load_script(pid)
    script.setdefault("title", cur.get("title", ""))
    save_script(pid, script)
    return {"ok": True}


@router.delete("/{pid}")
def delete_project(pid: str):
    d = project_dir(pid)
    shutil.rmtree(d)
    return {"ok": True}


@router.get("/{pid}/export")
def export_project(pid: str):
    """Export .zip de tout le projet (script, scènes, audio, versions, rendus)."""
    import tempfile
    d = project_dir(pid)
    tmp = Path(tempfile.gettempdir()) / f"hf_{pid}.zip"
    if tmp.exists():
        tmp.unlink()
    shutil.make_archive(str(tmp.with_suffix("")), "zip", d)
    return FileResponse(tmp.with_suffix(".zip"), filename=f"hyperframes_{pid}.zip")
