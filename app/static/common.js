// Shared helpers for all pages
async function api(path, opts = {}) {
  const init = { credentials: 'same-origin', ...opts };
  if (opts.json !== undefined) {
    init.method = init.method || 'POST';
    init.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    init.body = JSON.stringify(opts.json);
    delete init.json;
  }
  const res = await fetch(path, init);
  if (res.status === 401 && !location.pathname.startsWith('/login') && !location.pathname.startsWith('/share')) {
    location.href = '/login';
    throw new Error('Please log in.');
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      msg = typeof d === 'string' ? d
        : Array.isArray(d) ? d.map(e => (e.loc || []).slice(-1)[0] + ': ' + e.msg).join('; ') : msg;
    } catch (_) {}
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  const type = res.headers.get('content-type') || '';
  if (type.includes('application/json')) return res.json();
  return res;
}

function toast(message, kind = 'info') {
  const el = document.createElement('div');
  const colors = kind === 'error' ? 'bg-error text-on-error'
    : kind === 'ok' ? 'bg-secondary-container text-on-secondary-container'
    : 'bg-inverse-surface text-inverse-on-surface';
  el.className = `toast ${colors} px-4 py-2 rounded border-2 border-on-surface tactile-shadow-sm text-xs font-bold max-w-[90vw]`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtTime(sec) {
  sec = Math.max(0, Math.round(sec));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}
