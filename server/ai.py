"""Abstraction LLMProvider : OpenAI, Anthropic, Gemini, Ollama (+ OpenRouter)."""
import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/ai", tags=["ai"])

CFG_PATH = Path(__file__).resolve().parents[1] / "ai_config.json"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for k in list(os.environ):
        if k.startswith("AI_") or k == "OPENROUTER_API_KEY":
            env[k] = os.environ[k]
    return env


ENV = _load_env()
DEFAULT_CFG = {
    "provider": ENV.get("AI_PROVIDER", ""),
    "base_url": ENV.get("AI_BASE_URL", ""),
    "model": ENV.get("AI_MODEL", ""),
    "api_key": ENV.get("AI_API_KEY", ""),
    "temperature": 0.7,
}

PRESETS = {
    "openai":     {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "anthropic":  {"base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-20250514"},
    "google":     {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash"},
    "xkiro":      {"base_url": "https://api.xkiro.com/v1", "model": "mistralai/mistral-large-2512"},
    "xai":        {"base_url": "https://api.x.ai/v1", "model": "grok-4-fast"},
    "agnes":      {"base_url": "https://apihub.agnes-ai.com/v1", "model": ""},
    "mistral":    {"base_url": "https://api.mistral.ai/v1", "model": "codestral-latest"},
    "ollama":     {"base_url": "http://localhost:11434/v1", "model": "llama3.1"},   # LM Studio, vLLM… (champ custom)
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "qwen/qwen3-coder:free"},
}

# Modèles GRATUITS (OpenRouter ":free") recommandés pour le coding + raisonnement
FREE_MODELS = {
    "xkiro": [
        "mistralai/mistral-large-2512",        # par défaut Xkiro
        "mistralai/mistral-small-2512",
        "mistralai/devstral-small-2512",        # coding
        "mistralai/magistral-small-2512",       # raisonnement
        "qwen/qwen3-coder",                     # coding
        "qwen/qwen3-235b-a22b",                 # raisonnement
    ],
    "openrouter": [
        "qwen/qwen3-coder:free",                        # coding, très fort
        "qwen/qwen3-235b-a22b:free",                    # raisonnement, gros modèle MoE
        "qwen/qwen3-30b-a3b:free",                      # raisonnement, rapide
        "qwen/qwen-2.5-72b-instruct:free",
        "mistralai/mistral-small-3.2-24b-instruct:free",  # coding + raisonnement solide
        "mistralai/devstral-small-2505:free",           # spécial coding (SWE)
        "mistralai/mistral-nemo:free",
        "mistralai/mistral-7b-instruct:free",
    ],
    "mistral": [
        "codestral-latest",       # coding (niveau gratuit limité mais disponible)
        "magistral-small-latest", # raisonnement
        "mistral-small-latest",
        "open-mistral-nemo",
    ],
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CFG)
    if CFG_PATH.exists():
        try:
            cfg.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
        except ValueError:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def public_config(cfg: dict) -> dict:
    key = cfg.get("api_key") or ""
    return {
        "provider": cfg["provider"], "base_url": cfg["base_url"],
        "model": cfg["model"], "temperature": cfg["temperature"],
        "key_set": bool(key),
        "key_hint": (key[:3] + "…" + key[-4:]) if len(key) > 8 else ("définie" if key else ""),
    }


class CfgBody(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    temperature: float | None = None


@router.get("/models")
def get_models():
    """Catalogue de modèles gratuits par fournisseur."""
    return FREE_MODELS


@router.get("/presets")
def get_presets():
    """Presets fournisseur : URL de base + modèle par défaut (sans la clé API)."""
    return PRESETS


@router.get("/config")
def get_config():
    return public_config(load_config())


@router.post("/config")
def set_config(body: CfgBody):
    cfg = load_config()
    for k in ("provider", "base_url", "model"):
        v = getattr(body, k)
        if v is not None:
            cfg[k] = str(v).strip()
    if body.api_key:
        cfg["api_key"] = body.api_key.strip()
    if body.temperature is not None:
        cfg["temperature"] = min(1.0, max(0.0, body.temperature))
    save_config(cfg)
    return public_config(cfg)


@router.post("/config/test")
async def test_config(body: CfgBody):
    cfg = load_config()
    for k in ("provider", "base_url", "model"):
        v = getattr(body, k)
        if v:
            cfg[k] = str(v).strip()
    if body.api_key:
        cfg["api_key"] = body.api_key.strip()
    if not cfg["provider"]:
        raise HTTPException(422, "Choisis un fournisseur")
    if not cfg["base_url"] or not cfg["model"]:
        raise HTTPException(422, "Renseigne l'URL de base et le modèle")
    url = cfg["base_url"].rstrip("/")
    headers = {"content-type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    if cfg["provider"] == "anthropic":
        url += "/v1/messages"
        headers = {"x-api-key": cfg["api_key"], "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body_msg = {"model": cfg["model"], "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Réponds uniquement : OK"}]}
    else:
        url += "/chat/completions"
        body_msg = {"model": cfg["model"], "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Réponds uniquement : OK"}]}
    try:
        async with httpx.AsyncClient(timeout=(8, 30)) as client:
            r = await client.post(url, headers=headers, json=body_msg)
        if r.status_code != 200:
            raise HTTPException(502, f"{r.status_code} — {r.text[:200]}")
        data = r.json()
        if cfg["provider"] == "anthropic":
            reply = ((data.get("content") or [{}])[0] or {}).get("text", "")
        else:
            reply = ((data.get("choices") or [{}])[0] or {}).get("message", {}).get("content", "")
        return {"ok": True, "reply": str(reply).strip()[:40], "model": cfg["model"]}
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Connexion impossible : {e}")


# ── Génération ─────────────────────────────────────────────────────────────
class GenBody(BaseModel):
    prompt: str
    system: str = ""
    json_mode: bool = False
    max_tokens: int = 4096


def _extract_json(text: str):
    """Extrait le premier objet JSON valide (accolades équilibrées, chaînes respectées)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


async def llm_complete(cfg: dict, system: str, prompt: str,
                       max_tokens: int = 4096) -> str:
    """Appel bloquant (une requête, réponse complète)."""
    url = cfg["base_url"].rstrip("/")
    if cfg["provider"] == "anthropic":
        headers = {"x-api-key": cfg["api_key"], "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": cfg["model"], "max_tokens": max_tokens,
                "temperature": cfg["temperature"], "system": system,
                "messages": [{"role": "user", "content": prompt}]}
        url += "/v1/messages"
    else:
        headers = {"content-type": "application/json"}
        if cfg["api_key"]:
            headers["Authorization"] = "Bearer " + cfg["api_key"]
        body = {"model": cfg["model"], "max_tokens": max_tokens,
                "temperature": cfg["temperature"],
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}]}
        url += "/chat/completions"
    async with httpx.AsyncClient(timeout=(15, 300)) as client:
        r = await client.post(url, headers=headers, json=body)
    if r.status_code != 200:
        raise HTTPException(502, f"Erreur du moteur ({r.status_code}) : {r.text[:300]}")
    data = r.json()
    if cfg["provider"] == "anthropic":
        return ((data.get("content") or [{}])[0] or {}).get("text", "")
    return ((data.get("choices") or [{}])[0] or {}).get("message", {}).get("content", "")


@router.post("/generate")
async def generate(body: GenBody):
    """Génération IA : texte brut ou JSON extrait."""
    cfg = load_config()
    if not cfg["provider"] or not cfg["base_url"] or not cfg["model"]:
        raise HTTPException(422, "Moteur IA non configuré — ouvre les réglages")
    text = await llm_complete(cfg, body.system, body.prompt, body.max_tokens)
    if body.json_mode:
        parsed = _extract_json(text)
        if parsed is None:
            raise HTTPException(502, "Réponse IA sans JSON exploitable")
        return parsed
    return {"text": text}
