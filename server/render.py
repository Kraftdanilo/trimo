"""Rendu vidéo : Playwright (webm par scène) puis concat + MP4 via ffmpeg."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .projects import load_script, project_dir
from .scenes import combine_scene_html, DIMENSIONS

router = APIRouter(prefix="/api/projects/{pid}", tags=["render"])

TMP = Path(__file__).resolve().parents[1] / "projects" / "_render"


def _ffmpeg() -> str:
    for c in ("ffmpeg", "ffmpeg.exe"):
        if shutil.which(c):
            return c
    raise HTTPException(500, "ffmpeg introuvable — installe-le et ajoute-le au PATH")


def _probe(path: Path) -> float:
    """Durée d'un média via ffprobe."""
    ff = _ffmpeg().replace("ffmpeg", "ffprobe")
    r = subprocess.run([ff, "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError):
        return 0.0


class RenderBody(BaseModel):
    resolution: int | None = None    # 720 / 1080 / 1440 / 2160


@router.post("/render")
async def render(pid: str, body: RenderBody):
    """Rendu vidéo seule (sans audio) → MP4 — utilisé comme fallback."""
    script = load_script(pid)
    if not script["scenes"]:
        raise HTTPException(400, "aucune scène à rendre")
    style = script.get("style") or {}
    aspect = style.get("aspect", "16:9")
    base_w, base_h = DIMENSIONS.get(aspect, (1920, 1080))
    res = body.resolution or int(style.get("resolution", 1080))
    scale = res / base_h
    W, H = int(base_w * scale) // 2 * 2, res // 2 * 2
    fps = int(style.get("fps", 30))

    d = project_dir(pid)
    tmp = TMP / pid
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        segments = []
        for i, scene in enumerate(script["scenes"]):
            dur = float(scene.get("duration", 4))
            webm = tmp / f"scene_{i:03d}.webm"
            await _render_scene(combine_scene_html(pid, i), webm, W, H, dur, fps)
            segments.append((webm, dur, scene))
        out_mp4 = d / "output.mp4"
        _assemble(tmp, segments, out_mp4, W, H, fps)
        return {"ok": True, "file": f"/api/projects/{pid}/download",
                "duration": sum(s[1] for s in segments)}
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


async def _render_scene(html: str, out: Path, W: int, H: int, dur: float,
                        fps: int) -> None:
    """Capture Playwright : screencast du viewport pendant la durée de la scène."""
    from playwright.async_api import async_playwright
    proc = await asyncio.create_subprocess_exec(
        _ffmpeg(), "-y", "-f", "image2pipe", "-framerate", str(fps),
        "-i", "-", "-c:v", "libvpx-vp9", "-b:v", "6M",
        str(out), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    loop = asyncio.get_running_loop()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--force-device-scale-factor=1"])
        page = await browser.new_page(viewport={"width": W, "height": H})
        await page.goto("about:blank")
        await page.set_content(html, wait_until="networkidle")
        await page.evaluate("document.fonts && document.fonts.ready")
        t0 = loop.time()
        n = 0
        while True:
            el = loop.time() - t0
            if el >= dur:
                break
            png = await page.screenshot(type="png")
            try:
                proc.stdin.write(png)
                await proc.stdin.drain()
            except BrokenPipeError:
                break
            n += 1
            target = n / fps
            wait = t0 + target - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
        await browser.close()
    try:
        proc.stdin.close()
    except Exception:
        pass
    await proc.wait()


def _audio_for_scene(d: Path, i: int):
    """Fichier audio (custom prioritaire) pour la scène i."""
    for ext in ("mp3", "wav", "ogg"):
        f = d / f"scene_{i:03d}.{ext}"
        if f.exists():
            return f
    return None


def _assemble(tmp: Path, segments, out_mp4: Path, W: int, H: int,
              fps: int) -> None:
    """Concatène les segments vidéo normalisés → MP4 (sans audio)."""
    # 1. normalise chaque segment en mp4 intermédiaire (vidéo seule)
    parts = []
    for i, (webm, dur, scene) in enumerate(segments):
        norm = tmp / f"norm_{i:03d}.mp4"
        subprocess.run([_ffmpeg(), "-y", "-i", str(webm),
                        "-t", f"{dur:.3f}", "-an",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                        "-pix_fmt", "yuv420p", str(norm)],
                       capture_output=True)
        parts.append(norm)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    # 2. concat vidéo
    video_only = tmp / "video.mp4"
    subprocess.run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", str(video_only)],
                   capture_output=True)
    if not video_only.exists():
        raise HTTPException(500, "échec de concaténation vidéo")
    shutil.copy(video_only, out_mp4)


# ── Version finale avec audio : réassemble tout ───────────────────────────
@router.post("/render_full")
async def render_full(pid: str, body: RenderBody):
    """Rendu vidéo + audio (voix off) → MP4 final."""
    script = load_script(pid)
    if not script["scenes"]:
        raise HTTPException(400, "aucune scène")
    style = script.get("style") or {}
    aspect = style.get("aspect", "16:9")
    base_w, base_h = DIMENSIONS.get(aspect, (1920, 1080))
    res = body.resolution or int(style.get("resolution", 1080))
    scale = res / base_h
    W, H = int(base_w * scale) // 2 * 2, res // 2 * 2
    fps = int(style.get("fps", 30))

    d = project_dir(pid)
    tmp = TMP / pid
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        video_parts = []
        audio_filters = []
        inputs = []
        t = 0.0
        for i, scene in enumerate(script["scenes"]):
            dur = float(scene.get("duration", 4))
            webm = tmp / f"scene_{i:03d}.webm"
            await _render_scene(combine_scene_html(pid, i), webm, W, H, dur, fps)
            norm = tmp / f"norm_{i:03d}.mp4"
            subprocess.run([_ffmpeg(), "-y", "-i", str(webm), "-t", f"{dur:.3f}",
                            "-an", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "20", "-pix_fmt", "yuv420p", str(norm)],
                           capture_output=True)
            video_parts.append(norm)
            # audio (custom prioritaire)
            a = None
            adir = d / "audio"
            if scene.get("audio", {}).get("custom"):
                c = adir / scene["audio"]["custom"]
                if c.exists():
                    a = c
            else:
                for ext in ("mp3", "wav", "ogg"):
                    f = adir / f"scene_{i:03d}.{ext}"
                    if f.exists():
                        a = f
                        break
            if a:
                idx = len(inputs) // 2 + 1          # input index dans la commande ffmpeg
                inputs += ["-i", str(a)]
                # [idx:a] adelay → label unique « ax{idx} » pour éviter les collisions
                audio_filters.append(
                    f"[{idx}:a]adelay={int(t * 1000)}|{int(t * 1000)}[ax{idx}]")
            t += dur
        lst = tmp / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in video_parts),
                       encoding="utf-8")
        video_only = tmp / "video.mp4"
        subprocess.run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(video_only)],
                       capture_output=True)
        out_mp4 = d / "output.mp4"
        if audio_filters:
            n_a = len(audio_filters)
            fc = ";".join(audio_filters)
            fc += ";" + "".join(f"[ax{i + 1}]" for i in range(n_a)) + \
                f"amix=inputs={n_a}:duration=longest,apad=whole_dur={t:.3f}[mix]"
            cmd = [_ffmpeg(), "-y", "-i", str(video_only)] + inputs + \
                  ["-filter_complex", fc, "-map", "0:v", "-map", "[mix]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                   "-t", f"{t:.3f}", str(out_mp4)]
        else:
            cmd = [_ffmpeg(), "-y", "-i", str(video_only), "-c", "copy",
                   str(out_mp4)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise HTTPException(500, f"ffmpeg : {r.stderr[-400:]}")
        return {"ok": True, "file": f"/api/projects/{pid}/download",
                "duration": t}
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


@router.get("/download")
def download(pid: str):
    f = project_dir(pid) / "output.mp4"
    if not f.exists():
        raise HTTPException(404, "aucun rendu — lance un export d'abord")
    return FileResponse(f, media_type="video/mp4", filename="output.mp4")


class RenderPreviewBody(BaseModel):
    html: str
    width: int = 1920
    height: int = 1080


@router.post("/render_preview_png")
async def render_preview_png(pid: str, body: RenderPreviewBody):
    """Capture PNG d'un HTML (aperçu d'une scène éditée)."""
    from playwright.async_api import async_playwright
    tmp = TMP / pid
    tmp.mkdir(parents=True, exist_ok=True)
    png = tmp / "preview.png"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": body.width,
                                                "height": body.height})
        await page.set_content(body.html, wait_until="networkidle")
        await page.screenshot(path=str(png), type="png")
        await browser.close()
    return FileResponse(png, media_type="image/png", filename="preview.png")
