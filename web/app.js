/* HyperFrames — studio NLE (vanilla JS) */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* ── État ── */
let S = {
  pid: null, script: null, sceneIdx: 0,
  codeLang: 'html', tlT: 0, tlZoom: 1, _total: 0,
  ovPlaying: false, _ovScene: 0, loop: false,
  undo: [], redo: [],
};
let saveTimer = null;
const cur = () => S.script?.scenes?.[S.sceneIdx];

/* ── Utilitaires ── */
async function api(method, url, body) {
  const opt = { method, headers: {'Content-Type': 'application/json'} };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(url, opt);
  const txt = await r.text();
  let data; try { data = JSON.parse(txt); } catch { data = txt; }
  if (!r.ok) throw new Error(typeof data === 'object' && data.detail ? data.detail : (data || r.statusText));
  return data;
}
const toast = (msg, err) => {
  const d = document.createElement('div');
  d.className = 'toast' + (err ? ' err' : '');
  d.textContent = msg;
  $('#toast').appendChild(d);
  setTimeout(() => d.remove(), 3000);
};
const busy = (v, txt) => { $('#busy').classList.toggle('hidden', !v); if (txt) $('#busyTxt').textContent = txt; };
function fmtDur(s) {
  if (s == null || isNaN(s)) return '—';
  if (s < 60) return `${Math.round(s * 10) / 10} s`;
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${m} min ${String(r).padStart(2, '0')} s`;
}
function fmtTc(s) {
  const m = Math.floor(s / 60), r = s - m * 60;
  return `${m}:${String(Math.floor(r)).padStart(2, '0')}.${Math.floor((r % 1) * 10)}`;
}
/* taille de rendu réelle (identique à render.py) */
function sceneSize() {
  const st = S.script?.style || {};
  const base = {'16:9': [1920, 1080], '9:16': [1080, 1920],
                '1:1': [1080, 1080], '4:5': [1080, 1350]}[st.aspect || '16:9']
              || [1920, 1080];
  const k = (Number(st.resolution) || 1080) / base[1];
  return [Math.round(base[0] * k / 2) * 2, Math.round(base[1] * k / 2) * 2];
}
/* place une iframe de taille scène (W×H) dans son conteneur, mise à l'échelle */
function fitIframe(f, box, W, H) {
  const r = box.getBoundingClientRect();
  const k = Math.min((r.width || 1) / W, (r.height || 1) / H);
  f.style.width = W + 'px';
  f.style.height = H + 'px';
  f.style.transform = `scale(${k})`;
  f.style.transformOrigin = '0 0';
  f.style.left = Math.max(0, (r.width - W * k) / 2) + 'px';
  f.style.top = Math.max(0, (r.height - H * k) / 2) + 'px';
}

/* ── Undo / redo ── */
function snapshotUndo() {
  S.undo.push(JSON.stringify(S.script));
  if (S.undo.length > 50) S.undo.shift();
  S.redo.length = 0;
}
function doUndo() {
  if (!S.undo.length) return;
  S.redo.push(JSON.stringify(S.script));
  S.script = JSON.parse(S.undo.pop());
  renderAll(); saveScript(); toast('Annulé');
}
function doRedo() {
  if (!S.redo.length) return;
  S.undo.push(JSON.stringify(S.script));
  S.script = JSON.parse(S.redo.pop());
  renderAll(); saveScript(); toast('Rétabli');
}

/* ── Projets ── */
async function loadProjects() {
  const list = await api('GET', '/api/projects');
  const sel = $('#projectSelect');
  sel.innerHTML = '';
  if (!list.length) { await newProject(); return; }
  list.forEach(p => {
    const o = document.createElement('option');
    o.value = p.id; o.textContent = `${p.title} (${p.scenes})`;
    sel.appendChild(o);
  });
  sel.value = S.pid || list[0].id;
  await openProject(sel.value);
}
async function openProject(pid) {
  const same = S.pid === pid;
  S.pid = pid;
  const data = await api('GET', `/api/projects/${pid}`);
  S.script = data.script;
  S.sceneIdx = 0; S.tlT = 0; S._ovScene = 0;
  stopPlayback();
  /* réinitialise l'historique uniquement si on change de projet */
  if (!same) { S.undo = []; S.redo = []; }
  renderAll();
}
async function newProject() {
  const name = prompt('Nom du projet :', 'Nouveau projet');
  if (!name) return;
  const p = await api('POST', '/api/projects', { name });
  S.pid = null;
  await loadProjects();
  $('#projectSelect').value = p.id;
  await openProject(p.id);
  toast('Projet créé');
}
async function deleteProject() {
  if (!confirm('Supprimer définitivement ce projet ?')) return;
  await api('DELETE', `/api/projects/${S.pid}`);
  S.pid = null;
  await loadProjects();
  toast('Projet supprimé');
}

/* ── Sauvegarde ── */
function saveScript() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try { await api('PUT', `/api/projects/${S.pid}/script`, S.script); }
    catch (e) { toast('Sauvegarde : ' + e.message, true); }
  }, 500);
}
async function saveNow() {
  await api('PUT', `/api/projects/${S.pid}/script`, S.script);
  toast('Sauvegardé');
}

/* ── Rendu global ── */
function renderAll() {
  if (!S.script) return;
  renderHeader();
  renderSceneList();
  renderInspectorScene();
  renderVoice();
  renderStyle();
  renderSubtitles();
  renderTimeline();
  renderVersions();
  renderAssets();
  renderPreview();
  renderOverview();
  selectScene(S.sceneIdx, { skipCodeFetch: false });
}

function renderHeader() {
  $('#projTitle').value = S.script.title || '';
  $('#projDesc').value = S.script.description || '';
}

/* ── Bibliothèque de scènes (liste compacte) ── */
function sceneBadges(s) {
  if (s.silence) return '<span class="chip">🔇</span>';
  if (s.audio?.custom) return '<span class="chip">🎵</span>';
  if (s.audio?.duration) return `<span class="chip">🎙 ${(s.audio.duration).toFixed(1)}s</span>`;
  return '<span class="chip warn">⚠</span>';
}
function renderSceneList() {
  const el = $('#sceneList');
  el.innerHTML = '';
  (S.script.scenes || []).forEach((s, i) => {
    const d = document.createElement('div');
    d.className = 'sc-card' + (i === S.sceneIdx ? ' sel' : '') + (s.locked ? ' locked' : '');
    d.draggable = true;
    d.innerHTML = `
      <div class="sc-num">${i + 1}</div>
      <div class="sc-body">
        <div class="sc-text">${esc((s.text || '(vide)').slice(0, 90))}</div>
        <div class="sc-meta"><span class="sc-dur mono">${(Number(s.duration) || 0).toFixed(1)}s</span>${sceneBadges(s)}</div>
      </div>
      <div class="sc-actions">
        <button data-a="dup" title="Dupliquer">⧉</button>
        <button data-a="del" title="Supprimer">🗑</button>
      </div>`;
    d.addEventListener('click', e => {
      const a = e.target.closest('[data-a]')?.dataset.a;
      if (a === 'dup') { duplicateScene(i); return; }
      if (a === 'del') { deleteScene(i); return; }
      selectScene(i);
    });
    /* drag & drop natif → réordonner */
    d.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', String(i)); });
    d.addEventListener('dragover', e => { e.preventDefault(); d.classList.add('dragover'); });
    d.addEventListener('dragleave', () => d.classList.remove('dragover'));
    d.addEventListener('drop', async e => {
      e.preventDefault(); d.classList.remove('dragover');
      const from = Number(e.dataTransfer.getData('text/plain'));
      if (from === i) return;
      const order = S.script.scenes.map((_, k) => k);
      order.splice(from, 1);
      order.splice(i, 0, from);
      snapshotUndo();
      await api('POST', `/api/projects/${S.pid}/scenes/reorder`, { order });
      await openProject(S.pid);
      toast('Ordre mis à jour');
    });
    el.appendChild(d);
  });
}
async function duplicateScene(i) {
  snapshotUndo();
  S.script.scenes.splice(i + 1, 0, JSON.parse(JSON.stringify(S.script.scenes[i])));
  saveScript(); renderAll(); toast('Scène dupliquée');
}
async function deleteScene(i) {
  if (!confirm('Supprimer cette scène ?')) return;
  snapshotUndo();
  await api('DELETE', `/api/projects/${S.pid}/scenes/${i}`);
  await openProject(S.pid);
}

/* Génère le code IA des scènes qui n'en ont pas (en séquence, avec progression). */
async function generateMissingCode() {
  const scenes = S.script.scenes || [];
  const codes = await Promise.all(scenes.map((_, i) =>
    api('GET', `/api/projects/${S.pid}/scenes/${i}/code`).catch(() => ({ html: '' }))));
  const targets = [];
  scenes.forEach((s, i) => {
    if (!s.locked && !(codes[i].html || '').trim()) targets.push(i);
  });
  if (!targets.length) {
    toast('Toutes les scènes ont déjà du code — utilise « ↻ Code IA » par scène');
    return;
  }
  if (!confirm(`Générer le code IA de ${targets.length} scène(s) ? (la directive de l'inspecteur sera utilisée)`)) return;
  const dir = ($('#insDirective')?.value || '').trim();
  let done = 0, failed = 0;
  for (const i of targets) {
    busy(true, `Code IA — scène ${i + 1} (${done + failed + 1}/${targets.length})…`);
    try {
      await api('POST', `/api/projects/${S.pid}/scenes/${i}/regenerate`, { what: 'code', directive: dir });
      done++;
    } catch { failed++; }
  }
  busy(false);
  await openProject(S.pid);
  toast(`${done} scène(s) générée(s)${failed ? ` — ${failed} échec(s)` : ''}`, failed > 0);
}

/* ── Sélection (liste ↔ timeline ↔ viewport ↔ inspecteur) ── */
function selectScene(i, opts = {}) {
  const n = (S.script?.scenes || []).length;
  if (!n) return;
  i = Math.max(0, Math.min(n - 1, i));
  S.sceneIdx = i;
  S._ovScene = i;
  S.tlT = sceneStart(i);
  $$('#sceneList .sc-card').forEach((d, k) => d.classList.toggle('sel', k === i));
  $$('#tlTrack .tl-block').forEach((b, k) => b.classList.toggle('sel', k === i));
  const sel = $(`#sceneList .sc-card:nth-child(${i + 1})`);
  sel?.scrollIntoView({ block: 'nearest' });
  renderInspectorScene();
  updatePlayhead();
  ovInfoUpdate();
  if (!opts.skipCodeFetch) loadCodeTab();
  ovLoadScene(i);
}

/* ── Inspecteur : scène courante ── */
function renderInspectorScene() {
  const s = cur();
  if (!s) return;
  $('#insNum').textContent = (S.sceneIdx + 1) + ' / ' + S.script.scenes.length;
  $('#insText').value = s.text || '';
  $('#insPrompt').value = s.visual_prompt || '';
  $('#insDur').value = s.duration;
  $('#insLock').textContent = s.locked ? '🔓 Déverrouiller' : '🔒 Verrouiller';
  $('#insSilence').textContent = s.silence ? '🔊 voix' : '🔇 silence';
  const a = s.audio || {};
  $('#insAudioInfo').textContent =
    a.custom ? `audio custom : ${a.custom}` :
    a.duration ? `voix générée : ${a.duration.toFixed(1)}s · ${(a.words || []).length} mots` :
    s.silence ? 'scène silencieuse' : 'pas encore de voix';
  $('#insPlay').style.display = (a.custom || a.duration) ? '' : 'none';
}

/* ── Génération script ── */
async function genScript(mode) {
  const idea = $('#aiIdea').value.trim();
  if (!idea) { toast('Décris ton idée d\'abord', true); return; }
  busy(true, 'Le scénariste IA écrit…');
  try {
    if (mode === 'regen') {
      await api('POST', `/api/projects/${S.pid}/script/regenerate`, { idea });
      await openProject(S.pid);
      toast('Script régénéré (les scènes verrouillées sont conservées)');
    } else {
      const body = { idea };
      const n = Number($('#aiNScenes').value);
      if (n) body.n_scenes = n;
      const result = await api('POST', '/api/script/generate', body);
      snapshotUndo();
      S.script.title = result.title;
      S.script.description = result.description;
      S.script.language = result.language;
      S.script.scenes = result.scenes;
      renderAll(); saveScript();
      toast(`${result.scenes.length} scènes générées`);
    }
  } catch (e) { toast(e.message, true); }
  busy(false);
}

/* ── Régénération IA d'une scène ── */
async function regenScene(i, what, directive) {
  const dir = directive !== undefined ? directive
            : ($('#insDirective')?.value || '').trim();
  busy(true, 'Régénération de la scène…');
  try {
    await api('POST', `/api/projects/${S.pid}/scenes/${i}/regenerate`, { what, directive: dir });
    await openProject(S.pid);
    toast('Scène régénérée');
  } catch (e) { toast(e.message, true); }
  busy(false);
}

/* ── Presets motion design (remplissent la directive) ── */
const MOTION_PRESETS = {
  'Cinétique': 'typographie cinétique : le texte apparaît mot à mot (translation + opacity + léger blur), ease-out expo, staggering 80 ms',
  'Minimal': 'minimalisme élégant : grandes formes géométriques, transitions lentes et douces, beaucoup d\'espace, 2 couleurs max',
  'Néon': 'esthétique néon : traits lumineux avec glow (box-shadow/text-shadow), fond très sombre, fines particules flottantes',
  'Bounce': 'cartoon dynamique : overshoots, squash & stretch, rebonds élastiques cubic-bezier(.34,1.56,.64,1)',
  'Ciné': 'cinématique sombre : révélation lente du texte, vignette, grain subtil, mouvements de caméra très lents (scale 1.0→1.05)',
  'Data': 'data-viz : barres et compteurs animés, chiffres qui montent en easing expo, grille technique en fond',
};
function renderPresets() {
  const el = $('#insPresets');
  if (!el) return;
  el.innerHTML = '';
  Object.entries(MOTION_PRESETS).forEach(([k, v]) => {
    const b = document.createElement('button');
    b.className = 'chip preset';
    b.textContent = k;
    b.title = v;
    b.addEventListener('click', () => { $('#insDirective').value = v; });
    el.appendChild(b);
  });
}

/* ── Éditeur de code ── */
async function loadCodeTab() {
  const i = S.sceneIdx;
  $('#codeSceneNum').textContent = i + 1;
  try {
    const code = await api('GET', `/api/projects/${S.pid}/scenes/${i}/code`);
    /* évite d'écraser l'édition en cours si l'utilisateur a déjà changé de scène */
    if (S.sceneIdx !== i) return;
    S._code = code;
    showCode();
    previewCode();
  } catch {}
}
function showCode() {
  const lang = S.codeLang;
  $('#codeEditor').value = S._code?.[lang] || '';
}
async function saveCode() {
  const i = S.sceneIdx;
  S._code = S._code || { html: '', css: '', js: '' };
  S._code[S.codeLang] = $('#codeEditor').value;
  const r = await api('PUT', `/api/projects/${S.pid}/scenes/${i}/code`, {
    html: S._code.html, css: S._code.css, js: S._code.js,
  });
  if (r.warnings?.length) {
    $('#codeMsg').textContent = '⚠ ' + r.warnings.join(' · ');
    $('#codeMsg').className = 'msg err';
  } else {
    $('#codeMsg').textContent = '✓ code sauvegardé';
    $('#codeMsg').className = 'msg ok';
  }
  previewCode();
  ovLoadScene(i);           // rafraîchit le viewport avec le nouveau code
  renderTimeline();
}
function composeDoc(html, css, js) {
  let doc = html || '<!DOCTYPE html><html><head></head><body></body></html>';
  doc = /<\/head>/i.test(doc) ? doc.replace(/<\/head>/i, `<style>${css}</style></head>`)
                              : doc + `<style>${css}</style>`;
  doc = /<\/body>/i.test(doc) ? doc.replace(/<\/body>/i, `<script>${js}<\/script></body>`)
                              : doc + `<script>${js}<\/script>`;
  return doc;
}
function previewCode() {
  const i = S.sceneIdx;
  if (S._code) S._code[S.codeLang] = $('#codeEditor').value;
  const html = S._code?.html || '';
  const css = S._code?.css || '';
  const js = S._code?.js || '';
  $('#codePreview').srcdoc = composeDoc(html, css, js);
  const [W, H] = sceneSize();
  fitIframe($('#codePreview'), $('#cpWrap'), W, H);
  const s = S.script.scenes[i];
  if (s) $('#previewInfo').textContent = `scène ${i + 1} · ${s.duration}s · ${(s.text || '').slice(0, 60)}`;
}
async function resetCode() {
  if (!confirm('Créer un snapshot puis revenir à la version IA d\'origine ?')) return;
  await api('POST', `/api/projects/${S.pid}/versions`, { label: 'avant reset code' });
  toast('Snapshot créé. Utilise l\'onglet Versions pour restaurer un code IA précis.');
}
async function regenCodeAI() {
  busy(true, 'L\'IA réécrit le code de la scène…');
  try {
    await api('POST', `/api/projects/${S.pid}/scenes/${S.sceneIdx}/regenerate`, { what: 'code' });
    await loadCodeTab();
    await ovLoadScene(S.sceneIdx);
    toast('Code régénéré par l\'IA');
  } catch (e) { toast(e.message, true); }
  busy(false);
}

/* ── Voix off ── */
async function loadVoices() {
  let voices;
  try { voices = await api('GET', '/api/voices'); }
  catch (e) { toast('Liste des voix indisponible : ' + e.message, true); return; }
  if (!voices || !Object.keys(voices).length) {
    toast('Aucune voix edge-tts disponible', true);
    return;
  }
  const sel = $('#voiceSelect');
  const curv = sel.value;
  sel.innerHTML = '';
  const langs = Object.keys(voices).sort();
  const fr = langs.filter(l => l.startsWith('fr'));
  const others = langs.filter(l => !l.startsWith('fr'));
  [...fr, ...others].forEach(lang => {
    const g = document.createElement('optgroup');
    g.label = lang;
    (voices[lang] || []).forEach(v => {
      const o = document.createElement('option');
      o.value = v.name;
      o.textContent = `${v.name} (${v.gender === 'Female' ? 'F' : 'M'})`;
      g.appendChild(o);
    });
    sel.appendChild(g);
  });
  const cfg = S.script.voice || {};
  sel.value = cfg.name || curv || sel.querySelector('option')?.value || '';
  $('#voiceRate').value = cfg.rate || '+0%';
  $('#voiceVolume').value = cfg.volume || '+0%';
  $('#voicePitch').value = cfg.pitch || '+0Hz';
}
function renderVoice() {
  const el = $('#voiceScenes');
  el.innerHTML = '';
  (S.script.scenes || []).forEach((s, i) => {
    const d = document.createElement('div');
    d.className = 'scene-item' + (i === S.sceneIdx ? ' sel' : '');
    const a = s.audio || {};
    const dur = a.duration ? `${a.duration.toFixed(1)}s` : (a.custom ? 'custom' : '—');
    d.innerHTML = `
      <div class="num">${i + 1}</div>
      <div class="main">
        <div>${esc((s.text || '').slice(0, 100))}${s.text?.length > 100 ? '…' : ''}</div>
        <div class="row" style="margin:0">
          <span class="hint">audio : ${dur}${s.silence ? ' · silence' : ''}</span>
          ${a.custom || a.duration ? `<button class="btn" data-a="play">▶</button>` : ''}
        </div>
      </div>`;
    d.addEventListener('click', e => {
      if (e.target.closest('[data-a=play]')) playAudio(i);
      else selectScene(i);
    });
    el.appendChild(d);
  });
}
function playAudio(i) {
  const a = $('#audioPlayer');
  a.src = `/api/projects/${S.pid}/audio/${i}?t=${Date.now()}`;
  a.play().catch(() => {});
}
async function ttsAll() {
  busy(true, 'Synthèse de toute la voix off…');
  try {
    await saveVoiceCfg();
    await api('POST', `/api/projects/${S.pid}/tts`, {});
    await openProject(S.pid);
    toast('Voix off générée');
  } catch (e) { toast(e.message, true); }
  busy(false);
}
async function ttsScene() {
  busy(true, `Synthèse scène ${S.sceneIdx + 1}…`);
  try {
    await saveVoiceCfg();
    await api('POST', `/api/projects/${S.pid}/tts`, { index: S.sceneIdx });
    await openProject(S.pid);
    toast('Voix générée');
  } catch (e) { toast(e.message, true); }
  busy(false);
}
async function saveVoiceCfg() {
  S.script.voice = {
    name: $('#voiceSelect').value,
    rate: $('#voiceRate').value,
    volume: $('#voiceVolume').value,
    pitch: $('#voicePitch').value,
  };
  saveScript();
}
async function uploadVoice(ev) {
  const f = ev.target.files[0];
  if (!f) return;
  const b64 = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result.split(',')[1]); fr.readAsDataURL(f); });
  await api('POST', `/api/projects/${S.pid}/audio/upload`, { index: S.sceneIdx, data_b64: b64, ext: f.name.split('.').pop() });
  toast('Voix custom uploadée pour la scène ' + (S.sceneIdx + 1));
  await openProject(S.pid);
  ev.target.value = '';
}

/* ── Style global ── */
function renderStyle() {
  const st = S.script.style || {};
  $('#stPrimary').value = st.primary || '#7C5CFF';
  $('#stSecondary').value = st.secondary || '#0E0E12';
  $('#stBackground').value = st.background || '#0E0E12';
  $('#stFont').value = st.font || 'Inter';
  $('#stAspect').value = st.aspect || '16:9';
  $('#stRes').value = st.resolution || 1080;
  $('#stFps').value = st.fps || 30;
}
async function saveStyle() {
  S.script.style = {
    primary: $('#stPrimary').value, secondary: $('#stSecondary').value,
    background: $('#stBackground').value, font: $('#stFont').value,
    aspect: $('#stAspect').value, resolution: Number($('#stRes').value),
    fps: Number($('#stFps').value),
  };
  saveScript();
  fitViewport(); ovInfoUpdate();
  toast('Style appliqué');
}

/* ── Sous-titres ── */
function renderSubtitles() {
  const st = S.script.subtitle_style || {};
  $('#subEnabled').checked = st.enabled !== false;
  $('#subSize').value = st.size || 5;
  $('#subPos').value = st.position || 'bottom';
  $('#subColor').value = st.color || '#FFFFFF';
  $('#subOutline').checked = !!st.outline;
  $('#subBg').checked = !!st.background;
  const el = $('#subList');
  el.innerHTML = '';
  let t = 0;
  (S.script.scenes || []).forEach((s, i) => {
    const dur = s.duration || 4;
    const words = s.audio?.words || [];
    if (!words.length || s.silence) { t += dur; return; }
    for (let j = 0; j < words.length; j += 7) {
      const line = words.slice(j, j + 7);
      const start = (t + line[0].t).toFixed(2);
      const end = (t + line[line.length - 1].t + line[line.length - 1].d).toFixed(2);
      const div = document.createElement('div');
      div.className = 'sub-line';
      div.innerHTML = `
        <span class="mono hint" style="min-width:110px">${start} → ${end}</span>
        <input style="flex:1" value="${esc(line.map(w => w.w).join(' '))}" data-i="${i}" data-j="${j}">
        <span class="hint">s${i + 1}</span>`;
      el.appendChild(div);
    }
    t += dur;
  });
}
async function saveSubStyle() {
  S.script.subtitle_style = {
    enabled: $('#subEnabled').checked, size: Number($('#subSize').value),
    position: $('#subPos').value, color: $('#subColor').value,
    outline: $('#subOutline').checked, background: $('#subBg').checked,
  };
  saveScript(); toast('Style des sous-titres sauvegardé');
}
async function exportSrt() {
  const r = await fetch(`/api/projects/${S.pid}/subtitles/srt`);
  if (!r.ok) { toast('Génère la voix off d\'abord', true); return; }
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = `${S.script.title || S.pid}.srt`; a.click();
}

/* ══ Timeline : règle · clips · playhead · scrub · zoom ══ */
function sceneStart(i) {
  let a = 0;
  const sc = S.script?.scenes || [];
  for (let k = 0; k < i && k < sc.length; k++) a += sc[k].duration || 4;
  return a;
}
function sceneAt(t) {
  let acc = 0;
  const sc = S.script?.scenes || [];
  for (let i = 0; i < sc.length; i++) {
    const d = sc[i].duration || 4;
    if (t < acc + d) return i;
    acc += d;
  }
  return Math.max(0, sc.length - 1);
}
function renderTimeline() {
  const scenes = S.script?.scenes || [];
  const total = scenes.reduce((a, s) => a + (s.duration || 4), 0);
  S._total = total;
  $('#tlInner').style.width = (S.tlZoom * 100) + '%';
  /* règle graduée */
  const step = total <= 15 ? 1 : total <= 45 ? 2 : total <= 120 ? 5 : total <= 300 ? 15 : 30;
  let h = '';
  for (let t = 0; t <= total + 1e-6; t += step) {
    h += `<div class="tl-tick" style="left:${(t / total * 100).toFixed(3)}%"><span>${fmtTc(t)}</span></div>`;
  }
  $('#tlRuler').innerHTML = h || '';
  /* clips */
  const track = $('#tlTrack');
  track.innerHTML = '';
  scenes.forEach((s, i) => {
    const b = document.createElement('div');
    b.className = 'tl-block' + (i === S.sceneIdx ? ' sel' : '');
    b.style.width = `calc(${((s.duration || 4) / total * 100).toFixed(3)}% - 2px)`;
    b.innerHTML = `<span>${i + 1}</span><span class="tl-dur">${(s.duration || 4).toFixed(1)}s</span><div class="tl-edge"></div>`;
    b.title = `scène ${i + 1} · ${(s.duration || 4).toFixed(1)}s — ${s.text || ''}`;
    b.addEventListener('click', e => {
      if (e.target.closest('.tl-edge')) return;   // le bord = redimensionner
      selectScene(i);
    });
    /* redimensionnement par le bord droit */
    let startX = 0, startW = 0, dragging = false;
    const edge = b.querySelector('.tl-edge');
    edge.addEventListener('pointerdown', e => {
      e.stopPropagation(); dragging = true; startX = e.clientX; startW = b.offsetWidth;
      edge.setPointerCapture(e.pointerId);
    });
    edge.addEventListener('pointermove', e => {
      if (!dragging) return;
      const trackW = track.getBoundingClientRect().width || 1;
      const dx = e.clientX - startX;
      const ns = Math.max(1, Math.min(30, Math.round((startW + dx) / trackW * total * 2) / 2));
      b.style.width = `calc(${(ns / total * 100).toFixed(3)}% - 2px)`;
      b.dataset.newDur = ns;
      b.querySelector('.tl-dur').textContent = ns.toFixed(1) + 's';
    });
    edge.addEventListener('pointerup', () => {
      if (dragging && b.dataset.newDur) {
        snapshotUndo();
        s.duration = Number(b.dataset.newDur);
        saveScript();
        renderTimeline(); renderSceneList(); renderInspectorScene(); renderPreview();
        selectScene(i, { skipCodeFetch: true });
      }
      dragging = false; delete b.dataset.newDur;
    });
    track.appendChild(b);
  });
  updatePlayhead();
}
function updatePlayhead() {
  const pct = S._total ? (S.tlT / S._total * 100) : 0;
  $('#tlCursor').style.left = pct + '%';
  const txt = `${fmtTc(S.tlT)} / ${fmtTc(S._total || 0)}`;
  $('#tlTime').textContent = txt;
  $('#ovTime').textContent = txt;
  /* garde le playhead visible pendant la lecture */
  if (S.ovPlaying) {
    const sc = $('#tlScroll'), inner = $('#tlInner');
    const px = S._total ? (S.tlT / S._total) * inner.offsetWidth : 0;
    if (px < sc.scrollLeft + 20 || px > sc.scrollLeft + sc.clientWidth - 40) {
      sc.scrollLeft = Math.max(0, px - sc.clientWidth * 0.3);
    }
  }
}
function seekTo(t) {
  if (!S.script?.scenes?.length) return;
  S.tlT = Math.max(0, Math.min(S._total || 0, t));
  const i = sceneAt(S.tlT);
  if (i !== S.sceneIdx) selectScene(i);
  else updatePlayhead();
}
function setZoom(z) {
  S.tlZoom = Math.max(1, Math.min(6, z));
  $('#tlZoomRange').value = S.tlZoom;
  renderTimeline();
}

/* ── Lecteur unifié (viewport + timeline + audio) ── */
let _ovT0 = 0, _ovStart = 0;          // horloge réelle : _ovStart + (now-_ovT0)/1000
function playToggle() {
  if (!S.script?.scenes?.length) return;
  S.ovPlaying = !S.ovPlaying;
  $('#ovPlay').textContent = S.ovPlaying ? '⏸' : '▶';
  $('#tlPlay').textContent = S.ovPlaying ? '⏸' : '▶';
  if (!S.ovPlaying) { $('#audioPlayer').pause(); return; }
  if (S._total && S.tlT >= S._total - 0.05) { S.tlT = 0; }   // rejoue depuis le début
  _ovT0 = performance.now();
  _ovStart = S.tlT;
  S._ovScene = sceneAt(S.tlT);
  if (S._ovScene !== S.sceneIdx) selectScene(S._ovScene);
  ovTick();
  requestAnimationFrame(_ovRaf);       // playhead fluide entre deux ticks
}
function _ovRaf() {
  if (!S.ovPlaying) return;
  S.tlT = _ovStart + (performance.now() - _ovT0) / 1000;
  updatePlayhead();
  requestAnimationFrame(_ovRaf);
}
function stopPlayback() {
  if (S.ovPlaying) playToggle();
  $('#audioPlayer')?.pause();
}
function playAudioIfAny(i) {
  const s = S.script.scenes[i];
  if (s && !s.silence && (s.audio?.duration || s.audio?.custom)) playAudio(i);
}
function ovTick() {
  if (!S.ovPlaying) return;
  /* temps dérivé de l'horloge réelle : reste exact même si les timers sont
     bridés (onglet en arrière-plan, webview) — seule la fluidité en pâtit */
  S.tlT = _ovStart + (performance.now() - _ovT0) / 1000;
  if (S.tlT >= S._total) {
    if (S.loop) {
      S.tlT = 0; _ovT0 = performance.now(); _ovStart = 0;
      selectScene(0);
    } else { S.tlT = S._total; updatePlayhead(); playToggle(); return; }
  } else {
    updatePlayhead();
    const i = sceneAt(S.tlT);
    if (i !== S._ovScene) {
      $('#audioPlayer').pause();
      selectScene(i);
      playAudioIfAny(i);
    }
  }
  setTimeout(() => ovTick(), 100);
}

/* ── Viewport ── */
function fitViewport() {
  const stage = $('#vpStage');
  const box = $('#ovFrame');
  if (!stage || !box) return;
  const [W, H] = sceneSize();
  const r = stage.getBoundingClientRect();
  const k = Math.max(0, Math.min((r.width - 16) / W, (r.height - 16) / H));
  box.style.width = Math.max(120, W * k) + 'px';
  box.style.height = Math.max(68, H * k) + 'px';
  fitIframe($('#ovViewport'), box, W, H);
}
async function ovLoadScene(i) {
  const s = S.script?.scenes?.[i];
  if (!s) return;
  try {
    const code = await api('GET', `/api/projects/${S.pid}/scenes/${i}/code`);
    if (S.sceneIdx !== i) return;      // scène changée entre-temps
    $('#ovViewport').srcdoc = composeDoc(code.html, code.css, code.js);
  } catch {
    $('#ovViewport').srcdoc = '<!DOCTYPE html><html><body style="background:#111;color:#777;font-family:sans-serif;display:grid;place-items:center;height:100vh;margin:0">Aucun code pour cette scène</body></html>';
  }
}
function renderOverview() {
  if (!S.script) return;
  fitViewport();
  ovInfoUpdate();
}
function ovInfoUpdate() {
  const s = cur();
  const st = S.script?.style || {};
  if (!s) { $('#ovInfo').textContent = ''; return; }
  $('#ovInfo').textContent =
    `scène ${S.sceneIdx + 1}/${S.script.scenes.length} · ${(Number(s.duration) || 0).toFixed(1)}s` +
    ` · ${st.aspect || '16:9'} · ${st.resolution || 1080}p · ${st.fps || 30}fps`;
}

/* ── Stats (chips du transport) ── */
function renderPreview() {
  if (!S.script) return;
  const sc = S.script.scenes || [];
  const totalDur = sc.reduce((a, s) => a + (Number(s.duration) || 0), 0);
  let voiced = 0, silenced = 0, custom = 0;
  sc.forEach(s => {
    if (s.silence) silenced++;
    else if (s.audio?.custom) custom++;
    else if (s.audio?.duration) voiced++;
  });
  const noVoice = sc.length - voiced - silenced - custom;
  const chips = [
    `${sc.length} scène${sc.length > 1 ? 's' : ''}`,
    fmtDur(totalDur),
  ];
  if (voiced) chips.push(`🎙 ${voiced}`);
  if (custom) chips.push(`🎵 ${custom}`);
  if (silenced) chips.push(`🔇 ${silenced}`);
  if (noVoice) chips.push(`⚠ ${noVoice} sans voix`);
  $('#pvStats').innerHTML = chips.map((c, k) =>
    `<span class="chip${c.startsWith('⚠') ? ' warn' : ''}">${esc(c)}</span>`).join('');
}

/* ── Assets ── */
async function renderAssets() {
  if (!S.pid) return;
  try {
    const list = await api('GET', `/api/projects/${S.pid}/assets`);
    const el = $('#assetList');
    el.innerHTML = list.length ? '' : '<p class="hint">Aucun asset — upload des images, musiques, logos…</p>';
    list.forEach(name => {
      const d = document.createElement('div');
      d.className = 'sub-line';
      d.innerHTML = `
        <span class="mono" style="flex:1">${esc(name)}</span>
        <span class="mono hint">{{asset:${esc(name)}}}</span>
        <button class="btn danger" data-a="del">🗑</button>`;
      d.querySelector('[data-a=del]').addEventListener('click', async () => {
        await api('DELETE', `/api/projects/${S.pid}/assets/${name}`);
        renderAssets();
      });
      el.appendChild(d);
    });
  } catch {}
}
async function uploadAsset(ev) {
  const f = ev.target.files[0];
  if (!f) return;
  const b64 = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result.split(',')[1]); fr.readAsDataURL(f); });
  await api('POST', `/api/projects/${S.pid}/assets`, { name: f.name, data_b64: b64 });
  toast('Asset uploadé : ' + f.name);
  renderAssets(); ev.target.value = '';
}

/* ── Versions ── */
async function renderVersions() {
  if (!S.pid) return;
  try {
    const list = await api('GET', `/api/projects/${S.pid}/versions`);
    const el = $('#versionList');
    el.innerHTML = list.length ? '' : '<p class="hint">Aucune version pour l\'instant.</p>';
    list.forEach(v => {
      const d = document.createElement('div');
      d.className = 'sub-line';
      d.innerHTML = `
        <b style="min-width:30px">v${v.n}</b>
        <span style="flex:1">${esc(v.label)}</span>
        <span class="hint mono">${v.time}</span>
        <button class="btn" data-a="restore">Restaurer</button>`;
      d.querySelector('[data-a=restore]').addEventListener('click', async () => {
        if (!confirm(`Restaurer la version v${v.n} ?`)) return;
        await api('POST', `/api/projects/${S.pid}/versions/${v.n}/restore`);
        await openProject(S.pid);
        toast(`Version v${v.n} restaurée`);
      });
      el.appendChild(d);
    });
  } catch {}
}
async function manualSnapshot() {
  const r = await api('POST', `/api/projects/${S.pid}/versions`, { label: 'manuel' });
  toast(`Version v${r.n} créée`);
  renderVersions();
}

/* ── Config IA ── */
const PROVIDER_LABELS = {
  openai: 'OpenAI', anthropic: 'Anthropic', google: 'Google (Gemini)',
  xkiro: 'Xkiro', xai: 'xAI (Grok)', agnes: 'Agnes AI', mistral: 'Mistral',
  ollama: 'Ollama (local)', openrouter: 'OpenRouter',
};
async function loadCfg() {
  const [c, presets] = await Promise.all([
    api('GET', '/api/ai/config'),
    api('GET', '/api/ai/presets'),
  ]);
  S.presets = presets || {};
  const sel = $('#cfgProvider');
  sel.innerHTML = '';
  const none = document.createElement('option');
  none.value = ''; none.textContent = '— non configuré —';
  sel.appendChild(none);
  for (const [key] of Object.entries(S.presets)) {
    const o = document.createElement('option');
    o.value = key;
    o.textContent = PROVIDER_LABELS[key] || key;
    sel.appendChild(o);
  }
  sel.value = c.provider;
  $('#cfgBase').value = c.base_url;
  $('#cfgModel').value = c.model;
  $('#cfgTemp').value = c.temperature;
  $('#cfgKey').placeholder = c.key_hint ? `définie (${c.key_hint})` : 'laisser vide pour conserver';
}
async function saveCfg() {
  await api('POST', '/api/ai/config', {
    provider: $('#cfgProvider').value, base_url: $('#cfgBase').value,
    model: $('#cfgModel').value,
    api_key: $('#cfgKey').value || null,
    temperature: Number($('#cfgTemp').value),
  });
  const msg = $('#cfgMsg');
  msg.textContent = '✓ configuration enregistrée';
  msg.className = 'msg ok';
}
async function testCfg() {
  const msg = $('#cfgMsg');
  msg.textContent = 'test…'; msg.className = 'msg';
  try {
    const r = await api('POST', '/api/ai/config/test', {
      provider: $('#cfgProvider').value, base_url: $('#cfgBase').value,
      model: $('#cfgModel').value, api_key: $('#cfgKey').value || null,
    });
    msg.textContent = `✓ ${r.model} répond : ${r.reply}`;
    msg.className = 'msg ok';
  } catch (e) {
    msg.textContent = '✗ ' + e.message;
    msg.className = 'msg err';
  }
}

/* ── Rendu vidéo ── */
async function renderVideo() {
  busy(true, 'Rendu MP4 en cours (Playwright + ffmpeg)…');
  try {
    const r = await api('POST', `/api/projects/${S.pid}/render_full`, {});
    busy(false);
    toast(`Vidéo rendue (${r.duration.toFixed(1)} s) — téléchargement…`);
    const a = document.createElement('a');
    a.href = r.file; a.download = `${S.script.title || 'video'}.mp4`; a.click();
  } catch (e) { busy(false); toast(e.message, true); }
}

/* ══ Onglets ══ */
/* bibliothèque gauche : scènes / assets */
$$('.left-tabs button').forEach(b => b.addEventListener('click', () => {
  $$('.left-tabs button').forEach(x => x.classList.toggle('on', x === b));
  $('#leftScenes').hidden = b.dataset.lt !== 'scenes';
  $('#leftAssets').hidden = b.dataset.lt !== 'assets';
  if (b.dataset.lt === 'assets') renderAssets();
}));
/* inspecteur droit */
$$('.insp-tabs button').forEach(b => b.addEventListener('click', () => {
  $$('.insp-tabs button').forEach(x => x.classList.toggle('on', x === b));
  $$('.insp-sec').forEach(s => s.classList.remove('on'));
  const id = 'insp' + b.dataset.insp[0].toUpperCase() + b.dataset.insp.slice(1);
  document.getElementById(id)?.classList.add('on');
  if (b.dataset.insp === 'code') { loadCodeTab(); }
  if (b.dataset.insp === 'voice') loadVoices();
  if (b.dataset.insp === 'versions') renderVersions();
}));
/* onglets de code (html/css/js) */
$$('.code-tabs button').forEach(b => b.addEventListener('click', () => {
  if (S._code) S._code[S.codeLang] = $('#codeEditor').value;
  S.codeLang = b.dataset.lang;
  $$('.code-tabs button').forEach(x => x.classList.toggle('on', x === b));
  showCode();
}));

/* ══ Événements ══ */
$('#btnNewProject').addEventListener('click', newProject);
$('#btnDeleteProject').addEventListener('click', deleteProject);
$('#projectSelect').addEventListener('change', e => openProject(e.target.value));
$('#btnSave').addEventListener('click', saveNow);
$('#btnRender').addEventListener('click', renderVideo);
$('#btnUndo').addEventListener('click', doUndo);
$('#btnRedo').addEventListener('click', doRedo);
$('#projTitle').addEventListener('change', e => { S.script.title = e.target.value; saveScript(); });
$('#projDesc').addEventListener('change', e => { S.script.description = e.target.value; saveScript(); });
$('#btnGenScript').addEventListener('click', () => genScript('gen'));
$('#btnRegenScript').addEventListener('click', () => {
  if (confirm('Régénérer tout le script ? Les scènes verrouillées seront conservées.')) genScript('regen');
});
$('#btnAddScene').addEventListener('click', async () => {
  snapshotUndo();
  await api('POST', `/api/projects/${S.pid}/scenes`, { after: -1 });
  await openProject(S.pid);
});
$('#btnGenAllCode').addEventListener('click', generateMissingCode);

/* inspecteur scène */
$('#insText').addEventListener('change', e => {
  const s = cur(); if (!s) return;
  snapshotUndo(); s.text = e.target.value;
  saveScript(); renderSceneList(); renderVoice();
});
$('#insPrompt').addEventListener('change', e => {
  const s = cur(); if (!s) return;
  snapshotUndo(); s.visual_prompt = e.target.value;
  saveScript();
});
$('#insDur').addEventListener('change', e => {
  const s = cur(); if (!s) return;
  snapshotUndo();
  s.duration = Math.max(1, Math.min(30, Number(e.target.value) || 4));
  saveScript(); renderSceneList(); renderTimeline(); renderPreview(); ovInfoUpdate();
});
$('#insLock').addEventListener('click', () => {
  const s = cur(); if (!s) return;
  snapshotUndo(); s.locked = !s.locked;
  saveScript(); renderSceneList(); renderInspectorScene();
});
$('#insRegenText').addEventListener('click', () => regenScene(S.sceneIdx, 'text'));
$('#insRegenCode').addEventListener('click', () => regenScene(S.sceneIdx, 'code'));
$('#insRegenBoth').addEventListener('click', () => regenScene(S.sceneIdx, 'both'));
$('#insTts').addEventListener('click', ttsScene);
$('#insPlay').addEventListener('click', () => playAudio(S.sceneIdx));
$('#insSilence').addEventListener('click', () => {
  const s = cur(); if (!s) return;
  snapshotUndo(); s.silence = !s.silence;
  saveScript(); renderSceneList(); renderInspectorScene(); renderPreview();
});

/* éditeur de code */
$('#btnCodeSave').addEventListener('click', saveCode);
$('#btnCodePreview').addEventListener('click', previewCode);
$('#btnCodeReset').addEventListener('click', resetCode);
$('#btnCodeAI').addEventListener('click', regenCodeAI);
$('#btnCodeValidate').addEventListener('click', saveCode);

/* voix */
$('#btnVoiceSave').addEventListener('click', async () => { await saveVoiceCfg(); toast('Config voix sauvegardée'); });
$('#btnTtsAll').addEventListener('click', ttsAll);
$('#btnTtsScene').addEventListener('click', ttsScene);
$('#voiceUpload').addEventListener('change', uploadVoice);

/* style + sous-titres */
$('#btnStyleSave').addEventListener('click', saveStyle);
$('#btnSubSave').addEventListener('click', saveSubStyle);
$('#btnSubSrt').addEventListener('click', exportSrt);

/* transport */
$('#ovPlay').addEventListener('click', playToggle);
$('#tlPlay').addEventListener('click', playToggle);
$('#ovPrev').addEventListener('click', () => selectScene(S.sceneIdx - 1));
$('#ovNext').addEventListener('click', () => selectScene(S.sceneIdx + 1));
$('#tlStart').addEventListener('click', () => seekTo(0));
$('#btnLoop').addEventListener('click', () => {
  S.loop = !S.loop;
  $('#btnLoop').classList.toggle('primary', S.loop);
  toast(S.loop ? 'Boucle activée' : 'Boucle désactivée');
});
$('#btnFs').addEventListener('click', () => {
  const w = $('#vpWrap');
  document.fullscreenElement ? document.exitFullscreen() : w.requestFullscreen?.();
});
document.addEventListener('fullscreenchange', () => setTimeout(fitViewport, 60));

/* zoom timeline */
$('#tlZoomIn').addEventListener('click', () => setZoom(S.tlZoom + 0.5));
$('#tlZoomOut').addEventListener('click', () => setZoom(S.tlZoom - 0.5));
$('#tlZoomRange').addEventListener('input', e => setZoom(Number(e.target.value)));

/* scrub : clic / glisser sur la timeline (hors clips) */
(() => {
  const el = $('#tlScroll');
  let down = false;
  const xToT = e => {
    const r = $('#tlInner').getBoundingClientRect();
    return (e.clientX - r.left) / r.width * (S._total || 0);
  };
  el.addEventListener('pointerdown', e => {
    if (e.target.closest('.tl-block')) return;
    down = true;
    el.setPointerCapture(e.pointerId);
    stopPlayback();
    seekTo(xToT(e));
  });
  el.addEventListener('pointermove', e => { if (down) seekTo(xToT(e)); });
  el.addEventListener('pointerup', () => down = false);
  el.addEventListener('wheel', e => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    setZoom(S.tlZoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
  }, { passive: false });
})();

/* assets + versions + IA */
$('#assetUpload').addEventListener('change', uploadAsset);
$('#btnSnapshot').addEventListener('click', manualSnapshot);
$('#btnCfgSave').addEventListener('click', saveCfg);
$('#btnCfgTest').addEventListener('click', testCfg);
$('#cfgProvider').addEventListener('change', e => {
  const p = S.presets && S.presets[e.target.value];
  if (p) { $('#cfgBase').value = p.base_url; $('#cfgModel').value = p.model; }
});

/* ══ Raccourcis clavier ══ */
document.addEventListener('keydown', e => {
  const tg = e.target.tagName;
  const typing = tg === 'INPUT' || tg === 'TEXTAREA' || tg === 'SELECT';
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveNow(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); doUndo(); }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) { e.preventDefault(); doRedo(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); renderVideo(); }
  if (typing) return;
  if (e.code === 'Space') { e.preventDefault(); playToggle(); }
  if (e.key === 'ArrowLeft') selectScene(S.sceneIdx - 1);
  if (e.key === 'ArrowRight') selectScene(S.sceneIdx + 1);
});

/* resize : réadapte le viewport (+ aperçu code s'il est visible) */
window.addEventListener('resize', () => {
  fitViewport();
  if ($('#inspCode').classList.contains('on')) previewCode();
});

/* ══ Démarrage ══ */
renderPresets();
loadProjects().then(() => { loadCfg(); fitViewport(); }).catch(e => toast(e.message, true));
