"""Voix off : edge-tts (gratuit, local) + sous-titres depuis WordBoundary."""
import asyncio
import json
import re
from pathlib import Path

import edge_tts
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .projects import load_script, save_script, project_dir

router = APIRouter(prefix="/api/projects/{pid}", tags=["tts"])

voices_router = APIRouter(prefix="/api", tags=["tts"])


@voices_router.get("/voices")
async def list_voices():
    """Liste des voix edge-tts disponibles (regroupées par langue)."""
    voices = await edge_tts.list_voices()
    out = {}
    for v in voices:
        lang = v["Locale"]
        out.setdefault(lang, []).append({
            "name": v["ShortName"], "gender": v["Gender"],
        })
    return out


def _rate(r): return f"{r:+d}%" if isinstance(r, (int, float)) else str(r or "+0%")


def _pitch(p): return f"{p:+d}Hz" if isinstance(p, (int, float)) else str(p or "+0Hz")


def _volume(v): return f"{v:+d}%" if isinstance(v, (int, float)) else str(v or "+0%")


class TtsBody(BaseModel):
    index: int | None = None          # None = toutes les scènes
    voice: str | None = None
    rate: str | None = None
    volume: str | None = None
    pitch: str | None = None


async def _tts_scene(pid: str, index: int, scene: dict, voice_cfg: dict) -> dict:
    """Synthétise la voix d'une scène + extrait les timestamps des mots."""
    d = project_dir(pid) / "audio"
    d.mkdir(exist_ok=True)
    mp3 = d / f"scene_{index:03d}.mp3"
    text = (scene.get("text") or "").strip()
    if scene.get("silence") or not text:
        if mp3.exists():
            mp3.unlink()
        return {"index": index, "duration": 0.0, "words": []}
    communicate = edge_tts.Communicate(
        text, voice_cfg.get("name", "fr-FR-HenriNeural"),
        rate=_rate(voice_cfg.get("rate", "+0%")),
        volume=_volume(voice_cfg.get("volume", "+0%")),
        pitch=_pitch(voice_cfg.get("pitch", "+0Hz")))
    words = []
    with open(mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "t": chunk["offset"] / 1e7,          # 100 ns → s
                    "d": chunk["duration"] / 1e7,
                    "w": chunk["text"],
                })
    duration = 0.0
    if words:
        duration = words[-1]["t"] + words[-1]["d"]
    return {"index": index, "duration": round(duration, 3), "words": words}


@router.post("/tts")
async def generate_tts(pid: str, body: TtsBody):
    """Synthèse voix off pour une scène ou toutes, + timings de sous-titres."""
    script = load_script(pid)
    voice_cfg = script.get("voice") or {}
    for k in ("name", "rate", "volume", "pitch"):
        v = getattr(body, k)
        if v is not None:
            voice_cfg[k] = v
    script["voice"] = voice_cfg
    save_script(pid, script)
    scenes = script["scenes"]
    indices = ([body.index] if body.index is not None
               else list(range(len(scenes))))
    if body.index is not None and not (0 <= body.index < len(scenes)):
        raise HTTPException(404, "scène introuvable")
    results = []
    for i in indices:
        r = await _tts_scene(pid, i, scenes[i], voice_cfg)
        results.append(r)
        if i < len(scenes):
            scenes[i]["audio"] = {
                "duration": r["duration"], "words": r["words"],
            }
            # met à jour la durée cible si le texte a été synthétisé
            if r["duration"] > 0:
                scenes[i]["duration"] = max(scenes[i].get("duration", 0),
                                            round(r["duration"] + 0.6, 2))
    save_script(pid, script)
    return {"ok": True, "results": [
        {k: v for k, v in r.items() if k != "words"} for r in results]}


@router.get("/audio/{index}")
def get_audio(pid: str, index: int):
    f = project_dir(pid) / "audio" / f"scene_{index:03d}.mp3"
    if not f.exists():
        raise HTTPException(404, "audio absent — génère la voix off d'abord")
    return FileResponse(f, media_type="audio/mpeg", filename=f.name)


class UploadBody(BaseModel):
    index: int
    data_b64: str
    ext: str = "mp3"


@router.post("/audio/upload")
def upload_audio(pid: str, body: UploadBody):
    """Upload d'une voix off personnalisée (MP3/WAV) pour une scène."""
    from .assets import decode_b64
    script = load_script(pid)
    if not (0 <= body.index < len(script["scenes"])):
        raise HTTPException(404, "scène introuvable")
    d = project_dir(pid) / "audio"
    d.mkdir(exist_ok=True)
    ext = body.ext if body.ext in ("mp3", "wav", "ogg") else "mp3"
    f = d / f"scene_{body.index:03d}.{ext}"
    f.write_bytes(decode_b64(body.data_b64))
    script["scenes"][body.index]["audio"] = {"custom": f.name}
    save_script(pid, script)
    return {"ok": True, "file": f.name}


def _fmt_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_srt(script: dict) -> str:
    """SRT depuis le texte + timestamps WordBoundary par scène."""
    blocks = []
    cursor = 0.0
    n = 1
    for i, scene in enumerate(script["scenes"]):
        dur = float(scene.get("duration", 4))
        audio = scene.get("audio") or {}
        words = audio.get("words") or []
        if scene.get("silence") or not scene.get("text"):
            cursor += dur
            continue
        if words:
            # regroupe les mots en lignes de ~7 mots
            lines = [words[j:j + 7] for j in range(0, len(words), 7)]
            for line in lines:
                start = cursor + line[0]["t"]
                end = cursor + line[-1]["t"] + line[-1]["d"]
                text = " ".join(w["w"] for w in line)
                blocks.append(f"{n}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}")
                n += 1
        else:
            blocks.append(f"{n}\n{_fmt_srt(cursor)} --> {_fmt_srt(cursor + min(dur, 4))}\n"
                          f"{scene['text']}")
            n += 1
        cursor += dur
    return "\n\n".join(blocks) + ("\n" if blocks else "")


@router.get("/subtitles/srt")
def get_srt(pid: str):
    return FileResponse(_write_srt_tmp(pid), filename=f"{pid}.srt",
                        media_type="application/x-subrip")


def _write_srt_tmp(pid: str):
    import tempfile
    srt = build_srt(load_script(pid))
    tmp = Path(tempfile.gettempdir()) / f"hf_{pid}.srt"
    tmp.write_text(srt, encoding="utf-8")
    return tmp


@router.put("/subtitles")
def update_subtitles(pid: str, body: dict):
    """Édition manuelle des sous-titres : liste de {text, start, end, scene}."""
    script = load_script(pid)
    script["subtitles"] = body.get("subtitles") or []
    save_script(pid, script)
    return {"ok": True}
