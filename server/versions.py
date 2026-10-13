"""Versions : snapshots avant chaque régénération IA, restauration, diff."""
import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .projects import load_script, save_script, project_dir

router = APIRouter(prefix="/api/projects/{pid}", tags=["versions"])


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def snapshot(pid: str, label: str, author: str = "user") -> dict:
    """Archive l'état courant (script + codes de scènes) avant modification."""
    d = project_dir(pid)
    vdir = d / "versions"
    vdir.mkdir(exist_ok=True)
    n = len(list(vdir.iterdir())) + 1
    v = vdir / f"{n:03d}"
    v.mkdir()
    shutil.copy(d / "script.json", v / "script.json")
    scenes_root = d / "scenes"
    if scenes_root.is_dir():
        shutil.copytree(scenes_root, v / "scenes", dirs_exist_ok=True)
    meta = {"n": n, "label": label, "author": author, "time": _now()}
    (v / "meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                 encoding="utf-8")
    return meta


@router.post("/versions")
def create_version(pid: str, body: dict):
    return snapshot(pid, body.get("label") or "manuel", body.get("author") or "user")


@router.get("/versions")
def list_versions(pid: str):
    vdir = project_dir(pid) / "versions"
    if not vdir.is_dir():
        return []
    out = []
    for v in sorted(vdir.iterdir()):
        mf = v / "meta.json"
        if mf.exists():
            out.append(json.loads(mf.read_text(encoding="utf-8")))
    return sorted(out, key=lambda m: -m["n"])


def _scene_code_snapshot(vdir: Path, index: int) -> str:
    f = vdir / "scenes" / f"{index:03d}" / "index.html"
    return f.read_text(encoding="utf-8") if f.exists() else ""


@router.get("/versions/diff")
def diff_versions(pid: str, a: int, b: int):
    """Diff ligne à ligne entre deux versions (script)."""
    vdir = project_dir(pid) / "versions"
    va, vb = vdir / f"{a:03d}", vdir / f"{b:03d}"
    for v in (va, vb):
        if not v.is_dir():
            raise HTTPException(404, "version introuvable")

    def read(p: Path):
        return (p / "script.json").read_text(encoding="utf-8").splitlines()

    la, lb = read(va), read(vb)
    import difflib
    diff = list(difflib.unified_diff(la, lb, fromfile=f"v{a}", tofile=f"v{b}",
                                     lineterm=""))
    return {"diff": "\n".join(diff[:400])}


@router.get("/versions/{n}")
def get_version(pid: str, n: int):
    v = project_dir(pid) / "versions" / f"{n:03d}"
    if not v.is_dir():
        raise HTTPException(404, "version introuvable")
    script = json.loads((v / "script.json").read_text(encoding="utf-8"))
    return {"meta": json.loads((v / "meta.json").read_text(encoding="utf-8")),
            "script": script}


@router.post("/versions/{n}/restore")
def restore_version(pid: str, n: int):
    v = project_dir(pid) / "versions" / f"{n:03d}"
    if not v.is_dir():
        raise HTTPException(404, "version introuvable")
    d = project_dir(pid)
    snapshot(pid, "avant restauration", "auto")
    shutil.copy(v / "script.json", d / "script.json")
    if (v / "scenes").is_dir():
        shutil.rmtree(d / "scenes", ignore_errors=True)
        shutil.copytree(v / "scenes", d / "scenes")
    return {"ok": True}
