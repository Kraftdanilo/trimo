# HyperFrames

Studio web : à partir d'une idée → script structuré → scènes HTML/CSS/JS animées
générées par IA → voix off edge-tts → édition complète → export MP4.

## Interface

Studio type NLE (inspiré CapCut PC) : tout est sur un seul écran.

```
┌──────────────────────────────────────────────────────────────┐
│ Topbar : projet · titre · undo/redo · sauver · Exporter MP4  │
├──────────┬──────────────────────────────┬────────────────────┤
│ Scènes   │  VIEWPORT (letterbox, ratio  │ Inspecteur :       │
│ Assets   │  du projet, scène à l'échelle│ Scène · Code ·     │
│ + script │  réelle) + transport         │ Projet · Voix ·    │
│ IA       │  ⏮ ▶ ⏭ 🔁 + timecode         │ Versions · IA      │
├──────────┴──────────────────────────────┴────────────────────┤
│ Timeline : règle graduée · playhead · scrub · zoom · clips   │
│ (glisser le bord droit d'un clip = ajuster la durée)         │
└──────────────────────────────────────────────────────────────┘
```

- Lecture unifiée : le playhead traverse la timeline, le viewport bascule de
  scène en scène et joue l'audio correspondant. Espace = lecture, ←/→ = scène
  précédente/suivante, clic sur la règle = scrub.
- Le viewport affiche la scène à sa taille de rendu réelle (ex. 1920×1080)
  mise à l'échelle — identique au rendu Playwright final.
- Presets motion design (Cinétique, Minimal, Néon, Bounce, Ciné, Data) dans
  l'inspecteur : remplissent la directive passée à l'IA pour régénérer le code
  d'une scène.
- « 🤖 Code manquant » (bibliothèque de scènes) : génère en séquence le code IA
  de toutes les scènes qui n'en ont pas encore, avec progression.

## Démarrage

```bash
pip install -r requirements.txt
playwright install chromium        # pour le rendu vidéo
ffmpeg dans le PATH                # pour l'export MP4
python run.py                      # http://localhost:8080
```

Ou : `uvicorn server:app --port 8080`

## Pipeline

1. **Script IA** — l'idée devient un script JSON (scènes, durées, textes voix off,
   prompts visuels) via OpenAI / Anthropic / Gemini / Mistral / X.ai / Xkiro /
   Agnes / Ollama / OpenRouter.
2. **Code de scène IA** — pour chaque scène, un document HTML autonome (CSS/JS
   inline, animation requestAnimationFrame ou CSS keyframes) est généré.
3. **Voix off** — edge-tts (gratuit, local) : voix, rate/volume/pitch, timestamps
   WordBoundary → sous-titres automatiques. Upload MP3/WAV possible par scène.
4. **Édition** — script (drag & drop, verrouillage, régénération ciblée),
   code (3 onglets HTML/CSS/JS, aperçu iframe sandbox, validation), style global
   (couleurs, police, ratio, résolution, fps), timeline, assets, versions.
5. **Export** — Playwright capture chaque scène, ffmpeg concatène + mixe
   l'audio → `output.mp4` (H.264/AAC) téléchargeable.

## Stockage

```
projects/{id}/
  script.json      # projet complet (style, voix, scènes, sous-titres)
  scenes/{idx}/    # index.html, style.css, script.js
  audio/           # scene_000.mp3, customs…
  assets/          # images, musiques, logos
  versions/        # snapshots (script + scènes) horodatés
  output.mp4       # dernier rendu
```

## Configuration IA

Onglet « Réglages IA » ou `ai_config.json` / `.env`
(`AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`).
Ollama : `http://localhost:11434/v1` sans clé.
Catalogue de modèles gratuits : `GET /api/ai/models`.

## Tests

```bash
python -m pytest tests/ -v
```

## Limites connues

- Le rendu vidéo est temps réel (1 s de vidéo ≈ 1 s de capture).
- CodeMirror/Monaco, WaveSurfer, Prettier sont prévus mais l'éditeur actuel
  utilise des `<textarea>` (simple, zéro dépendance CDN).
- L'aperçu audio+vidéo est scène par scène : à l'entrée dans une scène,
  l'animation et la voix repartent du début de la scène (pas de seek intra-scène).
