"""Génération du script vidéo structuré via IA (scènes + durées + prompts visuels)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .ai import load_config, llm_complete, _extract_json, HTTPException as AIHTTP
from .prompts import SCRIPT_PROMPT
from .projects import load_script, save_script
from .versions import snapshot

router = APIRouter(prefix="/api/projects/{pid}", tags=["script"])

SCRIPT_ROUTER = APIRouter(prefix="/api", tags=["script"])


class ScriptGenBody(BaseModel):
    idea: str
    mode: str = "generate"       # generate | improve
    n_scenes: int | None = None


@SCRIPT_ROUTER.post("/script/generate")
async def generate_script(body: ScriptGenBody):
    """Génère un script complet depuis une idée (nouveau projet) ou améliore."""
    cfg = load_config()
    if not cfg["provider"] or not cfg["base_url"] or not cfg["model"]:
        raise HTTPException(422, "Moteur IA non configuré — ouvre les réglages")
    n = body.n_scenes or ""
    extra = (f"\nNombre de scènes demandé : {n}" if n else "")
    user = (f"Idée / script du metteur en scène :\n{body.idea}{extra}\n\n"
            f"Écris le script vidéo et réponds uniquement avec le JSON.")
    try:
        raw = await llm_complete(cfg, SCRIPT_PROMPT, user, 4096)
    except AIHTTP as e:
        raise HTTPException(e.status_code, e.detail)
    parsed = _extract_json(raw)
    if not parsed or not parsed.get("scenes"):
        raise HTTPException(502, "réponse IA sans script JSON exploitable")
    scenes = []
    for s in parsed["scenes"][:24]:
        if not isinstance(s, dict):
            continue
        scenes.append({
            "text": str(s.get("text", "")).strip(),
            "visual_prompt": str(s.get("visual_prompt", "")).strip(),
            "duration": max(1.0, min(20.0, float(s.get("duration", 4)))),
            "locked": bool(s.get("locked", False)),
        })
    if not scenes:
        raise HTTPException(502, "script vide")
    return {
        "title": str(parsed.get("title", "video")).strip()[:60],
        "description": str(parsed.get("description", ""))[:300],
        "language": str(parsed.get("language", "fr"))[:8],
        "scenes": scenes,
    }


@router.post("/script/regenerate")
async def regenerate_script(pid: str, body: ScriptGenBody):
    """Régénère tout le script du projet (avec confirmation côté UI)."""
    script = load_script(pid)
    snapshot(pid, "avant régénération du script", "auto")
    body.mode = "improve"
    context = (f"Script actuel :\n{script['title']} — {script.get('description', '')}\n"
               + "\n".join(f"- [{i}] {s['text']} ({s['duration']}s)"
                           f"{' [VERROUILLÉE]' if s.get('locked') else ''}"
                           for i, s in enumerate(script["scenes"]))
               + f"\n\nDemande : {body.idea}")
    result = await generate_script(ScriptGenBody(idea=context, mode="improve"))
    # les scènes verrouillées sont conservées à leur position d'origine
    locked = {i: s for i, s in enumerate(script["scenes"]) if s.get("locked")}
    merged = list(result["scenes"])
    for i, s in locked.items():
        if i < len(merged):
            merged[i] = s
    script.update({"title": result["title"], "description": result["description"],
                   "language": result["language"], "scenes": merged})
    save_script(pid, script)
    return {"ok": True, "script": script}
