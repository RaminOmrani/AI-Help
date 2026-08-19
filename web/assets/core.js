/* ============================================================
   ابزارهای مشترک: مارک‌داون امن، درخواست‌ها، استریم SSE، اعلان
   ============================================================ */

export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const escapeHtml = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

/* ---------- مارک‌داون سبک (ورودی همیشه escape می‌شود) ---------- */
export function md(src) {
  if (!src) return '';
  const blocks = [];
  let text = escapeHtml(src);

  // بلوک کد
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    blocks.push(`<pre><code data-lang="${lang}">${code.replace(/\n$/, '')}</code></pre>`);
    return ` @@B${blocks.length - 1}@@ `;
  });
  // کد درون‌خطی
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    blocks.push(`<code>${code}</code>`);
    return ` @@B${blocks.length - 1}@@ `;
  });

  const lines = text.split('\n');
  const out = [];
  let listType = null;

  const closeList = () => { if (listType) { out.push(`</${listType}>`); listType = null; } };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^&gt;\s?/.test(line)) {
      closeList();
      out.push(`<blockquote>${inline(line.replace(/^&gt;\s?/, ''))}</blockquote>`);
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(line)) { closeList(); out.push('<hr>'); continue; }

    const ordered = line.match(/^(\d+)[.)]\s+(.*)$/);
    const bullet  = line.match(/^[-*•]\s+(.*)$/);
    if (ordered) {
      if (listType !== 'ol') { closeList(); out.push('<ol>'); listType = 'ol'; }
      out.push(`<li>${inline(ordered[2])}</li>`);
      continue;
    }
    if (bullet) {
      if (listType !== 'ul') { closeList(); out.push('<ul>'); listType = 'ul'; }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();

  return out.join('\n').replace(/@@B(\d+)@@/g, (_, i) => blocks[+i]);
}

function inline(s) {
  return s
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\s)\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

/* ---------- اعلان ---------- */
export function toast(message, kind = '') {
  let host = document.getElementById('toasts');
  if (!host) {
    host = document.createElement('div');
    host.id = 'toasts';
    document.body.appendChild(host);
  }
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .3s, transform .3s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(() => el.remove(), 320);
  }, 4200);
}

/* ---------- ذخیره‌سازی محلی ---------- */
let tokenScope = 'default';
/** نقش این صفحه را مشخص می‌کند تا توکن مدیر و کارشناس روی هم نیفتند. */
export function setAuthScope(role) { tokenScope = role || 'default'; }

export const store = {
  get tokenKey() { return `ai_token_${tokenScope}`; },
  get token()  { return localStorage.getItem(this.tokenKey) || ''; },
  set token(v) { v ? localStorage.setItem(this.tokenKey, v) : localStorage.removeItem(this.tokenKey); },
  /** شناسه‌ی پایدار مرورگر — با «گفتگوی جدید» عوض نمی‌شود، پس سابقه حفظ می‌ماند. */
  get client() {
    let id = localStorage.getItem('ai_client');
    if (!id) {
      id = crypto.randomUUID?.() || String(Date.now() + Math.random());
      localStorage.setItem('ai_client', id);
    }
    return id;
  },
  get session() {
    let id = localStorage.getItem('ai_session');
    if (!id) {
      id = crypto.randomUUID?.() || String(Date.now() + Math.random());
      localStorage.setItem('ai_session', id);
    }
    return id;
  },
  newSession() {
    const id = crypto.randomUUID?.() || String(Date.now() + Math.random());
    localStorage.setItem('ai_session', id);
    return id;
  },
  useSession(id) { localStorage.setItem('ai_session', id); },
  get length() { return localStorage.getItem('ai_length') || 'normal'; },
  set length(v) { localStorage.setItem('ai_length', v); },
};

/* ---------- درخواست‌ها ---------- */
export async function api(path, { method = 'GET', body, auth = false } = {}) {
  const headers = {};
  if (auth) headers.Authorization = `Bearer ${store.token}`;
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, {
    method,
    headers,
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });

  if (auth && (res.status === 401 || res.status === 403)) {
    store.token = '';
    location.reload();
  }
  if (!res.ok) {
    let detail = `خطای ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* بی‌خیال */ }
    throw new Error(detail);
  }
  return res.json();
}

/* ---------- استریم SSE ---------- */
export async function streamChat(path, payload, handlers, { auth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) headers.Authorization = `Bearer ${store.token}`;

  let res;
  try {
    res = await fetch(path, { method: 'POST', headers, body: JSON.stringify(payload) });
  } catch {
    handlers.error?.({ message: 'ارتباط با سرور برقرار نشد. مطمئن شوید سرور روشن است.' });
    return;
  }
  if (!res.ok || !res.body) {
    let detail = `خطای ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* بی‌خیال */ }
    handlers.error?.({ message: detail });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const line = part.split('\n').find((l) => l.startsWith('data:'));
      if (!line) continue;
      let event;
      try { event = JSON.parse(line.slice(5).trim()); } catch { continue; }
      handlers[event.type]?.(event);
    }
  }
}

/* ---------- تم ---------- */
export function initTheme(buttonSelector) {
  const saved = localStorage.getItem('ai_theme');
  const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
  const apply = (theme) => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('ai_theme', theme);
    $$(buttonSelector).forEach((b) => { b.textContent = theme === 'dark' ? '☀️' : '🌙'; });
  };
  apply(saved || (prefersDark ? 'dark' : 'light'));
  $$(buttonSelector).forEach((btn) =>
    btn.addEventListener('click', () =>
      apply(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark')
    )
  );
}

export function copyText(text) {
  navigator.clipboard?.writeText(text).then(
    () => toast('کپی شد ✓', 'ok'),
    () => toast('کپی نشد', 'err')
  );
}

export const faDigits = (n) => String(n ?? '').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]);

export const money = (n) => faDigits(Math.round(Number(n) || 0).toLocaleString('en-US'));


/* ---------- درِ کشویی سابقه ---------- */
/**
 * یک درِ کشویی برای گفتگوهای قبلی می‌سازد.
 * @param {object} o
 * @param {() => Promise<Array>} o.load   گرفتن فهرست گفتگوها
 * @param {(sessionId: string) => void} o.open   باز کردن یک گفتگو
 * @param {(sessionId: string) => Promise<void>} o.remove  حذف یک گفتگو
 * @param {() => void} o.fresh  شروع گفتگوی جدید
 */
export function openHistoryDrawer({ load, open, remove, fresh }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';

  const drawer = document.createElement('aside');
  drawer.className = 'drawer';
  drawer.innerHTML = `
    <header>
      <b>گفتگوهای قبلی</b>
      <button class="btn btn-sm btn-primary" data-x="new">✨ جدید</button>
      <button class="btn btn-sm btn-ghost" data-x="close">✕</button>
    </header>
    <div class="list"><p class="empty-note">در حال بارگذاری…</p></div>`;

  document.body.append(backdrop, drawer);
  const close = () => { backdrop.remove(); drawer.remove(); };
  backdrop.addEventListener('click', close);
  drawer.querySelector('[data-x="close"]').onclick = close;
  drawer.querySelector('[data-x="new"]').onclick = () => { close(); fresh(); };

  const list = drawer.querySelector('.list');
  const current = store.session;

  const render = (items) => {
    if (!items.length) {
      list.innerHTML = '<p class="empty-note">هنوز گفتگویی ثبت نشده.<br>سوالت را بپرس تا اینجا ذخیره شود.</p>';
      return;
    }
    list.innerHTML = items
      .map((c) => `
        <div class="conv ${c.session_id === current ? 'on' : ''}" data-s="${escapeHtml(c.session_id)}">
          <div class="txt">
            <b>${escapeHtml(c.title || 'بدون عنوان')}</b>
            <span>${faDigits(c.turns)} پیام · <time>${escapeHtml((c.created_at || '').slice(0, 16))}</time></span>
          </div>
          <button class="del" title="حذف">🗑</button>
        </div>`)
      .join('');

    list.querySelectorAll('.conv').forEach((el) => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.del')) return;
        close();
        open(el.dataset.s);
      });
      el.querySelector('.del').addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          await remove(el.dataset.s);
          el.remove();
          if (!list.querySelector('.conv')) render([]);
          if (el.dataset.s === current) fresh();
        } catch (err) { toast(err.message, 'err'); }
      });
    });
  };

  load().then(render).catch((err) => {
    list.innerHTML = `<p class="empty-note">${escapeHtml(err.message)}</p>`;
  });
}


/* ---------- انتخاب طول پاسخ ---------- */
const LENGTHS = [
  ['short', 'کوتاه', 'فقط جوابِ مستقیم، بدون مقدمه و تیتر — طول را از روی خود سوال تشخیص می‌دهد'],
  ['normal', 'متوسط', 'همه‌ی گام‌های لازم، بدون حاشیه‌روی'],
  ['detailed', 'کامل', 'همه‌ی جزئیات، روش‌های جایگزین و نکته‌های مرتبط'],
];

/** یک انتخابگر طول پاسخ داخل عنصر داده‌شده می‌سازد. مقدار در مرورگر ذخیره می‌شود. */
export function mountLengthPicker(host) {
  if (!host) return;
  host.className = 'seg';
  host.innerHTML = LENGTHS
    .map(([id, label, hint]) =>
      `<button data-len="${id}" title="${escapeHtml(hint)}">${label}</button>`)
    .join('');

  const paint = () => {
    host.querySelectorAll('button').forEach((b) =>
      b.classList.toggle('on', b.dataset.len === store.length));
  };
  host.querySelectorAll('button').forEach((b) =>
    b.addEventListener('click', () => { store.length = b.dataset.len; paint(); }));
  paint();
}
