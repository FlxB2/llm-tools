// Edit the text of any web page in place: a small bar in the bottom-right corner turns edit mode on,
// then click a text and type. Changes are kept in this browser per page (localStorage) and come
// back the next time the editor runs there; "Changes" lists them as old → new, ready to copy.
//
// "Options" switches between design variants, when the page marks some up:
//   <div data-variants="Names">
//     <div data-variant="Name + role">…</div>
//     <div data-variant="Pills">…</div>
//   </div>
// Only one variant per group shows at a time; the pick is remembered per page like the text edits.
//
// Runs on its own when loaded with <script src="text-editor.js">. Everything lives in the one
// function so index.html can turn it into a bookmarklet for pages you don't control.
function textEditor() {
  if (window.__textEditor) return window.__textEditor.show();

  const storageKey = `text-editor:${location.host}${location.pathname}`;
  const load = () => {
    try {
      return JSON.parse(localStorage.getItem(storageKey)) || {};
    } catch {
      return {};
    }
  };
  const save = () => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(changes));
    } catch {}
  };

  // path → { before, after, beforeText, afterText }; before/after are innerHTML so links and
  // emphasis inside an edited text survive.
  let changes = load();
  let on = false;
  let current = null; // the element being edited
  let sessionStart = ''; // its HTML when this edit began, for Escape

  // The widget sits in a shadow root so the page's CSS can't reach it and ours can't leak out.
  const host = document.createElement('div');
  host.setAttribute('data-text-editor', '');
  const ui = host.attachShadow({ mode: 'open' });
  ui.innerHTML = `
    <style>
      :host { all: initial; position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;
        font: 500 13px/1.3 system-ui, -apple-system, sans-serif; color: #fff; cursor: auto; }
      .bar { display: flex; align-items: center; gap: 4px; padding: 4px; border-radius: 999px;
        background: #14121f; box-shadow: 0 8px 24px rgba(0,0,0,.25), inset 0 0 0 1px rgba(255,255,255,.08); }
      button { all: unset; cursor: pointer; padding: 7px 12px; border-radius: 999px; white-space: nowrap; }
      button:hover { background: rgba(255,255,255,.1); }
      button:focus-visible { outline: 2px solid #9b87ff; outline-offset: 1px; }
      .toggle[aria-pressed="true"] { background: #7c5cff; }
      .count { min-width: 1.4em; padding: 1px 6px; border-radius: 999px; background: rgba(255,255,255,.14);
        font-size: 11px; text-align: center; }
      .count:empty { display: none; }
      .close { padding: 7px 10px; opacity: .6; }
      .panel { position: absolute; right: 0; bottom: calc(100% + 8px); width: min(380px, calc(100vw - 32px));
        padding: 12px; border-radius: 14px; background: #14121f; box-shadow: 0 8px 24px rgba(0,0,0,.25); }
      [hidden] { display: none !important; }
      textarea { box-sizing: border-box; width: 100%; height: 180px; padding: 8px; resize: vertical;
        border: 0; border-radius: 8px; background: rgba(255,255,255,.07); color: inherit;
        font: 12px/1.45 ui-monospace, monospace; }
      .row { display: flex; justify-content: flex-end; gap: 4px; margin-top: 8px; }
      .hint { margin: 0 0 8px; opacity: .6; font-size: 12px; }
      .groups { display: flex; flex-direction: column; gap: 6px; }
      .group { display: flex; align-items: center; justify-content: space-between; gap: 8px;
        padding: 4px 4px 4px 8px; border-radius: 10px; background: rgba(255,255,255,.07); }
      .group .name { padding: 6px 4px; font-weight: 600; }
      .stepper { display: flex; align-items: center; gap: 2px; min-width: 0; }
      .stepper span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; opacity: .85; }
      .stepper button { padding: 6px 10px; }
      .hover { position: fixed; pointer-events: none; border: 2px solid #7c5cff; border-radius: 4px;
        background: rgba(124,92,255,.06); display: none; }
    </style>
    <div class="hover"></div>
    <div class="panel options" hidden>
      <p class="hint">Variants on this page. Your pick is remembered here.</p>
      <div class="groups"></div>
    </div>
    <div class="panel changes" hidden>
      <p class="hint">Saved in this browser for this page.</p>
      <textarea readonly></textarea>
      <div class="row"><button class="reset">Undo all</button><button class="copy">Copy</button></div>
    </div>
    <div class="bar">
      <button class="toggle" aria-pressed="false">✎ Edit text</button>
      <button class="opts" aria-expanded="false" hidden>Options</button>
      <button class="list" aria-expanded="false">Changes <span class="count"></span></button>
      <button class="close" aria-label="Close">✕</button>
    </div>`;
  const $ = (s) => ui.querySelector(s);
  const hover = $('.hover');
  const panel = $('.changes');
  const optionsPanel = $('.options');

  // Page-side marks for edited and active texts, keyed on our own attributes only.
  const pageStyle = document.createElement('style');
  pageStyle.textContent = `
    [data-te-on] [data-te-edited] { outline: 1px dashed rgba(124,92,255,.8); outline-offset: 3px; }
    [data-te-editing] { outline: 2px solid #7c5cff !important; outline-offset: 3px; cursor: text; }
    [data-te-on] body { cursor: text; }`;

  // A stable address for an element: ids where there are some, else tag + position from <body>.
  const pathOf = (el) => {
    const parts = [];
    while (el && el !== document.body) {
      if (el.id) {
        parts.unshift(`#${CSS.escape(el.id)}`);
        return parts.join(' > ');
      }
      const same = [...el.parentElement.children].filter((c) => c.tagName === el.tagName);
      parts.unshift(`${el.tagName.toLowerCase()}:nth-of-type(${same.indexOf(el) + 1})`);
      el = el.parentElement;
    }
    return ['body', ...parts].join(' > ');
  };
  const find = (path) => {
    try {
      return document.querySelector(path);
    } catch {
      return null;
    }
  };

  // The element a click means: the nearest one that holds text itself, not just in its children.
  const textTarget = (el) => {
    for (; el && el !== document.body; el = el.parentElement) {
      if (el === host || /^(SCRIPT|STYLE|SVG|svg)$/.test(el.tagName)) return null;
      if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) return el;
    }
    return null;
  };

  const startEdit = (el, x, y) => {
    if (el === current) return;
    finish();
    current = el;
    sessionStart = el.innerHTML;
    el.setAttribute('data-te-editing', '');
    el.contentEditable = 'true';
    el.focus();
    // Put the caret where the click landed, not at the start.
    const range = document.caretRangeFromPoint?.(x, y);
    if (range) {
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
    hover.style.display = 'none';
  };

  const finish = (revert = false) => {
    const el = current;
    if (!el) return;
    current = null;
    if (revert) el.innerHTML = sessionStart;
    el.removeAttribute('contenteditable');
    el.removeAttribute('data-te-editing');
    const path = pathOf(el);
    const before = changes[path]?.before ?? sessionStart;
    if (el.innerHTML === before) {
      delete changes[path];
      el.removeAttribute('data-te-edited');
    } else {
      const text = (html) => {
        const d = document.createElement('div');
        d.innerHTML = html;
        return d.textContent.replace(/\s+/g, ' ').trim();
      };
      changes[path] = { before, after: el.innerHTML, beforeText: text(before), afterText: text(el.innerHTML) };
      el.setAttribute('data-te-edited', '');
    }
    save();
    render();
  };

  const render = () => {
    const list = Object.values(changes);
    $('.count').textContent = list.length || '';
    $('textarea').value = list.length
      ? `${location.href}\n\n` + list.map((c, i) => `${i + 1}. "${c.beforeText}"\n   → "${c.afterText}"`).join('\n\n')
      : 'No changes yet.';
  };

  const onMove = (e) => {
    const el = !current || !current.contains(e.target) ? textTarget(e.target) : null;
    if (!el) return (hover.style.display = 'none');
    const r = el.getBoundingClientRect();
    Object.assign(hover.style, {
      display: 'block',
      left: `${r.left - 4}px`,
      top: `${r.top - 4}px`,
      width: `${r.width + 8}px`,
      height: `${r.height + 8}px`,
    });
  };
  // Capture phase, so links, buttons and the page's own handlers don't fire while editing.
  const onClick = (e) => {
    if (e.composedPath().includes(host)) return;
    if (current?.contains(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    const el = textTarget(e.target);
    el ? startEdit(el, e.clientX, e.clientY) : finish();
  };
  const onKey = (e) => {
    if (!current) return;
    if (e.key === 'Escape') finish(true);
    else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      finish();
    }
  };
  const hideHover = () => (hover.style.display = 'none');

  const setOn = (value) => {
    on = value;
    $('.toggle').setAttribute('aria-pressed', String(on));
    document.documentElement.toggleAttribute('data-te-on', on);
    const method = on ? 'addEventListener' : 'removeEventListener';
    document[method]('mousemove', onMove, true);
    document[method]('click', onClick, true);
    document[method]('keydown', onKey, true);
    window[method]('scroll', hideHover, true);
    if (!on) {
      finish();
      hideHover();
    }
  };

  $('.toggle').onclick = () => setOn(!on);
  // One panel open at a time.
  const openPanel = (which) => {
    for (const [p, button] of [
      [panel, $('.list')],
      [optionsPanel, $('.opts')],
    ]) {
      p.hidden = p !== which || !p.hidden;
      button.setAttribute('aria-expanded', String(!p.hidden));
    }
  };
  $('.list').onclick = () => openPanel(panel);
  $('.opts').onclick = () => openPanel(optionsPanel);

  // Variant groups: show one child per [data-variants] group, step through them from the panel.
  const pickKey = `${storageKey}:variants`;
  let picks = {};
  try {
    picks = JSON.parse(localStorage.getItem(pickKey)) || {};
  } catch {}
  const groups = [...document.querySelectorAll('[data-variants]')];
  const variantsOf = (g) => [...g.children].filter((c) => c.hasAttribute('data-variant'));
  const groupName = (g, i) => g.dataset.variants || `Group ${i + 1}`;
  const pick = (g, i, index) => {
    const variants = variantsOf(g);
    if (!variants.length) return;
    index = (index + variants.length) % variants.length;
    // Inline display rather than [hidden], which a page's own display classes can override.
    variants.forEach((v, j) => (v.style.display = j === index ? '' : 'none'));
    picks[groupName(g, i)] = index;
    try {
      localStorage.setItem(pickKey, JSON.stringify(picks));
    } catch {}
    renderGroups();
  };
  const renderGroups = () => {
    const list = $('.groups');
    list.replaceChildren(
      ...groups.map((g, i) => {
        const variants = variantsOf(g);
        const index = picks[groupName(g, i)] ?? 0;
        const row = document.createElement('div');
        row.className = 'group';
        const name = document.createElement('button');
        name.className = 'name';
        name.textContent = groupName(g, i);
        name.title = 'Scroll to it';
        name.onclick = () => g.scrollIntoView({ behavior: 'smooth', block: 'center' });
        const stepper = document.createElement('div');
        stepper.className = 'stepper';
        const prev = document.createElement('button');
        prev.textContent = '‹';
        prev.setAttribute('aria-label', 'Previous variant');
        prev.onclick = () => pick(g, i, index - 1);
        const label = document.createElement('span');
        label.textContent = `${index + 1}/${variants.length} · ${variants[index]?.dataset.variant || ''}`;
        const next = document.createElement('button');
        next.textContent = '›';
        next.setAttribute('aria-label', 'Next variant');
        next.onclick = () => pick(g, i, index + 1);
        stepper.append(prev, label, next);
        row.append(name, stepper);
        return row;
      }),
    );
  };
  groups.forEach((g, i) => pick(g, i, picks[groupName(g, i)] ?? 0));
  $('.opts').hidden = !groups.length;
  $('.copy').onclick = async () => {
    try {
      await navigator.clipboard.writeText($('textarea').value);
      $('.copy').textContent = 'Copied';
    } catch {
      $('textarea').select();
      $('.copy').textContent = 'Press ⌘C';
    }
    setTimeout(() => ($('.copy').textContent = 'Copy'), 1500);
  };
  $('.reset').onclick = () => {
    finish();
    for (const [path, c] of Object.entries(changes)) {
      const el = find(path);
      if (el && el.innerHTML === c.after) {
        el.innerHTML = c.before;
        el.removeAttribute('data-te-edited');
      }
    }
    changes = {};
    save();
    render();
  };
  $('.close').onclick = () => {
    setOn(false);
    host.remove();
    pageStyle.remove();
    delete window.__textEditor;
  };

  // Bring back earlier edits, but only where the text is still what it was when edited, so a
  // changed page doesn't get an old edit pasted over something else.
  for (const [path, c] of Object.entries(changes)) {
    const el = find(path);
    if (el && el.innerHTML === c.before) el.innerHTML = c.after;
    if (el && el.innerHTML === c.after) el.setAttribute('data-te-edited', '');
  }

  document.head.append(pageStyle);
  document.body.append(host);
  render();
  window.__textEditor = { show: () => document.body.append(host) };
}

if (document.currentScript) {
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', textEditor) : textEditor();
}
