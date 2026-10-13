"""Assets : upload d'images/vidéos/musiques/logos, bibliothèque par projet."""
import base64
import binascii
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .projects import project_dir

router = APIRouter(prefix="/api/projects/{pid}", tags=["assets"])

ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "svg",
           "mp4", "webm", "mp3", "wav", "ogg"}
MAX_ASSET_BYTES = 50 * 1024 * 1024      # 50 Mo


def decode_b64(data_b64: str) -> bytes:
    """Décodage base64 validé (rejette entrée malformée et tailles excessives)."""
    try:
        raw = base64.b64decode(data_b64, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "payload base64 invalide")
    if not raw:
        raise HTTPException(400, "payload vide")
    if len(raw) > MAX_ASSET_BYTES:
        raise HTTPException(413, "fichier trop volumineux (> 50 Mo)")
    return raw


@router.get("/assets")
def list_assets(pid: str):
    d = project_dir(pid) / "assets"
    d.mkdir(exist_ok=True)
    return sorted(f.name for f in d.iterdir() if f.is_file())


class AssetIn(BaseModel):
    name: str
    data_b64: str


@router.post("/assets")
def upload_asset(pid: str, body: AssetIn):
    name = re.sub(r"[^\w.\-]", "_", body.name).strip()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise HTTPException(400, f"extension non autorisée : {ext or 'aucune'}")
    d = project_dir(pid) / "assets"
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(decode_b64(body.data_b64))
    return {"ok": True, "name": name}


@router.get("/assets/{name}")
def get_asset(pid: str, name: str):
    name = re.sub(r"[^\w.\-]", "_", name)
    f = project_dir(pid) / "assets" / name
    if not f.exists():
        raise HTTPException(404, "asset introuvable")
    return FileResponse(f)


class ReplaceBody(BaseModel):
    old: str
    new: str


@router.post("/assets/replace")
def replace_asset(pid: str, body: ReplaceBody):
    """Remplace un asset partout : copie le contenu de `new` sous le nom `old`."""
    d = project_dir(pid) / "assets"
    src = d / re.sub(r"[^\w.\-]", "_", body.new)
    dst = d / re.sub(r"[^\w.\-]", "_", body.old)
    if not src.exists():
        raise HTTPException(404, "asset source introuvable")
    dst.write_bytes(src.read_bytes())
    return {"ok": True}


@router.delete("/assets/{name}")
def delete_asset(pid: str, name: str):
    f = project_dir(pid) / "assets" / re.sub(r"[^\w.\-]", "_", name)
    if f.exists():
        f.unlink()
    return {"ok": True}
