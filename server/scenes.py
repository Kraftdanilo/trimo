"""Endpoints scènes : code HTML/CSS/JS par scène, régénération IA, validation."""
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .ai import load_config, llm_complete, HTTPException as AIHTTP
from .projects import load_script, save_script, project_dir, scene_dir
from .prompts import CODE_PROMPT, REGENERATE_TEXT, REGENERATE_CODE

router = APIRouter(prefix="/api/projects/{pid}", tags=["scenes"])

DIMENSIONS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080),
              "4:5": (1080, 1350)}


def scene_files(pid: str, index: int):
    d = scene_dir(pid, index)
    return d / "index.html", d / "style.css", d / "script.js"


def split_scene_html(html: str):
    """Découpe un document autonome en 3 fichiers (html / css / js).

    Les <style> et <script> inline sont extraits ; les <script src="…">
    (références externes) restent dans le HTML. re.sub réécrit depuis la
    chaîne originale : modifier html dans une boucle finditer corromprait
    le document dès le 2e bloc script.
    """
    style = ""
    m = re.search(r"<style[^>]*>([\s\S]*?)</style>", html, re.I)
    if m:
        style = m.group(1).strip()
        html = html[:m.start()] + html[m.end():]

    scripts = []

    def _grab(m: "re.Match") -> str:
        if re.search(r"\bsrc\s*=", m.group(0), re.I):
            return m.group(0)          # script externe : on garde la référence
        scripts.append(m.group(1).strip())
        return ""

    html = re.sub(r"<script[^>]*>([\s\S]*?)</script>", _grab, html, flags=re.I)
    html = re.sub(r"\n{3,}", "\n\n", html).strip()
    js = "\n\n".join(s for s in scripts if s)
    return html, style, js


def combine_scene_html(pid: str, index: int) -> str:
    """Recombine html+css+js en document autonome (rendu + prévisualisation)."""
    fh, fc, fs = scene_files(pid, index)
    html = fh.read_text(encoding="utf-8") if fh.exists() else ""
    css = fc.read_text(encoding="utf-8") if fc.exists() else ""
    js = fs.read_text(encoding="utf-8") if fs.exists() else ""
    if "</head>" in html.lower():
        i = html.lower().index("</head>")
        html = html[:i] + f"<style>{css}</style>" + html[i:]
    else:
        html += f"<style>{css}</style>"
    if "</body>" in html.lower():
        i = html.lower().index("</body>")
        html = html[:i] + f"<script>{js}</script>" + html[i:]
    else:
        html += f"<script>{js}</script>"
    return html


def _extract_html(raw: str) -> str | None:
    """Secours : extrait le document HTML brut quand le JSON est tronqué/illisible."""
    m = re.search(r"<!DOCTYPE\s+html|<html[\s>]", raw, re.I)
    if not m:
        return None
    end = raw.lower().rfind("</html>")
    if end == -1:
        return None
    return raw[m.start():end + len("</html>")]


def write_scene_code(pid: str, index: int, html: str) -> None:
    h, c, j = split_scene_html(html)
    fh, fc, fs = scene_files(pid, index)
    fh.parent.mkdir(parents=True, exist_ok=True)
    fh.write_text(h, encoding="utf-8")
    fc.write_text(c, encoding="utf-8")
    fs.write_text(j, encoding="utf-8")


def read_scene_code(pid: str, index: int):
    fh, fc, fs = scene_files(pid, index)
    return {
        "html": fh.read_text(encoding="utf-8") if fh.exists() else "",
        "css": fc.read_text(encoding="utf-8") if fc.exists() else "",
        "js": fs.read_text(encoding="utf-8") if fs.exists() else "",
    }


class SceneIn(BaseModel):
    text: str | None = None
    duration: float | None = None
    visual_prompt: str | None = None
    locked: bool | None = None
    silence: bool | None = None


@router.get("/scenes/{index}/code")
def get_code(pid: str, index: int):
    return read_scene_code(pid, index)


@router.put("/scenes/{index}/code")
def put_code(pid: str, index: int, body: dict):
    """Sauvegarde du code édité (3 onglets) — validation basique incluse."""
    script = load_script(pid)
    if not (0 <= index < len(script["scenes"])):
        raise HTTPException(404, "scène introuvable")
    h, c, j = body.get("html") or "", body.get("css") or "", body.get("js") or ""
    problems = validate_code(h, c, j)
    fh, fc, fs = scene_files(pid, index)
    fh.parent.mkdir(parents=True, exist_ok=True)
    fh.write_text(h, encoding="utf-8")
    fc.write_text(c, encoding="utf-8")
    fs.write_text(j, encoding="utf-8")
    return {"ok": True, "warnings": problems}


def validate_code(html: str, css: str, js: str) -> list:
    """Validation « évidente » : balises non fermées grossières, accolades, etc."""
    problems = []
    for name, code in (("html", html), ("css", css), ("js", js)):
        if code.count("{") != code.count("}"):
            problems.append(f"{name} : accolades déséquilibrées")
        if code.count("(") != code.count(")"):
            problems.append(f"{name} : parenthèses déséquilibrées")
    if html and "<html" not in html.lower():
        problems.append("html : balise <html> absente")
    if js and js.count('"') % 2:
        problems.append("js : guillemets déséquilibrés")
    return problems


@router.get("/scenes/{index}/preview")
def scene_preview(pid: str, index: int):
    """Document autonome servi pour l'iframe de prévisualisation."""
    script = load_script(pid)
    if not (0 <= index < len(script["scenes"])):
        raise HTTPException(404, "scène introuvable")
    from fastapi import Response
    html = combine_scene_html(pid, index)
    style = script.get("style") or {}
    vars_css = (f":root{{--hf-primary:{style.get('primary', '#7C5CFF')};"
                f"--hf-secondary:{style.get('secondary', '#0E0E12')};"
                f"--hf-bg:{style.get('background', '#0E0E12')};"
                f"--hf-font:'{style.get('font', 'Inter')}',sans-serif}}")
    m = re.search(r"<head\b[^>]*>", html, re.I)
    if m:
        html = html[:m.end()] + f"<style>{vars_css}</style>" + html[m.end():]
    else:
        html = f"<style>{vars_css}</style>" + html
    return Response(html, media_type="text/html")


class RegenerateBody(BaseModel):
    what: str = "both"          # text | code | both
    directive: str = ""


@router.post("/scenes/{index}/regenerate")
async def regenerate_scene(pid: str, index: int, body: RegenerateBody):
    """Régénère cette scène (texte seul, code seul, ou les deux)."""
    script = load_script(pid)
    if not (0 <= index < len(script["scenes"])):
        raise HTTPException(404, "scène introuvable")
    scene = script["scenes"][index]
    if scene.get("locked"):
        raise HTTPException(409, "scène verrouillée — déverrouille-la d'abord")
    cfg = load_config()
    if not cfg["provider"]:
        raise HTTPException(422, "Moteur IA non configuré")
    out = {}
    style = script.get("style") or {}
    width, height = DIMENSIONS.get(style.get("aspect", "16:9"), (1920, 1080))
    try:
        if body.what in ("text", "both"):
            sys_p = REGENERATE_TEXT
            user_p = (f"Scène actuelle : {json.dumps(scene, ensure_ascii=False)}\n"
                      f"Contexte vidéo : {script.get('title')} — {script.get('description')}\n"
                      f"Langue : {script.get('language', 'fr')}\n"
                      f"Demande : {body.directive or 'améliore cette scène'}")
            out["text"] = await llm_complete(cfg, sys_p, user_p, 800)
            parsed = None
            try:
                from .ai import _extract_json
                parsed = _extract_json(out["text"])
            except Exception:
                pass
            if parsed and parsed.get("text"):
                scene["text"] = str(parsed["text"])
                if parsed.get("duration"):
                    scene["duration"] = float(parsed["duration"])
                scene.pop("_raw", None)
            else:
                raise HTTPException(502, "réponse IA illisible pour le texte")
        if body.what in ("code", "both"):
            sys_p = CODE_PROMPT.format(width=width, height=height,
                                       duration=scene.get("duration", 4))
            user_p = (f"Prompt visuel : {scene.get('visual_prompt', scene.get('text', ''))}\n"
                      f"Texte voix off : {scene.get('text', '')}\n"
                      f"Directive : {body.directive or 'aucune — suis le prompt visuel'}\n"
                      f"Style global : {json.dumps(style, ensure_ascii=False)}\n"
                      f"Code actuel (optionnel, à améliorer) : "
                      f"{combine_scene_html(pid, index)[:4000]}")
            raw = await llm_complete(cfg, sys_p, user_p, 16384)
            from .ai import _extract_json
            parsed = _extract_json(raw)
            html = (parsed or {}).get("html") or _extract_html(raw)
            if not html:
                raise HTTPException(502, "réponse IA sans code HTML")
            write_scene_code(pid, index, html)
            out["code"] = True
    except AIHTTP:
        raise
    save_script(pid, script)
    return {"ok": True, **out}


class AddSceneBody(BaseModel):
    after: int = -1              # index d'insertion (-1 = fin)
    scene: dict | None = None    # scène complète optionnelle


@router.post("/scenes")
def add_scene(pid: str, body: AddSceneBody):
    script = load_script(pid)
    new_scene = body.scene or {
        "text": "Nouvelle scène", "visual_prompt": "visuel simple animé",
        "duration": 4.0, "locked": False,
    }
    pos = len(script["scenes"]) if body.after < 0 else max(0, min(body.after + 1,
                                                                  len(script["scenes"])))
    script["scenes"].insert(pos, new_scene)
    save_script(pid, script)
    from .projects import renumber_scenes
    renumber_scenes(pid, pos)
    return {"ok": True, "index": pos}


@router.delete("/scenes/{index}")
def delete_scene(pid: str, index: int):
    script = load_script(pid)
    if not (0 <= index < len(script["scenes"])):
        raise HTTPException(404, "scène introuvable")
    script["scenes"].pop(index)
    save_script(pid, script)
    import shutil
    d = project_dir(pid)
    scenes_root = d / "scenes"
    if scenes_root.is_dir():
        target = scenes_root / f"{index:03d}"
        if target.exists():
            shutil.rmtree(target)
        for p in sorted(p for p in scenes_root.iterdir()
                        if p.is_dir() and p.name.isdigit() and int(p.name) > index):
            p.rename(scenes_root / f"{int(p.name) - 1:03d}")
    return {"ok": True}


class ReorderBody(BaseModel):
    order: list[int]


@router.post("/scenes/reorder")
def reorder_scenes(pid: str, body: ReorderBody):
    """Réordonne les scènes (drag & drop) : liste d'anciens index."""
    script = load_script(pid)
    scenes = script["scenes"]
    if sorted(body.order) != list(range(len(scenes))):
        raise HTTPException(400, "ordre invalide")
    script["scenes"] = [scenes[i] for i in body.order]
    save_script(pid, script)
    # renumérotation physique des dossiers de scènes
    d = project_dir(pid)
    scenes_root = d / "scenes"
    if scenes_root.is_dir():
        dirs = {int(p.name): p for p in scenes_root.iterdir()
                if p.is_dir() and p.name.isdigit()}
        tmp = d / "scenes_tmp"
        tmp.mkdir(exist_ok=True)
        for new_i, old_i in enumerate(body.order):
            if old_i in dirs:
                dirs[old_i].rename(tmp / f"{new_i:03d}")
        for p in tmp.iterdir():
            p.rename(scenes_root / p.name)
        tmp.rmdir()
    return {"ok": True}


class CodeGenBody(BaseModel):
    index: int


@router.post("/scenes/generate_code")
async def generate_code_bulk(pid: str, body: CodeGenBody):
    """Génère le code d'une scène depuis son visual_prompt (bouton « Générer le code »)."""
    return await regenerate_scene(pid, body.index, RegenerateBody(what="code"))
