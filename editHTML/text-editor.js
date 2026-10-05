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
// "Spacing" lets you click any element and change its margin, padding and gap in px, with the
// margin (orange) and padding (green) drawn over the page like the browser's inspector. Those
// changes are inline styles, kept and listed under "Changes" like the text edits.
//
// "⚙" moves the bar to another corner or edge (top/bottom × left/center/right), for pages whose
// own controls sit where the bar does. That choice is kept per site, not per page.
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
      .gear { padding: 4px 9px; font-size: 18px; line-height: 1; }
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
      .box-m, .box-p { position: fixed; pointer-events: none; box-sizing: border-box; border-style: solid; display: none; }
      .box-m { border-color: rgba(246,166,82,.45); }
      .box-p { border-color: rgba(120,190,110,.5); outline: 1.5px solid #7c5cff; }
      .space[aria-pressed="true"] { background: #7c5cff; }
      .el { margin: 0 0 10px; font: 12px/1.4 ui-monospace, monospace; opacity: .85; word-break: break-all;
        max-height: 3.6em; overflow: hidden; }
      .grid { display: grid; grid-template-columns: auto 1fr 1fr; gap: 6px 8px; align-items: center; }
      .grid .head { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; opacity: .6; }
      .grid .head.m { color: #f6a652; opacity: 1; }
      .grid .head.p { color: #78be6e; opacity: 1; }
      .grid label { opacity: .7; font-size: 12px; }
      input { all: unset; box-sizing: border-box; width: 100%; padding: 6px 8px; border-radius: 8px;
        background: rgba(255,255,255,.07); font: 12px ui-monospace, monospace; color: inherit; }
      input:focus { outline: 2px solid #9b87ff; }
      input.changed { background: rgba(124,92,255,.35); }
      input::-webkit-inner-spin-button, input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
      input[type=number] { -moz-appearance: textfield; text-align: center; cursor: ew-resize; touch-action: none; }
      input[type=number]:focus { cursor: text; }
      .field { display: flex; align-items: center; gap: 2px; min-width: 0; }
      .field input { flex: 1; min-width: 0; }
      .panel.spacing { width: min(440px, calc(100vw - 32px)); }
      .field .step { padding: 5px 8px; border-radius: 8px; font-size: 14px; line-height: 1; }
      .row.left { justify-content: space-between; }
      /* Bar position. Centring uses auto margins, not a transform: a transform on the host would
         make it the containing block of the fixed hover and spacing overlays. */
      :host([data-pos^="top"]) { top: 16px; bottom: auto; }
      :host([data-pos$="left"]) { left: 16px; right: auto; }
      :host([data-pos$="center"]) { left: 0; right: 0; width: fit-content; margin: 0 auto; }
      :host([data-pos^="top"]) .panel { bottom: auto; top: calc(100% + 8px); }
      :host([data-pos$="left"]) .panel { right: auto; left: 0; }
      :host([data-pos$="center"]) .panel { right: auto; left: 50%; transform: translateX(-50%); }
      .positions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
      .positions button { padding: 8px 6px; text-align: center; border-radius: 10px; background: rgba(255,255,255,.07); }
      .positions button[aria-pressed="true"] { background: #7c5cff; }
    </style>
    <div class="hover"></div>
    <div class="box-m"></div>
    <div class="box-p"></div>
    <div class="panel spacing" hidden>
      <p class="hint">Click an element. Values in px. Drag a field left or right, or use − + and ↑ ↓; Shift for steps of 8.</p>
      <p class="el"></p>
      <div class="grid"></div>
      <div class="row left"><button class="parent">↑ Parent</button><button class="unselect">Done</button></div>
    </div>
    <div class="panel options" hidden>
      <p class="hint">Variants on this page. Your pick is remembered here.</p>
      <div class="groups"></div>
    </div>
    <div class="panel changes" hidden>
      <p class="hint">Saved in this browser for this page.</p>
      <textarea readonly></textarea>
      <div class="row"><button class="reset">Undo all</button><button class="copy">Copy</button></div>
    </div>
    <div class="panel settings" hidden>
      <p class="hint">Where the bar sits. Remembered in this browser for this site.</p>
      <div class="positions"></div>
    </div>
    <div class="bar">
      <button class="toggle" aria-pressed="false">✎ Edit text</button>
      <button class="space" aria-pressed="false">↔ Spacing</button>
      <button class="opts" aria-expanded="false" hidden>Options</button>
      <button class="list" aria-expanded="false">Changes <span class="count"></span></button>
      <button class="gear" aria-expanded="false" aria-label="Settings" title="Settings">⚙</button>
      <button class="close" aria-label="Close">✕</button>
    </div>`;
  const $ = (s) => ui.querySelector(s);
  const hover = $('.hover');
  const panel = $('.changes');
  const optionsPanel = $('.options');
  const spacingPanel = $('.spacing');
  const settingsPanel = $('.settings');
  const boxM = $('.box-m');
  const boxP = $('.box-p');

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
    const spaced = Object.values(spacing);
    const count = list.length + spaced.reduce((n, s) => n + Object.keys(s.props).length, 0);
    $('.count').textContent = count || '';
    const text = list.map((c, i) => `${i + 1}. "${c.beforeText}"\n   → "${c.afterText}"`).join('\n\n');
    const space = spaced
      .map((s, i) =>
        [`${i + 1}. ${s.label}`, ...Object.entries(s.props).map(([p, r]) => `   ${p}: ${r.before} → ${r.after}`)].join('\n'),
      )
      .join('\n\n');
    $('textarea').value = count
      ? [location.href, list.length && `Text:\n\n${text}`, spaced.length && `Spacing:\n\n${space}`].filter(Boolean).join('\n\n')
      : 'No changes yet.';
  };

  const onMove = (e) => {
    const el = !current || !current.contains(e.target) ? textTarget(e.target) : null;
    drawHover(el);
  };
  const drawHover = (el) => {
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

  // Spacing: path → { label, props: { 'padding-top': { inline, before, after } } }, where inline is
  // the element's own inline value before we touched it, so undo puts back exactly that.
  const spaceKey = `${storageKey}:spacing`;
  let spacing = {};
  try {
    spacing = JSON.parse(localStorage.getItem(spaceKey)) || {};
  } catch {}
  const saveSpacing = () => {
    try {
      localStorage.setItem(spaceKey, JSON.stringify(spacing));
    } catch {}
  };
  const sides = ['top', 'right', 'bottom', 'left'];
  let spaceOn = false;
  let selected = null;

  // How the element reads in the change list: its tag, id and (trimmed) classes, enough to find it
  // in the source.
  const describe = (el) => {
    const cls = (el.getAttribute('class') || '').trim().replace(/\s+/g, ' ');
    const id = el.id ? ` id="${el.id}"` : '';
    return `<${el.tagName.toLowerCase()}${id}${cls ? ` class="${cls.length > 90 ? `${cls.slice(0, 90)}…` : cls}"` : ''}>`;
  };
  const px = (el, prop) => Math.round(parseFloat(getComputedStyle(el).getPropertyValue(prop)) || 0);

  // Margin and padding as bands, the way the browser's inspector shows them: each box's border
  // widths are the element's margins and paddings.
  const drawBox = (el) => {
    if (!el) {
      boxM.style.display = boxP.style.display = 'none';
      return;
    }
    const r = el.getBoundingClientRect();
    const v = (p) => Math.max(px(el, p), 0);
    const m = sides.map((s) => v(`margin-${s}`));
    const b = sides.map((s) => v(`border-${s}-width`));
    const p = sides.map((s) => v(`padding-${s}`));
    Object.assign(boxM.style, {
      display: 'block',
      left: `${r.left - m[3]}px`,
      top: `${r.top - m[0]}px`,
      width: `${r.width + m[1] + m[3]}px`,
      height: `${r.height + m[0] + m[2]}px`,
      borderWidth: m.map((x) => `${x}px`).join(' '),
    });
    Object.assign(boxP.style, {
      display: 'block',
      left: `${r.left + b[3]}px`,
      top: `${r.top + b[0]}px`,
      width: `${r.width - b[1] - b[3]}px`,
      height: `${r.height - b[0] - b[2]}px`,
      borderWidth: p.map((x) => `${x}px`).join(' '),
    });
  };

  const setProp = (el, prop, value) => {
    const path = pathOf(el);
    const entry = (spacing[path] ??= { label: describe(el), props: {} });
    const rec = (entry.props[prop] ??= { inline: el.style.getPropertyValue(prop), before: `${px(el, prop)}px` });
    const after = `${value}px`;
    if (after === rec.before) {
      rec.inline ? el.style.setProperty(prop, rec.inline) : el.style.removeProperty(prop);
      delete entry.props[prop];
      if (!Object.keys(entry.props).length) delete spacing[path];
    } else {
      el.style.setProperty(prop, after);
      rec.after = after;
    }
    saveSpacing();
    render();
    drawBox(el);
  };

  const renderSpacing = () => {
    const el = selected;
    $('.el').textContent = el ? describe(el) : 'Nothing selected yet.';
    $('.parent').hidden = !el || el.parentElement === document.body || !el.parentElement;
    const grid = $('.grid');
    grid.replaceChildren();
    if (!el) return;
    const touched = spacing[pathOf(el)]?.props ?? {};
    const cell = (tag, text, cls) => {
      const n = document.createElement(tag);
      if (text) n.textContent = text;
      if (cls) n.className = cls;
      grid.append(n);
    };
    const input = (prop, label) => {
      const i = document.createElement('input');
      i.type = 'number';
      i.value = px(el, prop);
      i.title = prop;
      i.setAttribute('aria-label', `${label} ${prop}`);
      if (touched[prop]) i.classList.add('changed');
      i.oninput = () => {
        if (i.value === '' || isNaN(+i.value)) return;
        setProp(el, prop, Math.round(+i.value));
        i.classList.toggle('changed', !!spacing[pathOf(el)]?.props[prop]);
      };
      const step = (by) => {
        i.value = (+i.value || 0) + by;
        i.oninput();
      };
      i.onkeydown = (e) => {
        if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
        e.preventDefault();
        step((e.key === 'ArrowUp' ? 1 : -1) * (e.shiftKey ? 8 : 1));
      };
      // Scrub like Figma: press on the field and drag left or right, 1 px per 3 px of movement (8 with
      // Shift). A press without a drag still focuses the field for typing.
      i.onpointerdown = (e) => {
        if (document.activeElement === i || ui.activeElement === i) return;
        e.preventDefault();
        const x0 = e.clientX;
        const v0 = +i.value || 0;
        let dragged = false;
        i.setPointerCapture(e.pointerId);
        i.onpointermove = (m) => {
          const dx = m.clientX - x0;
          if (!dragged && Math.abs(dx) < 3) return;
          dragged = true;
          const value = v0 + Math.round(dx / 3) * (m.shiftKey ? 8 : 1);
          if (+i.value !== value) {
            i.value = value;
            i.oninput();
          }
        };
        i.onpointerup = () => {
          i.onpointermove = i.onpointerup = null;
          if (!dragged) {
            i.focus();
            i.select();
          }
        };
      };
      // − and + beside the field; Shift-click steps by 8.
      const button = (text, sign) => {
        const b = document.createElement('button');
        b.className = 'step';
        b.textContent = text;
        b.setAttribute('aria-label', `${sign > 0 ? 'Increase' : 'Decrease'} ${prop}`);
        b.onclick = (e) => step(sign * (e.shiftKey ? 8 : 1));
        return b;
      };
      const field = document.createElement('div');
      field.className = 'field';
      field.append(button('−', -1), i, button('+', 1));
      grid.append(field);
    };
    cell('span');
    cell('span', 'Margin', 'head m');
    cell('span', 'Padding', 'head p');
    for (const s of sides) {
      cell('label', s[0].toUpperCase() + s.slice(1));
      input(`margin-${s}`, 'Margin');
      input(`padding-${s}`, 'Padding');
    }
    cell('label', 'Gap ↕ ↔');
    input('row-gap', 'Gap');
    input('column-gap', 'Gap');
  };

  const select = (el) => {
    selected = el;
    drawBox(el);
    renderSpacing();
    showPanel(spacingPanel);
  };
  const onSpaceMove = (e) => {
    const el = e.composedPath().includes(host) ? null : e.target;
    drawHover(el && el !== selected && el !== document.documentElement ? el : null);
  };
  const onSpaceClick = (e) => {
    if (e.composedPath().includes(host)) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.target !== document.documentElement) select(e.target);
  };
  const onSpaceKey = (e) => {
    if (e.key === 'Escape' && !e.composedPath().includes(host)) select(null);
  };
  const onSpaceScroll = () => {
    hideHover();
    drawBox(selected);
  };

  const setSpace = (value) => {
    if (value) setOn(false);
    spaceOn = value;
    $('.space').setAttribute('aria-pressed', String(spaceOn));
    const method = spaceOn ? 'addEventListener' : 'removeEventListener';
    document[method]('mousemove', onSpaceMove, true);
    document[method]('click', onSpaceClick, true);
    document[method]('keydown', onSpaceKey, true);
    window[method]('scroll', onSpaceScroll, true);
    window[method]('resize', onSpaceScroll);
    if (spaceOn) select(selected);
    else {
      selected = null;
      drawBox(null);
      hideHover();
      if (!spacingPanel.hidden) showPanel(null);
    }
  };

  const setOn = (value) => {
    if (value) setSpace(false);
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
  $('.space').onclick = () => setSpace(!spaceOn);
  $('.parent').onclick = () => selected?.parentElement && select(selected.parentElement);
  $('.unselect').onclick = () => setSpace(false);
  // One panel open at a time. openPanel toggles the one asked for; showPanel just shows it.
  const panels = () => [
    [panel, $('.list')],
    [optionsPanel, $('.opts')],
    [spacingPanel, null],
    [settingsPanel, $('.gear')],
  ];
  const showPanel = (which) => {
    for (const [p, button] of panels()) {
      p.hidden = p !== which;
      button?.setAttribute('aria-expanded', String(!p.hidden));
    }
  };
  const openPanel = (which) => showPanel(which.hidden ? which : null);
  $('.list').onclick = () => openPanel(panel);
  $('.opts').onclick = () => openPanel(optionsPanel);
  $('.gear').onclick = () => openPanel(settingsPanel);

  // Bar position, per site: a page's own controls tend to sit in the same corner on every page.
  const posKey = `text-editor:${location.host}:position`;
  const positions = ['top-left', 'top-center', 'top-right', 'bottom-left', 'bottom-center', 'bottom-right'];
  const place = (pos) => {
    host.dataset.pos = pos;
    try {
      localStorage.setItem(posKey, pos);
    } catch {}
    for (const b of $('.positions').children) b.setAttribute('aria-pressed', String(b.dataset.pos === pos));
  };
  $('.positions').replaceChildren(
    ...positions.map((pos) => {
      const b = document.createElement('button');
      b.dataset.pos = pos;
      b.textContent = pos.replace('-', ' ').replace(/^./, (c) => c.toUpperCase());
      b.onclick = () => place(pos);
      return b;
    }),
  );
  let savedPos = null;
  try {
    savedPos = localStorage.getItem(posKey);
  } catch {}
  place(positions.includes(savedPos) ? savedPos : 'bottom-right');

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
    // Inline display rather than [hidden], which a page's own display classes can override. The
    // variant's own inline display (say display:grid) is kept aside and put back when it shows.
    variants.forEach((v, j) => {
      if (!('teDisplay' in v.dataset)) v.dataset.teDisplay = v.style.display;
      v.style.display = j === index ? v.dataset.teDisplay : 'none';
    });
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
    for (const [path, s] of Object.entries(spacing)) {
      const el = find(path);
      if (!el) continue;
      for (const [prop, r] of Object.entries(s.props)) {
        r.inline ? el.style.setProperty(prop, r.inline) : el.style.removeProperty(prop);
      }
    }
    spacing = {};
    saveSpacing();
    render();
    if (selected) select(selected);
  };
  $('.close').onclick = () => {
    setOn(false);
    setSpace(false);
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
  for (const [path, s] of Object.entries(spacing)) {
    const el = find(path);
    if (el) for (const [prop, r] of Object.entries(s.props)) el.style.setProperty(prop, r.after);
  }

  document.head.append(pageStyle);
  document.body.append(host);
  render();
  window.__textEditor = { show: () => document.body.append(host) };
}

if (document.currentScript) {
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', textEditor) : textEditor();
}
