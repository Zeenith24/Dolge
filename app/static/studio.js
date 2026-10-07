// Dolge Reel Studio – front-end logic
const $ = id => document.getElementById(id);

const state = {
  user: null, cfg: null, assets: [], pinned: [], videos: [],
  voice: 'oliver', gender: 'all', music: null, caption: 'cut_paper',
  current: null,            // video object currently shown in the phone
  pollTimer: null, previewAudio: null, previewBusy: false,
};

const TONES = {
  cinematic: { voice: 'oliver', speed: 0.95, pitch: -1, caption: 'typewriter', label: 'Cinematic' },
  suspense:  { voice: 'kai',    speed: 0.95, pitch: -2, caption: 'neon',       label: 'Mystery / Hook' },
  upbeat:    { voice: 'jasper', speed: 1.15, pitch: 1,  caption: 'marker',     label: 'Upbeat Paced' },
  cozy:      { voice: 'aria',   speed: 0.95, pitch: 1,  caption: 'cut_paper',  label: 'Nostalgic Cozy' },
};

const SPARKS = [
  "My roommate swore the apartment upstairs was empty. Then I found a note under my door, written in my own handwriting, telling me not to go to work tomorrow. I ignored it. That was my first mistake.",
  "I asked my boss for a raise, and she laughed. Six months later, I found out she'd been quietly paying my replacement double. So I did the one thing nobody expected. I quit on the day of the biggest client meeting.",
  "Three rules to finding the freshest street matcha in Kyoto before the morning crowds wake up. Rule one: follow the elderly locals, not the signs. Rule two: never order the sweet one first.",
  "I took a sleeper train across Scotland and discovered a handwritten notebook between the seat cushions. The last page said, if you're reading this, don't get off at the next stop.",
];

// ------------------------------------------------------------------ boot
async function boot() {
  try {
    [state.user, state.cfg] = await Promise.all([api('/api/auth/me'), api('/api/config')]);
  } catch (e) { return; }
  $('user-name').textContent = state.user.name.split(' ')[0].toUpperCase();
  $('avatar').textContent = state.user.name.trim()[0]?.toUpperCase() || '?';
  setCredits(state.user.credits);
  renderVoices(); renderMusic(); renderCaptions(); updateEstimate(); bindUI();
  await Promise.all([loadAssets(), loadVideos()]);
  if (!state.pinned.length && state.assets.length) state.pinned = [state.assets[0].id];
  renderAssets(); renderSequence(); renderPreview(); startPolling();
}

function setCredits(n) {
  state.user.credits = n;
  $('credits').textContent = `${n} Credit${n === 1 ? '' : 's'}`;
  $('credit-note').textContent = n > 0 ? `Uses 1 reel credit (${n} remaining)` : 'You are out of credits';
}

// ------------------------------------------------------------------ data
async function loadAssets() { state.assets = await api('/api/assets'); }
async function loadVideos() {
  state.videos = await api('/api/videos');
  renderArchive();
}

// ------------------------------------------------------------------ voices
function renderVoices() {
  $('voice-grid').innerHTML = state.cfg.voices.map(v => {
    const active = v.id === state.voice;
    const hidden = state.gender !== 'all' && v.gender !== state.gender;
    return `<label data-voice="${v.id}" class="voice-card ${active ? 'active' : ''} relative ${active ? 'bg-secondary-fixed/30' : 'bg-surface-container-lowest'} border-2 border-on-surface rounded-lg p-3 cursor-pointer tactile-shadow-sm hover:-translate-y-0.5 transition-transform ${hidden ? 'hidden' : 'block'}">
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-2"><span class="text-2xl">${v.emoji}</span>
          <div><span class="text-sm font-bold block">${escapeHtml(v.name)}</span><span class="text-[10px] text-primary font-bold">${escapeHtml(v.tag)}</span></div></div>
        <span class="${active ? 'flex' : 'hidden'} w-5 h-5 rounded-full bg-secondary-container border border-on-surface items-center justify-center font-bold text-xs">✓</span>
      </div>
      <p class="text-xs text-on-surface-variant mt-2">${escapeHtml(v.desc)}</p>
    </label>`;
  }).join('');
  $('audition-sub').textContent = voiceById(state.voice).name;
  renderPreview();
}
const voiceById = id => state.cfg.voices.find(v => v.id === id);

function setGenderTab(g) {
  state.gender = g;
  const on = ['bg-surface-container-lowest', 'border-2', 'border-on-surface', 'font-bold', 'tactile-shadow-sm'];
  document.querySelectorAll('.gender-tag').forEach(b => {
    const sel = b.dataset.g === g;
    on.forEach(c => b.classList.toggle(c, sel));
    b.classList.toggle('text-on-surface-variant', !sel);
  });
  renderVoices();
}

// ------------------------------------------------------------------ music / captions
function renderMusic() {
  const items = [{ id: null, title: '🔇 No music' }, ...state.cfg.music.map(m => ({ id: m.id, title: '🎵 ' + m.title }))];
  $('music-pills').innerHTML = items.map(m => {
    const sel = m.id === state.music;
    return `<button type="button" data-music="${m.id === null ? '' : escapeHtml(m.id)}" class="audio-pill ${sel ? 'bg-secondary-container text-on-secondary-container' : 'bg-surface-container-lowest text-on-surface hover:bg-secondary-fixed/50'} border-2 border-on-surface py-1 px-1.5 rounded text-left text-[11px] tactile-shadow-sm font-bold truncate">${escapeHtml(m.title)}</button>`;
  }).join('');
  if (!state.cfg.music.length) {
    $('music-pills').insertAdjacentHTML('afterend', '<p class="text-[10px] text-outline mt-1">Drop .mp3/.wav files into <b>assets/music/</b> and reload to add soundtracks.</p>');
  }
}

function renderCaptions() {
  $('caption-styles').innerHTML = state.cfg.captions.map(c => {
    const sel = c.id === state.caption;
    return `<button type="button" data-cap="${c.id}" class="${sel ? 'bg-secondary-container text-on-secondary-container border-2 border-on-surface tactile-shadow-sm font-bold' : 'bg-surface-container-lowest text-on-surface border border-outline-variant hover:border-on-surface'} py-2 px-1.5 rounded text-xs text-center">${c.label}</button>`;
  }).join('');
  renderPreview();
}

// ------------------------------------------------------------------ assets
function renderAssets() {
  $('asset-grid').innerHTML = state.assets.map(a => {
    const pinned = state.pinned.includes(a.id);
    return `<div data-asset="${a.id}" class="stock-card relative bg-surface-container-lowest border-2 border-on-surface rounded p-2 tactile-shadow-sm hover:-translate-y-0.5 transition-all">
      <div class="relative w-full aspect-[9/13] bg-surface-dim rounded overflow-hidden mb-1.5 border border-on-surface">
        ${a.has_thumb ? `<img class="w-full h-full object-cover" loading="lazy" src="/api/assets/${a.id}/thumb" alt="">` : ''}
        <div class="absolute top-1 left-1 bg-surface-container-lowest/90 px-1 py-0.5 rounded text-[9px] font-bold border border-on-surface">${a.mine ? 'MINE' : 'VAULT'} ● ${fmtTime(a.duration)}</div>
        ${pinned ? '<div class="absolute top-1 right-1 w-5 h-5 bg-secondary-fixed rounded-full border border-on-surface flex items-center justify-center text-xs font-bold">✓</div>' : ''}
        ${a.mine ? `<button data-del-asset="${a.id}" title="Delete upload" class="absolute bottom-1 right-1 w-5 h-5 bg-error text-on-error rounded-full border border-on-surface text-[10px] leading-none">✕</button>` : ''}
      </div>
      <div class="text-[11px] font-bold truncate">${escapeHtml(a.title)}</div>
      <button type="button" data-pin="${a.id}" class="w-full mt-1 ${pinned ? 'bg-secondary-fixed text-on-secondary-fixed' : 'bg-surface-container-high text-on-surface'} text-[10px] uppercase font-bold py-0.5 rounded border border-on-surface">${pinned ? 'Pinned ✓' : 'Pin'}</button>
    </div>`;
  }).join('') || '<p class="col-span-full text-sm text-on-surface-variant">No clips yet — upload some footage on the left, or drop videos into <b>input_videos/</b>.</p>';
  $('pin-count').textContent = `${state.pinned.length} clip${state.pinned.length === 1 ? '' : 's'} pinned`;
}

function renderSequence() {
  const byId = Object.fromEntries(state.assets.map(a => [a.id, a]));
  const items = state.pinned.map(id => byId[id]).filter(Boolean);
  $('seq-label').textContent = `Active Sequence Trail (${items.length} Clip${items.length === 1 ? '' : 's'})`;
  $('sequence').innerHTML = items.map((a, i) => `
    <div class="bg-surface-container-lowest p-1.5 rounded border border-on-surface text-center w-24 shrink-0">
      <div class="w-full h-10 bg-on-surface/10 rounded overflow-hidden mb-1">${a.has_thumb ? `<img class="w-full h-full object-cover" src="/api/assets/${a.id}/thumb" alt="">` : ''}</div>
      <span class="block text-[10px] font-bold truncate">${String(i + 1).padStart(2, '0')} ${escapeHtml(a.title)}</span>
      <span class="flex justify-center gap-1 mt-0.5">
        <button data-move="${a.id}:-1" class="text-[10px] px-1 border border-outline rounded ${i === 0 ? 'opacity-30' : ''}">◀</button>
        <button data-move="${a.id}:1" class="text-[10px] px-1 border border-outline rounded ${i === items.length - 1 ? 'opacity-30' : ''}">▶</button>
      </span>
    </div>`).join('') || '<span class="text-xs text-on-surface-variant self-center px-2">Pin at least one clip above.</span>';
}

function togglePin(id) {
  const i = state.pinned.indexOf(id);
  if (i >= 0) state.pinned.splice(i, 1);
  else if (state.pinned.length >= 8) return toast('You can pin up to 8 clips.', 'error');
  else state.pinned.push(id);
  renderAssets(); renderSequence(); renderPreview();
}

function movePin(id, delta) {
  const i = state.pinned.indexOf(id), j = i + delta;
  if (i < 0 || j < 0 || j >= state.pinned.length) return;
  [state.pinned[i], state.pinned[j]] = [state.pinned[j], state.pinned[i]];
  renderSequence(); renderPreview();
}

async function uploadFiles(files) {
  for (const file of files) {
    $('drop-icon').textContent = 'progress_activity';
    $('drop-icon').classList.add('animate-spin');
    $('drop-title').textContent = 'Uploading…';
    $('drop-sub').textContent = file.name;
    try {
      const fd = new FormData(); fd.append('file', file);
      const asset = await api('/api/assets/upload', { method: 'POST', body: fd });
      state.assets.unshift(asset);
      state.pinned.push(asset.id);
      toast(`Pinned “${asset.title}”`, 'ok');
    } catch (e) { toast(`${file.name}: ${e.message}`, 'error'); }
  }
  $('drop-icon').textContent = 'cloud_upload';
  $('drop-icon').classList.remove('animate-spin');
  $('drop-title').textContent = 'Pin Custom Clips';
  $('drop-sub').textContent = 'Drag an MP4/MOV here or click to browse (max 300 MB)';
  renderAssets(); renderSequence(); renderPreview();
}

// ------------------------------------------------------------------ estimate
function wordCount() { return ($('story').value.replace(/\[[^\]]*\]/g, ' ').trim().match(/\S+/g) || []).length; }
function updateEstimate() {
  const speed = parseFloat($('speed').value);
  const secs = wordCount() / (2.6 * speed);
  const max = state.cfg.max_duration;
  $('duration-est').innerHTML = `${wordCount()} words · approx. ${secs.toFixed(0)}s of voiceover` +
    (secs > max ? ` <b class="text-error">(over ${max}s – will be trimmed)</b>` : '');
  $('speed-val').textContent = speed.toFixed(2).replace(/0$/, '') + 'x';
  const p = parseInt($('pitch').value, 10);
  $('pitch-val').textContent = (p > 0 ? '+' : '') + p + 'st';
}

// ------------------------------------------------------------------ preview phone
function renderPreview() {
  const v = state.current;
  const img = $('preview-img'), vid = $('preview-video'), cap = $('preview-caption'), ov = $('progress-overlay');
  const busy = v && (v.status === 'queued' || v.status === 'processing');
  const done = v && v.status === 'done';

  ov.classList.toggle('hidden', !busy); ov.classList.toggle('flex', !!busy);
  if (busy) {
    $('progress-stage').textContent = v.stage || 'Working…';
    $('progress-bar').style.width = v.progress + '%';
    $('progress-pct').textContent = Math.round(v.progress) + '%';
  }

  if (done) {
    const src = `/api/videos/${v.id}/file`;
    if (!vid.src.endsWith(src)) { vid.src = src; }
    vid.classList.remove('hidden'); img.classList.add('hidden'); cap.innerHTML = '';
    $('phone-title').textContent = v.title;
    $('phone-sub').textContent = `${voiceById(v.voice)?.name || v.voice} voice · ${fmtTime(v.duration)}`;
    $('btn-download').href = `/api/videos/${v.id}/file?download=1`;
    $('btn-download').classList.remove('btn-disabled');
    $('btn-publish').classList.remove('btn-disabled');
    $('btn-publish').lastChild.textContent = v.share_token ? 'Copy Share Link' : 'Publish Reel';
  } else {
    vid.pause(); vid.removeAttribute('src'); vid.classList.add('hidden');
    $('btn-download').classList.add('btn-disabled'); $('btn-download').href = '#';
    $('btn-publish').classList.add('btn-disabled'); $('btn-publish').lastChild.textContent = 'Publish Reel';
    const first = state.assets.find(a => a.id === state.pinned[0]);
    if (first && first.has_thumb) { img.src = `/api/assets/${first.id}/thumb`; img.classList.remove('hidden'); }
    else img.classList.add('hidden');
    const cls = { cut_paper: 'cap-cut', marker: 'cap-marker', typewriter: 'cap-type', neon: 'cap-neon' }[state.caption];
    cap.innerHTML = busy ? '' : `<span class="${cls} px-2.5 py-0.5 rounded font-extrabold text-sm">IT WAS A RAINY</span><span class="${cls} px-2.5 py-0.5 rounded font-extrabold text-sm mt-1">TUESDAY IN TOKYO</span>`;
    $('phone-title').textContent = $('title').value || 'Preview';
    $('phone-sub').textContent = `${voiceById(state.voice)?.name || ''} voice · ${state.pinned.length} clip${state.pinned.length === 1 ? '' : 's'} · live caption sample`;
  }
  const gen = $('btn-generate');
  gen.disabled = !!busy;
  gen.innerHTML = busy
    ? '<span class="material-symbols-outlined text-2xl animate-spin">refresh</span><span class="font-extrabold uppercase">Synthesizing…</span>'
    : '<span class="font-extrabold uppercase tracking-wide">Generate Your Video Now</span>';
}

// ------------------------------------------------------------------ generate + polling
async function generate() {
  const text = $('story').value.trim();
  if (text.length < 10) return toast('Write a story first (at least a sentence).', 'error');
  if (!state.pinned.length) return toast('Pin at least one background clip.', 'error');
  if (state.user.credits < 1) return toast('You are out of credits.', 'error');
  try {
    const res = await api('/api/videos', { json: {
      title: $('title').value.trim() || 'Untitled reel', text,
      voice: state.voice, speed: parseFloat($('speed').value), pitch: parseInt($('pitch').value, 10),
      music: state.music, caption_style: state.caption, clip_ids: state.pinned,
    } });
    setCredits(res.credits);
    state.current = res.video;
    state.videos.unshift(res.video);
    renderArchive(); renderPreview(); startPolling();
    $('screen').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (e) { toast(e.message, 'error'); }
}

function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(poll, 1500);
}

async function poll() {
  const active = state.videos.filter(v => v.status === 'queued' || v.status === 'processing');
  if (!active.length) { clearInterval(state.pollTimer); state.pollTimer = null; return; }
  for (const v of active) {
    try {
      const res = await api(`/api/videos/${v.id}`);
      const idx = state.videos.findIndex(x => x.id === v.id);
      if (idx >= 0) state.videos[idx] = res.video;
      setCredits(res.credits);
      if (state.current && state.current.id === v.id) {
        state.current = res.video;
        if (res.video.status === 'done') toast(res.video.error || 'Reel crafted successfully!', res.video.error ? 'info' : 'ok');
        if (res.video.status === 'failed') toast('Render failed: ' + (res.video.error || 'unknown error') + ' (credit refunded)', 'error');
      }
    } catch (e) { /* transient */ }
  }
  renderPreview(); renderArchive();
}

// ------------------------------------------------------------------ publish / archive
async function publish(video) {
  try {
    let v = video;
    if (!v.share_token) v = await api(`/api/videos/${v.id}/share`, { json: { enabled: true } });
    patchVideo(v);
    const url = `${location.origin}/share/${v.share_token}`;
    try { await navigator.clipboard.writeText(url); toast('Share link copied!', 'ok'); }
    catch (_) { prompt('Copy your share link:', url); }
  } catch (e) { toast(e.message, 'error'); }
}

async function unpublish(video) {
  try { patchVideo(await api(`/api/videos/${video.id}/share`, { json: { enabled: false } })); toast('Reel unpublished.'); }
  catch (e) { toast(e.message, 'error'); }
}

function patchVideo(v) {
  const i = state.videos.findIndex(x => x.id === v.id);
  if (i >= 0) state.videos[i] = v;
  if (state.current && state.current.id === v.id) state.current = v;
  renderArchive(); renderPreview();
}

function renderArchive() {
  $('archive-empty').classList.toggle('hidden', state.videos.length > 0);
  $('archive-grid').innerHTML = state.videos.map(v => {
    const done = v.status === 'done', busy = v.status === 'queued' || v.status === 'processing';
    const badge = done ? 'bg-secondary-fixed' : busy ? 'bg-tertiary-fixed' : 'bg-error-container';
    return `<div class="bg-surface-container-lowest border-2 border-on-surface rounded p-2 tactile-shadow-sm">
      <div class="relative aspect-[9/13] bg-on-surface/10 rounded overflow-hidden border border-on-surface mb-1.5 ${done ? 'cursor-pointer' : ''}" ${done ? `data-play="${v.id}"` : ''}>
        ${v.has_thumb ? `<img class="w-full h-full object-cover" loading="lazy" src="/api/videos/${v.id}/thumb" alt="">` : ''}
        <span class="absolute top-1 left-1 ${badge} px-1 py-0.5 rounded text-[9px] font-bold border border-on-surface uppercase">${busy ? Math.round(v.progress) + '%' : v.status}</span>
        ${done ? '<span class="material-symbols-outlined absolute inset-0 m-auto w-fit h-fit text-surface text-4xl drop-shadow">play_circle</span>' : ''}
      </div>
      <div class="text-[11px] font-bold truncate">${escapeHtml(v.title)}</div>
      <div class="text-[10px] text-on-surface-variant truncate">${done ? fmtTime(v.duration) + ' · ' : ''}${new Date(v.created_at).toLocaleDateString()}</div>
      ${v.status === 'failed' ? `<div class="text-[10px] text-error mt-0.5 line-clamp-2">${escapeHtml(v.error || '')}</div>` : ''}
      <div class="flex gap-1 mt-1.5">
        ${done ? `<a href="/api/videos/${v.id}/file?download=1" title="Download" class="material-symbols-outlined text-base border border-on-surface rounded px-1 hover:bg-surface-container-high">download</a>
        <button data-share="${v.id}" title="${v.share_token ? 'Copy share link' : 'Publish'}" class="material-symbols-outlined text-base border border-on-surface rounded px-1 ${v.share_token ? 'bg-secondary-container' : ''} hover:bg-surface-container-high">${v.share_token ? 'link' : 'share'}</button>
        ${v.share_token ? `<button data-unshare="${v.id}" title="Unpublish" class="material-symbols-outlined text-base border border-on-surface rounded px-1 hover:bg-surface-container-high">link_off</button>` : ''}` : ''}
        ${!busy ? `<button data-del-video="${v.id}" title="Delete" class="material-symbols-outlined text-base border border-on-surface rounded px-1 ml-auto text-error hover:bg-error-container">delete</button>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ------------------------------------------------------------------ audition
async function audition() {
  if (state.previewBusy) return;
  state.previewBusy = true;
  const icon = $('audition-icon'), label = $('audition-label');
  icon.textContent = 'progress_activity'; icon.classList.add('animate-spin'); label.textContent = 'Generating…';
  try {
    const res = await api('/api/voices/preview', { json: {
      voice: state.voice, speed: parseFloat($('speed').value), pitch: parseInt($('pitch').value, 10),
      text: $('story').value.replace(/\[[^\]]*\]/g, ' ').trim().slice(0, 180),
    } });
    const blob = await res.blob();
    const player = $('audio-player');
    player.src = URL.createObjectURL(blob);
    icon.classList.remove('animate-spin'); icon.textContent = 'volume_up'; label.textContent = 'Playing…';
    await player.play();
    await new Promise(r => { player.onended = r; player.onerror = r; });
  } catch (e) { toast(e.message, 'error'); }
  icon.classList.remove('animate-spin'); icon.textContent = 'play_circle'; label.textContent = 'Audition Voice';
  state.previewBusy = false;
}

// ------------------------------------------------------------------ events
function applyTone(key) {
  const t = TONES[key];
  state.voice = t.voice; state.caption = t.caption;
  $('speed').value = t.speed; $('pitch').value = t.pitch;
  setGenderTab('all'); renderCaptions(); updateEstimate();
  toast(`${t.label}: ${voiceById(t.voice).name} voice, ${t.speed}x pace, ${t.caption.replace('_', ' ')} captions`);
}

function bindUI() {
  $('story').addEventListener('input', updateEstimate);
  $('title').addEventListener('input', () => { if (!state.current || state.current.status !== 'done') renderPreview(); });
  $('speed').addEventListener('input', updateEstimate);
  $('pitch').addEventListener('input', updateEstimate);
  $('btn-spark').onclick = () => { $('story').value = SPARKS[Math.floor(Math.random() * SPARKS.length)]; updateEstimate(); };
  document.querySelectorAll('.tone').forEach(b => b.onclick = () => applyTone(b.dataset.tone));
  $('gender-filter').onclick = e => { const b = e.target.closest('[data-g]'); if (b) setGenderTab(b.dataset.g); };
  $('voice-grid').onclick = e => { const c = e.target.closest('[data-voice]'); if (c) { state.voice = c.dataset.voice; renderVoices(); } };
  $('music-pills').onclick = e => { const b = e.target.closest('[data-music]'); if (b) { state.music = b.dataset.music || null; renderMusic(); } };
  $('caption-styles').onclick = e => { const b = e.target.closest('[data-cap]'); if (b) { state.caption = b.dataset.cap; renderCaptions(); } };
  $('btn-preview-voice').onclick = audition;

  $('asset-grid').onclick = async e => {
    const del = e.target.closest('[data-del-asset]');
    if (del) {
      if (!confirm('Delete this uploaded clip?')) return;
      try {
        await api(`/api/assets/${del.dataset.delAsset}`, { method: 'DELETE' });
        state.assets = state.assets.filter(a => a.id !== del.dataset.delAsset);
        state.pinned = state.pinned.filter(id => id !== del.dataset.delAsset);
        renderAssets(); renderSequence(); renderPreview();
      } catch (err) { toast(err.message, 'error'); }
      return;
    }
    const pin = e.target.closest('[data-pin]') || e.target.closest('[data-asset]');
    if (pin) togglePin(pin.dataset.pin || pin.dataset.asset);
  };
  $('sequence').onclick = e => {
    const m = e.target.closest('[data-move]');
    if (m) { const [id, d] = m.dataset.move.split(':'); movePin(id, parseInt(d, 10)); }
  };

  const dz = $('dropzone'), fi = $('file-input');
  dz.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files.length) uploadFiles([...fi.files]); fi.value = ''; };
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('bg-secondary-fixed/40'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('bg-secondary-fixed/40'); }));
  dz.addEventListener('drop', e => { if (e.dataTransfer.files.length) uploadFiles([...e.dataTransfer.files]); });

  $('btn-generate').onclick = generate;
  $('btn-publish').onclick = () => { if (state.current?.status === 'done') publish(state.current); };

  $('archive-grid').onclick = async e => {
    const play = e.target.closest('[data-play]');
    if (play) { state.current = state.videos.find(v => v.id === play.dataset.play); renderPreview(); $('screen').scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
    const sh = e.target.closest('[data-share]');
    if (sh) return publish(state.videos.find(v => v.id === sh.dataset.share));
    const un = e.target.closest('[data-unshare]');
    if (un) return unpublish(state.videos.find(v => v.id === un.dataset.unshare));
    const del = e.target.closest('[data-del-video]');
    if (del) {
      if (!confirm('Delete this reel permanently?')) return;
      try {
        await api(`/api/videos/${del.dataset.delVideo}`, { method: 'DELETE' });
        state.videos = state.videos.filter(v => v.id !== del.dataset.delVideo);
        if (state.current?.id === del.dataset.delVideo) state.current = null;
        renderArchive(); renderPreview();
      } catch (err) { toast(err.message, 'error'); }
    }
  };

  $('btn-logout').onclick = async () => { await api('/api/auth/logout', { method: 'POST' }); location.href = '/login'; };
}

boot();
