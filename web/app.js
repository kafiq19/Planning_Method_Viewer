"use strict";
const $ = id => document.getElementById(id);
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  del(k) { try { localStorage.removeItem(k); } catch (e) {} },
};
const state = { mode: store.get("mode", "plain"), tab: store.get("tab", "projects"), data: null, seq: 0, msg: null };

/* ---------- debug log: open the page with ?debug=1 (or store "debug" = 1) to see each request's time and any error ---------- */
(function () {
  let on = false;
  try { on = /[?&]debug=1\b/.test(location.search) || store.get("debug", "") === "1"; } catch (e) {}
  if (!on) return;
  const lines = [];
  let box = null;
  const log = (kind, text) => {
    lines.push(new Date().toLocaleTimeString() + " " + kind + " " + text);
    if (lines.length > 12) lines.shift();
    console.log("[planner]", kind, text);
    if (!box) { box = document.createElement("pre"); box.id = "debugLog"; document.body.append(box); }
    box.textContent = lines.join("\n");
  };
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const t0 = performance.now(), name = String(url).split("?")[0] + (opts && opts.method ? " " + opts.method : "");
    try {
      const r = await realFetch(url, opts);
      const ms = Math.round(performance.now() - t0);
      log(ms > 1000 ? "SLOW" : "ok", name + " " + r.status + " " + ms + "ms");
      return r;
    } catch (e) {
      log("FAIL", name + " " + e.message + " after " + Math.round(performance.now() - t0) + "ms");
      throw e;
    }
  };
  window.addEventListener("error", e => log("ERROR", e.message + " (" + (e.filename || "").split("/").pop() + ":" + e.lineno + ")"));
  window.addEventListener("unhandledrejection", e => log("REJECTED", String(e.reason && e.reason.message || e.reason)));
  log("debug", "on; turn off with localStorage.removeItem('debug') and leave ?debug=1 off the address");
})();

/* ---------- small DOM helper (text is always set as text, never as HTML) ---------- */
function h(tag, cls, ...kids) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  for (const k of kids) if (k != null && k !== false) n.append(k);
  return n;
}
const span = (cls, text) => h("span", cls, text);

/* ---------- pop-up menus: one open at a time; a click outside or Esc closes them ---------- */
const pops = [];
function popup(btn, menu) {
  const set = open => { menu.classList.toggle("hidden", !open); btn.setAttribute("aria-expanded", String(open)); };
  btn.addEventListener("click", e => { e.stopPropagation(); const open = menu.classList.contains("hidden"); closePops(); set(open); });
  pops.push(set);
}
function closePops() { for (const set of pops) set(false); }
document.addEventListener("click", e => { if (!e.target.closest(".menu")) closePops(); });
popup($("more"), $("moreMenu"));

/* ---------- theme (follows the system until it is chosen in the menu) ---------- */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  $("theme").firstChild.textContent = t === "dark" ? "Light mode " : "Dark mode ";
  $("themeNote").textContent = store.get("theme", null) ? "" : "follows system";
}
applyTheme(store.get("theme", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
$("theme").onclick = () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  store.set("theme", t); applyTheme(t); closePops();
};

/* ---------- text size and font (⋯ menu), remembered in this browser ---------- */
const SIZES = [["Small", .9, 12], ["Default", 1, 14], ["Large", 1.15, 16], ["Larger", 1.3, 18]];   // name, scale, size of its "A"
const FONTS = [                                                                // installed fonts only: no downloads
  ["System", '-apple-system, "Segoe UI", system-ui, sans-serif'],
  ["Rounded", 'ui-rounded, "SF Pro Rounded", "Arial Rounded MT", "Varela Round", -apple-system, "Segoe UI", system-ui, sans-serif'],
  ["Serif", 'Charter, "Bitstream Charter", "Iowan Old Style", Georgia, Cambria, serif'],
  ["Legible", '"Atkinson Hyperlegible", Verdana, "DejaVu Sans", Tahoma, sans-serif'],
  ["Condensed", '"Avenir Next Condensed", "Roboto Condensed", "Arial Narrow", sans-serif-condensed, system-ui, sans-serif'],
  ["Monospace", 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'],
];
function applyText() {
  const size = SIZES.find(z => z[0] === store.get("textSize", "Default")) || SIZES[1];
  const font = FONTS.find(f => f[0] === store.get("font", "System")) || FONTS[0];
  document.documentElement.style.setProperty("--fz", size[1]);
  document.documentElement.style.setProperty("--vfont", font[1]);
  for (const b of $("textSize").children) { const on = b.dataset.size === size[0]; b.classList.toggle("on", on); b.setAttribute("aria-checked", String(on)); }
  $("font").value = font[0];
}
for (const [name, , px] of SIZES) {
  const b = document.createElement("button");
  b.textContent = "A"; b.style.fontSize = px + "px"; b.dataset.size = name;
  b.title = name; b.setAttribute("aria-label", name); b.setAttribute("role", "radio");
  b.onclick = e => { e.stopPropagation(); store.set("textSize", name); applyText(); };
  $("textSize").append(b);
}
for (const [name, stack] of FONTS) {
  const o = document.createElement("option");
  o.value = o.textContent = name; o.style.fontFamily = stack;
  $("font").append(o);
}
$("font").onchange = () => { store.set("font", $("font").value); applyText(); };
applyText();

/* ---------- editor, files ---------- */
const editor = $("editor");
editor.addEventListener("input", () => { remember(); state.msg = null; showFile(); schedule(); });
editor.addEventListener("keydown", e => {            // Tab indents (the format is tab-based)
  if (e.key !== "Tab" || e.ctrlKey || e.metaKey || e.altKey) return;
  e.preventDefault();
  const { selectionStart: a, selectionEnd: b, value: v } = editor;
  if (a === b || !v.slice(a, b).includes("\n")) {
    editor.setRangeText("\t", a, b, "end");
  } else {                                           // multi-line: indent / outdent every line
    const start = v.lastIndexOf("\n", a - 1) + 1;
    const block = v.slice(start, b).split("\n").map(l => e.shiftKey ? l.replace(/^(\t| {1,4})/, "") : "\t" + l).join("\n");
    editor.setRangeText(block, start, b, "select");
  }
  editor.dispatchEvent(new Event("input"));
});

/* ---------- files, read and written by the local server through /api/file. Two kinds:
   - a project's pages (python planner.py --serve): saved automatically about a second after each change.
   - one file given on the command line (python planner.py --serve notes.txt): saved when you press Save.
   The text box shows one file at a time: opening a page saves the one being left first and loads the other from disk.
   Edits that couldn't be saved yet are kept per file ("draft:<path>": {version, text}) and come back with the page.
   The server checks the version before every write, so a change made elsewhere is never overwritten silently. ---------- */
const nl = s => s.replace(/\r\n?/g, "\n");                 // what a text box does to line endings
const unsaved = () => state.file && editor.value !== state.file.saved;
const AUTOSAVE_MS = 1000;
let autoTimer;
const baseName = p => p.split(/[\\/]/).pop();
const draftKey = p => "draft:" + p;
function readDraft(p) { try { return JSON.parse(store.get(draftKey(p), "null")); } catch (e) { return null; } }
function remember() {                                       // keep a file's unsaved edits
  const f = state.file;
  if (!f) return;
  if (editor.value === f.saved) store.del(draftKey(f.path));
  else store.set(draftKey(f.path), JSON.stringify({ version: f.version || "", text: editor.value }));
}

function showFile(problem) {                                // header: the breadcrumb (or the file chip) · Saved, or the Save pill
  const st = $("fileStatus"), f = state.file, chip = $("fileChip"), auto = !!state.folio;
  st.classList.toggle("bad", !!problem);
  $("fileName").textContent = f ? f.name : "";
  chip.title = f ? f.path : "";
  chip.classList.toggle("hidden", !f || auto);
  $("save").classList.toggle("hidden", !unsaved() || !!problem || auto);
  showCrumbs();
  if (problem) return st.replaceChildren(...problem);
  if (!f) return st.replaceChildren();
  st.replaceChildren(unsaved() ? (auto ? "Saving…" : "") : "Saved");
  if (auto && unsaved() && !f.blocked) { clearTimeout(autoTimer); autoTimer = setTimeout(() => save(), AUTOSAVE_MS); }
}

function setFile(text, version) {                           // the page now matches the file on disk
  state.file.saved = nl(text); state.file.version = version; state.file.blocked = false;
  if (editor.value !== state.file.saved) { replaceText(state.file.saved); schedule(); }
  remember();
  showFile();
}

async function fileApi(body, path = "/api/file") {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) } : {});
  let d;
  try { d = await r.json(); } catch (e) { d = { error: r.status === 404 ? "OLD_SERVER" : r.statusText || "no answer from the server" }; }
  return [r, d];
}
// The file as it is on disk now.
const fetchFile = f => state.folio ? fileApi(null, "/api/file?path=" + encodeURIComponent(f.path)) : fileApi();

function useFile(d) {                                       // show this file (from /api/file) in the text box
  state.file = { name: d.name, path: d.path, version: d.version, saved: nl(d.text) };
  state.switched = true; state.msg = null;
  const draft = readDraft(d.path), keep = !!draft && draft.text !== state.file.saved;
  editor.value = keep ? draft.text : state.file.saved;
  editor.setSelectionRange(0, 0); editor.scrollTop = 0;
  if (!keep) store.del(draftKey(d.path));
  const stale = keep && draft.version !== (d.version || "");   // edits made on an older version: let the user choose
  if (stale) state.file.blocked = true;
  showFile();
  if (stale) conflict();
  render(false);
}

async function leaveFile() {                                // before showing another file: save this one (if that fails, its draft stays)
  const f = state.file;
  if (!f) return;
  clearTimeout(autoTimer);
  while (f.saving) await new Promise(ok => setTimeout(ok, 50));
  if (unsaved() && !f.blocked) await save();
  remember();
}

async function startFileMode() {
  let r, d;
  try { [r, d] = await fileApi(); } catch (e) { return showFile(); }   // page opened without the server
  if (!r.ok) return showFile();
  if (d.name) return useFile(d);                            // a file given on the command line: just that one
  let folio = [{ ok: false }, {}];
  try { folio = await fileApi(null, "/api/portfolio"); } catch (e) {}
  if (folio[0].ok && folio[1].name) return startPortfolio(folio[1]);   // python planner.py --serve: the Projects folder
}

const DOC = "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5";
const FOLDER = "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z";
async function save(force) {
  if (!state.file) return;                                  // All projects: everything is already on disk
  const f = state.file;
  if (f.saving) { f.again = true; return; }                 // one write at a time; the newest text goes next
  clearTimeout(autoTimer);
  const text = editor.value;
  f.saving = true;
  showFile(["Saving…"]);
  try {
    const body = { path: f.path, text, version: f.version, force: !!force };
    const [r, d] = await fileApi(body);
    if (r.status === 409 && d.conflict) return conflict();
    if (!r.ok) throw new Error(d.error || r.statusText);
    f.version = d.version; f.saved = text; f.blocked = false;
    if (state.file === f) remember();
    showFile();
  } catch (e) {
    f.blocked = true;                                       // not retried automatically; Save (Ctrl/⌘-S) tries again
    showFile(["Not saved: " + e.message]);
  } finally {
    f.saving = false;
    if (f.again) { f.again = false; if (state.file === f && unsaved() && !f.blocked) save(); }
  }
}

function conflict() {                                       // the file changed on disk under us: never overwrite silently
  state.file.blocked = true;
  const b = (label, fn) => { const x = h("button", "", label); x.onclick = fn; return x; };
  showFile([state.file.name + " changed on disk.",
    b("Load disk version", async () => {
      if (unsaved() && !confirm("Replace your unsaved changes with the version on disk?")) return;
      const [r, d] = await fetchFile(state.file);
      if (r.ok) setFile(d.text, d.version);
    }),
    b("Keep mine and overwrite", () => save(true))]);
}

window.addEventListener("focus", async () => {              // pick up edits made in another editor
  if (state.all) return render(false);                      // All projects: read the backlogs again
  if (!state.file || state.file.saving) return;
  const f = state.file;
  let r, d;
  try { [r, d] = await fetchFile(f); } catch (e) { return; }
  if (!r.ok || state.file !== f || f.saving || d.version === f.version) return;
  if (unsaved()) conflict(); else setFile(d.text, d.version);
});
window.addEventListener("beforeunload", e => { if (unsaved()) { e.preventDefault(); e.returnValue = ""; } });
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
  if (e.key === "Escape") { closePops(); if (document.body.classList.contains("drawer-open")) openDrawer(false); }
});
$("save").onclick = () => save();
$("saveItem").onclick = () => { closePops(); save(); };
for (const ev of ["dragover", "drop"]) document.body.addEventListener(ev, e => e.preventDefault());   // a dropped file must not replace the page
$("today").value = store.get("today", "");
$("defWho").value = store.get("defWho", "");                // new-task defaults (⋯): prefill + Add task's Who / Effort
$("defWho").onchange = () => store.set("defWho", $("defWho").value.trim());
for (const [v] of [["xs"], ["s"], ["m"], ["l"], ["xl"]]) { const o = document.createElement("option"); o.value = v; o.textContent = v.toUpperCase(); $("defEffort").append(o); }
$("defEffort").value = store.get("defEffort", "");
$("defEffort").onchange = () => store.set("defEffort", $("defEffort").value);
$("today").onchange = () => { store.set("today", $("today").value.trim()); render(true); };

/* ---------- modes ---------- */
function setMode(m) {
  state.mode = m; store.set("mode", m);
  render(true);
}
$("modes").onclick = e => { if (e.target.dataset.mode) setMode(e.target.dataset.mode); };
$("split").checked = store.get("split", "0") === "1";
$("split").onchange = () => { store.set("split", $("split").checked ? "1" : "0"); layout(); };

function layout() {
  const all = !!state.all;                                  // All projects: the views only (there is no one text)
  if (all) state.mode = "planner";
  const can = plannerOK(), pb = $("modes").querySelector('[data-mode="planner"]');
  if (state.mode === "planner" && !can) state.mode = "plain";
  pb.disabled = !can;
  pb.title = can ? "" : "Planner is for a project's Backlog and Archive";
  const plain = state.mode === "plain", split = $("split").checked && !all;
  for (const b of $("modes").children) b.classList.toggle("on", b.dataset.mode === state.mode);
  $("modes").classList.toggle("hidden", all);
  $("editorPane").classList.toggle("hidden", !plain && !split);
  $("editorPane").classList.toggle("solo", plain);
  $("viewPane").classList.toggle("hidden", plain);
  $("splitWrap").classList.toggle("hidden", plain || all);
  $("todayWrap").classList.toggle("hidden", state.mode !== "planner");
  $("viewPane").classList.toggle("jump", split && state.mode === "planner");
  if (state.mode !== "planner" && !(state.msg && state.msg.anyMode)) toast.classList.add("hidden");   // edit messages belong to Planner mode
}

/* Edit alongside: clicking a task (not one of its buttons) selects its line in the text box and scrolls it into view */
$("viewPane").addEventListener("click", e => {
  const row = e.target.closest("[data-line]");
  if (!row || !$("viewPane").classList.contains("jump") || e.target.closest("button, input, select, a, .editbox, .pickbox")) return;
  if (String(getSelection())) return;                   // the user is selecting text in the view, not jumping
  goToLine(+row.dataset.line);
});
function goToLine(n) {
  const v = editor.value, lines = v.split("\n");
  if (!(n >= 1 && n <= lines.length)) return;
  const start = lines.slice(0, n - 1).reduce((a, l) => a + l.length + 1, 0), end = start + lines[n - 1].length;
  const m = document.createElement("div"), cs = getComputedStyle(editor);   // measure where the line sits, wrapping included
  m.className = "measure";
  for (const k of ["font", "letterSpacing", "tabSize", "padding", "border", "boxSizing"]) m.style[k] = cs[k];
  m.style.width = editor.clientWidth + "px";
  m.textContent = v.slice(0, start) + "\u200b";
  document.body.append(m);
  const y = m.scrollHeight - parseFloat(cs.paddingBottom) - parseFloat(cs.lineHeight);
  m.remove();
  editor.focus({ preventScroll: true });
  editor.setSelectionRange(start, end);
  editor.scrollTop = Math.max(0, y - editor.clientHeight / 3);       // the line a third of the way down
}

let timer;
function schedule() { clearTimeout(timer); timer = setTimeout(() => render(false), 400); }   // typing: wait for a pause before asking the server

// Is the planner view already showing exactly this data (for this page, tab and mode)?
const shownKey = () => [state.file && state.file.path, state.all, state.tab, state.mode, state.switched].join("|");
function unchanged(data) {
  const view = $("viewPane");
  return !!state.shown && state.shown.key === shownKey() && view.children.length === 2 && view.firstChild === tabsRow
    && JSON.stringify(state.shown.data) === JSON.stringify(data);
}

async function render(relayout) {
  if (relayout) layout();
  const view = $("viewPane");
  if (state.mode === "plain") return;
  if (state.mode === "markdown") {
    view.replaceChildren(h("div", "md"));
    view.firstChild.innerHTML = markdown(editor.value);    // markdown() escapes all input first
    return;
  }
  const seq = ++state.seq;
  if (state.ctl) state.ctl.abort();                          // the server needn't finish an answer nobody will read
  const ctl = state.ctl = new AbortController();
  try {
    const when = { today: $("today").value.trim() || null, period: archiveYear() ? null : state.period, planner: planFor(), year: archiveYear(), habits: isHabitsPage() };
    const r = await fetch("/api/parse", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.all ? { all: true, ...when } : { text: editor.value, name: folioName(), ...when }), signal: ctl.signal });
    const data = await r.json();
    if (seq !== state.seq) return;
    if (!r.ok) {
      if (state.period) { setPeriod(null); return; }        // e.g. a stored period the server rejects: fall back to all dates
      throw new Error(data.error || r.statusText);
    }
    if (unchanged(data)) return;                             // same answer as the one on screen: leave the view (focus, scroll, open editors) alone
    state.data = data;
    plannerView();
  } catch (err) {
    if (err.name === "AbortError" || seq !== state.seq) return;
    view.replaceChildren(h("div", "err", "Could not parse: " + err.message +
      ". Planner mode needs the server: run  python planner.py --serve"));
  }
}

/* ---------- planner views ---------- */
const TABS = [["projects", "Projects"], ["timeline", "Timeline"], ["people", "People"], ["upcoming", "Upcoming"], ["planner", "Planner"]];
if (state.tab === "week") state.tab = "planner";            // the Week tab (1.5) is the Planner now

/* ---------- status clicks: the server rewrites only the task's status mark ---------- */
const NEXT = { open: "doing", doing: "done", done: "open" };
const STATUS_NAME = { open: "open", doing: "in progress", done: "done" };

function replaceText(text) {           // swap in the new text, keeping the cursor and scroll where they were
  const old = editor.value;
  let a = 0, b = 0;
  while (a < old.length && a < text.length && old[a] === text[a]) a++;
  while (b < old.length - a && b < text.length - a && old[old.length - 1 - b] === text[text.length - 1 - b]) b++;
  const top = editor.scrollTop;
  editor.setRangeText(text.slice(a, text.length - b), a, old.length - b, "preserve");
  editor.scrollTop = top;
  remember();
  showFile();
}

async function editTask(t, op, value, btn, done) {   // -> true if the text changed (callers can await it to go on)
  const before = editor.value, seq = ++state.seq;
  let ok = false;
  clearTimeout(timer);
  if (btn) btn.disabled = true;
  const when = { today: $("today").value.trim() || null, period: archiveYear() ? null : state.period, planner: planFor(), year: archiveYear(), habits: isHabitsPage() };
  try {
    if (state.all) {                                     // All projects: the server edits the task's backlog on disk
      const r = await fetch("/api/edit", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: t.path, version: state.data.versions[t.path], all: true, line: t.line, title: t.title, op, value, ...when }) });
      const res = await r.json();
      if (!r.ok) throw new Error(res.conflict ? "that project changed on disk; the view is up to date now, so try again" : res.error || r.statusText);
      if (seq !== state.seq) return true;
      state.data = res.data;
      state.msg = { text: done, undo: { path: t.path, before: res.before, after: res.text, version: res.version } };
      plannerView();
      return true;
    }
    const r = await fetch("/api/edit", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: before, name: folioName(), line: t.line, title: t.title, op, value, ...when }) });
    const res = await r.json();
    if (editor.value !== before) return render(false);          // typed meanwhile: drop the edit
    if (!r.ok) throw new Error(res.error || r.statusText);
    replaceText(res.text);
    state.data = res.data;
    state.msg = { text: done, undo: { before, after: res.text } };
    ok = true;
  } catch (err) {
    state.msg = { text: "Not changed: " + err.message, bad: true };
    if (seq === state.seq) { await render(false); return false; }
  }
  if (seq === state.seq) plannerView();
  return ok;
}
const setStatus = (t, status, btn) => editTask(t, "status", status, btn, `Marked "${t.title}" ${STATUS_NAME[status]}.`);

/* a one-line input over a cell; Enter applies, Esc or leaving cancels; with `tab`, Tab / Shift-Tab apply and move on */
function editCell(cell, placeholder, initial, apply, wide, fill, tab) {   // fill: from the cell's left edge to the row's right edge
  const input = h("input"), box = h("span", "editbox" + (wide ? " wide" : "") + (fill ? " fill" : ""), input);
  input.type = "text"; input.placeholder = placeholder; input.value = initial || "";
  input.setAttribute("aria-label", placeholder);
  const close = () => { if (box.isConnected) box.remove(); };
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); const v = input.value; input.onblur = null; close(); apply(v); }
    else if (e.key === "Escape") { close(); cell.focus(); }
    else if (e.key === "Tab" && tab) { e.preventDefault(); const v = input.value; input.onblur = null; close(); tab(e.shiftKey ? -1 : 1, v); }
  };
  input.onblur = close;
  input.onclick = e => e.stopPropagation();
  const row = cell.closest(".task, .hrow");        // float over the cell's line, right edge on the cell's right edge
  const r = row.getBoundingClientRect(), c = cell.getBoundingClientRect();
  box.style.top = (c.top - r.top) + "px"; box.style.height = c.height + "px";
  box.style.right = Math.max(0, r.right - c.right) + "px";
  input.style.maxWidth = Math.max(80, r.width) + "px";
  if (fill) { box.style.left = Math.max(0, c.left - r.left) + "px"; box.style.right = "8px"; }
  row.append(box);
  if (!fill && box.getBoundingClientRect().left < r.left) {  // a narrow pane: it would stick out on the left, so keep it inside the row
    box.style.right = "auto"; box.style.left = "0";
  }
  input.focus(); input.select();
}
/* a single-choice list under a cell (the Effort cell): arrows or a letter move, Enter or a click picks, Esc or leaving
   cancels; with `tab`, Tab / Shift-Tab keep the choice (the one moved to, else the current one) and move on */
function pickCell(cell, label, choices, current, apply, tab) {
  const box = h("div", "pickbox");
  box.setAttribute("role", "listbox"); box.setAttribute("aria-label", label);
  const close = () => { if (box.isConnected) box.remove(); document.removeEventListener("pointerdown", outside, true); };
  const outside = e => { if (!box.contains(e.target)) close(); };
  const items = choices.map(({ value, text, note, badge }) => {
    const on = value === current;
    const b = h("button", "mi", span("ck", on ? "✓" : ""), badge ? span("eff", text) : text, note ? span("k", note) : "");
    b.setAttribute("role", "option"); b.setAttribute("aria-selected", String(on));
    b.onclick = e => { e.stopPropagation(); close(); apply(value); };
    return b;
  });
  box.append(...items);
  let moved = false;
  box.onkeydown = e => {
    e.stopPropagation();
    const i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); moved = true;
      items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
    } else if (e.key.length === 1 && /\w/.test(e.key)) {      // a letter: the next choice starting with it (s, m, l, x …)
      const k = e.key.toLowerCase(), n = items.length;
      for (let j = 1; j <= n; j++) {
        const c = choices[(i + j) % n];
        if (String(c.text).toLowerCase().startsWith(k)) { moved = true; items[(i + j) % n].focus(); break; }
      }
    } else if (e.key === "Tab" && tab) {
      e.preventDefault(); close();
      tab(e.shiftKey ? -1 : 1, moved && i >= 0 ? choices[i].value : current);
    } else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); close(); cell.focus(); }
  };
  box.addEventListener("focusout", e => { if (!box.contains(e.relatedTarget)) setTimeout(() => { if (!box.contains(document.activeElement)) close(); }); });
  box.onclick = e => e.stopPropagation();
  const row = cell.closest(".task, .wcard, .wline, .ph, .hrow, .fhead");   // drop down from the cell, right edge on the cell's right edge
  const r = row.getBoundingClientRect(), c = cell.getBoundingClientRect();
  box.style.top = (c.bottom - r.top + 2) + "px";
  box.style.right = Math.max(0, r.right - c.right) + "px";
  row.append(box);
  if (box.getBoundingClientRect().left < r.left) { box.style.right = "auto"; box.style.left = "0"; }
  document.addEventListener("pointerdown", outside, true);
  (items.find(b => b.getAttribute("aria-selected") === "true") || items[0]).focus();
}
function cellButton(cls, label, tip, content, edit) {    // a Who / Effort / Date / + cell: shows its value, click edits it
  const b = h("button", "cell " + cls, ...content);
  b.title = tip; b.setAttribute("aria-label", label);
  b.onclick = e => { e.stopPropagation(); edit(b); };
  return b;
}
const ADD = () => span("add", "+");

/* "+ Add task": a new top-level task at the end of a project (op "task", sent with the project's @ line and name).
   Given no project (People, Timeline, Upcoming), the form also has a project picker; `prefill` starts the text. */
function addTaskRow(project, who = "") {           // who: People prefills that person's initials
  const btn = h("button", "addtask", span("plus", "+"), "Add task");
  btn.title = project ? "Add a task at the end of " + projLabel(project) : "Add a task to a project";
  btn.dataset.key = (project ? "p\n" + (project.path || "") + "\n" + project.name : "x") + "\n" + who;   // found again after a redraw (keep adding)
  const row = h("div", "addrow", btn);
  btn.onclick = () => openAdd(btn, project, who);
  return row;
}
/* + Add task: the title, then optional Who / Effort / Date fields (Tab moves between them), prefilled with the
   defaults from ⋯. Enter adds it and opens the form again for the next one; Esc or clicking away ends. The fields
   go to the server separately (op "task" with {title, who, effort, date}); the page never writes note syntax. */
function openAdd(btn, project, presetWho, keep) {
  const targets = state.data.targets;
  if (!project && !targets.length) {
    state.msg = { text: "There is no project yet: add one like  @Planning  in the text first.", bad: true };
    return showToast();
  }
  const input = h("input");
  input.type = "text"; input.placeholder = "new task"; input.setAttribute("aria-label", "New task");
  const fWhoIn = h("input", "fwho"), fDate = h("input", "fdate");
  fWhoIn.type = fDate.type = "text";
  fWhoIn.placeholder = "Who"; fWhoIn.setAttribute("aria-label", "Who (initials)");
  fDate.placeholder = "Date"; fDate.setAttribute("aria-label", "Date, like Oct24 or ~T1");
  const fEff = h("select", "feff", h("option", "", "Effort"), ...EFFORTS.map(([v]) => h("option", "", v.toUpperCase())));
  fEff.firstChild.value = ""; [...fEff.options].slice(1).forEach((o, i) => { o.value = EFFORTS[i][0]; });
  fEff.setAttribute("aria-label", "Effort");
  fWhoIn.value = keep ? keep.who : presetWho || store.get("defWho", "");
  fEff.value = keep ? keep.effort : store.get("defEffort", "");
  if (keep && keep.title) { input.value = keep.title; fDate.value = keep.date || ""; }
  let sel = null;
  if (!project) {
    const count = {};
    for (const t of targets) count[t.name] = (count[t.name] || 0) + 1;
    sel = h("select", "", ...targets.map((t, i) => {
      const o = h("option", "", projLabel(t) + (count[t.name] > 1 && t.section ? " (" + t.section + ")" : ""));
      o.value = i;
      return o;
    }));
    sel.setAttribute("aria-label", "Project");
    const last = store.get("addTo", ""), at = i => (targets[i].path || "") + "\n" + targets[i].line + "\n" + targets[i].name;
    const pick = [targets.findIndex(t => t.name === filt.proj), targets.findIndex((t, i) => at(i) === last), 0].find(i => i >= 0);
    sel.value = pick;
  }
  const form = h("div", "addform", ...(sel ? [sel] : []), input, fWhoIn, fEff, fDate);
  let closed = false, pressing = false;
  const cancel = () => {                         // closed is set first: removing the focused input fires focusout again
    if (closed) return;
    closed = true;
    form.replaceWith(btn);
  };
  form.addEventListener("pointerdown", () => { pressing = true; setTimeout(() => { pressing = false; }, 500); });
  form.addEventListener("focusout", () => setTimeout(() => {   // leaving the form cancels (a click on its own picker doesn't)
    if (!pressing && !form.contains(document.activeElement)) cancel();
  }));
  form.onkeydown = e => {
    e.stopPropagation();
    if (e.key === "Escape") { cancel(); btn.focus(); }
    else if (e.key === "Enter" && e.target !== sel) {
      e.preventDefault();
      const v = input.value.trim(), p = project || targets[sel.value];
      const fields = { title: v, who: fWhoIn.value.trim(), effort: fEff.value, date: fDate.value.trim() };
      cancel();
      if (!v) return;
      if (sel) store.set("addTo", (p.path || "") + "\n" + p.line + "\n" + p.name);
      const plain = !fields.who && !fields.effort && !fields.date;
      const done = editTask({ line: p.line, title: p.name, path: p.path }, "task", plain ? v : fields, null, `Added "${v}" to ${projLabel(p)}.`);
      done.then(ok => {                            // keep adding: the form again, empty, same Who / Effort; refused: as typed
        const again = [...plannerBody.querySelectorAll(".addtask")].find(b => b.dataset.key === btn.dataset.key);
        if (again) openAdd(again, project, presetWho, ok ? { who: fields.who, effort: fields.effort } : fields);
      });
    }
  };
  btn.replaceWith(form);
  input.focus();
}

async function undo() {
  const u = state.msg && state.msg.undo;
  state.msg = null;
  if (u && (u.path || u.files)) {                        // files on disk (All projects, the archive): each back, unless it changed since
    for (const x of u.files || [{ path: u.path, before: u.before, version: u.version }]) {
      const mine = state.file && !state.all && state.file.path === x.path;
      if (mine && unsaved()) { state.msg = { text: "Can't undo: this page has changed since", bad: true }; break; }
      const [r, d] = await fileApi({ path: x.path, text: x.before, version: x.version });
      if (!r.ok) { state.msg = { text: "Can't undo: " + (d.conflict ? baseName(x.path) + " changed since" : d.error || r.statusText), bad: true }; break; }
      if (mine) setFile(x.before, d.version);
    }
    if (u.files) { await refreshFolio(); drawDrawer(); }
    return render(false);
  }
  if (u && editor.value === u.after) { replaceText(u.before); render(false); }
  else plannerView();
}

const MARK = {                                  // open: ring; in progress: half-filled ring; done: filled with a check
  open: '<circle cx="9" cy="9" r="7" fill="none" stroke="currentColor" stroke-width="1.6"/>',
  doing: '<circle cx="9" cy="9" r="7" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M9 2a7 7 0 0 1 0 14z" fill="currentColor"/>',
  done: '<circle cx="9" cy="9" r="7.8" fill="currentColor"/><path d="M5.5 9.2l2.3 2.3 4.6-4.8" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
};
function statusBox(t) {
  const b = h("button", "st");
  b.innerHTML = `<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">${MARK[t.status]}</svg>`;   // fixed markup, no note text
  b.title = `${STATUS_NAME[t.status]}. Click to mark ${STATUS_NAME[NEXT[t.status]]} (line ${t.line})`;
  b.setAttribute("aria-label", b.title);
  b.onclick = () => setStatus(t, NEXT[t.status], b);
  return b;
}

/* ---------- filters (display only: they pick from the server's data, they never parse notes) ---------- */
const FKEYS = { q: "fq", who: "fwho", proj: "fproj", done: "fdone" };
const filt = { q: store.get("fq", ""), who: store.get("fwho", ""), proj: store.get("fproj", ""), done: store.get("fdone", "1") === "1" };
const filterOn = () => !!(filt.q.trim() || filt.who || filt.proj || !filt.done);

function filtered(d) {
  if (!filterOn()) return d;
  const q = filt.q.trim().toLowerCase();
  const keep = (t, proj) => (!filt.proj || proj === filt.proj)
    && (!filt.who || (filt.who === "(unassigned)" ? !t.assignees.length : t.assignees.includes(filt.who)))
    && (!q || [t.title, ...t.notes, proj].join("\n").toLowerCase().includes(q));
  const prune = (t, proj) => {                    // keep matching tasks, and their ancestors (dimmed) for context
    const children = t.children.map(c => prune(c, proj)).filter(Boolean);
    const self = !t.dim && keep(t, proj) && (filt.done || t.status !== "done");
    return self || children.length ? { ...t, children, dim: !self } : null;
  };
  const flat = list => list.filter(t => keep(t, t.project));
  const shown = t => filt.done || t.status !== "done";     // Projects and Timeline list done tasks unless "Show done tasks" is off
  const u = d.upcoming;
  return { ...d, filtered: true,
    projects: d.projects.map(sec => ({ ...sec,
      projects: sec.projects.map(p => ({ ...p, tasks: p.tasks.map(t => prune(t, p.name)).filter(Boolean) }))
        .filter(p => p.tasks.length) })).filter(sec => sec.projects.length),
    timeline: { ...d.timeline, rows: flat(d.timeline.rows).filter(shown), unscheduled: flat(d.timeline.unscheduled).filter(shown) },
    people: d.people.filter(g => !filt.who || g.name === filt.who)
      .map(g => ({ ...g, tasks: flat(g.tasks) })).filter(g => g.tasks.length),
    upcoming: { ...u, overdue: flat(u.overdue), due: flat(u.due), reminders: flat(u.reminders), doing: flat(u.doing) },
    planner: { ...d.planner, columns: d.planner.columns.map(x => ({ ...x, tasks: flat(x.tasks).filter(shown) })),
      projects: d.planner.projects.map(g => ({ ...g, tasks: flat(g.tasks).filter(shown) })).filter(g => g.tasks.length),
      backlog: d.planner.backlog.map(g => ({ ...g, tasks: flat(g.tasks) })).filter(g => g.tasks.length),
      priorities: flat(d.planner.priorities).filter(shown), habits: flat(d.planner.habits) } };
}

/* ---------- period: All dates / Month / Season, stepped with ‹ › (the server does the date math) ---------- */
try { state.period = JSON.parse(store.get("period", "null")); } catch (e) { state.period = null; }
const icon = (d, size = 15) => {                // a small stroke icon (inline SVG, no library)
  const n = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  n.setAttribute("width", size); n.setAttribute("height", size); n.setAttribute("viewBox", "0 0 24 24");
  n.setAttribute("aria-hidden", "true");
  n.innerHTML = `<path d="${d}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
  return n;
};
const pPrev = h("button", "", "‹"), pNext = h("button", "", "›"), pMid = h("button", "pmid"), pCaret = h("button", "pcaret", "▾");
const pMenu = h("div", "menu hidden"), pctl = h("span", "pctl", pPrev, pMid, pNext, h("span", "pop", pCaret, pMenu));
pCaret.setAttribute("aria-haspopup", "menu"); pCaret.setAttribute("aria-label", "All dates, by month or by season");
pCaret.title = "Show all dates, one month or one season";
popup(pCaret, pMenu);
pMid.onclick = e => {                            // the date: back to this month / season; already there (or All dates): the menu
  const per = state.data && state.data.period;
  if (per && !per.current) return setPeriod(per.now);
  e.stopPropagation(); pCaret.click();
};
function setPeriod(p) {
  state.period = p ? { kind: p.kind, year: p.year, index: p.index } : null;
  store.set("period", JSON.stringify(state.period));
  render(false);
}
pPrev.onclick = () => state.data.period && setPeriod(state.data.period.prev);
pNext.onclick = () => state.data.period && setPeriod(state.data.period.next);
function showPeriod(per) {       // ‹ › name where they go (on hover); the date says what is showing and returns to now
  const unit = per && (per.kind === "month" ? "month" : "season");
  pctl.classList.toggle("on", !!per);
  pctl.classList.toggle("away", !!per && !per.current);
  pPrev.classList.toggle("hidden", !per); pNext.classList.toggle("hidden", !per);
  pMid.textContent = per ? per.short : "All dates";   // "Fall 2026"; the line above the list gives the months
  pMid.title = !per ? "Show all dates, one month or one season"
    : per.current ? `This ${unit}. Use ‹ › to step, ▾ for all dates, months or seasons` : `Back to this ${unit}: ${per.now.label}`;
  const item = (label, note, on, pick, disabled) => {
    const b = h("button", "mi", label, span("k", note)); b.setAttribute("role", "menuitemradio");
    b.setAttribute("aria-checked", !!on); b.disabled = !!disabled;
    b.onclick = () => { closePops(); pick(); };
    return b;
  };
  const kind = per ? per.kind : "";
  pMenu.replaceChildren(
    item("All dates", kind === "" ? "✓" : "", kind === "", () => kind && setPeriod(null)),
    item("By month", kind === "month" ? "✓" : "", kind === "month", () => kind !== "month" && setPeriod({ kind: "month" })),
    item("By season", kind === "season" ? "✓" : "Winter, Summer, Fall", kind === "season", () => kind !== "season" && setPeriod({ kind: "season" })),
    ...(per ? [h("div", "sep"), item("This " + unit, per.current ? "you're here" : per.now.label, false, () => setPeriod(per.now), per.current)] : []));
  if (!per) return;
  for (const [b, dir, to] of [[pPrev, "Previous", per.prev], [pNext, "Next", per.next]]) {
    b.title = `${dir} ${unit}: ${to.label}`; b.setAttribute("aria-label", b.title);
  }
}

/* ---------- Planner: Year / Season / Month / Week, then ‹ Oct 12-18 › (the server does the date math). The level is
   remembered ("planKind"); the period is not, so the Planner opens on the current week, month, season or year ---------- */
const PLAN_LEVELS = [["year", "Year"], ["season", "Season"], ["month", "Month"], ["week", "Week"]];
const PLAN_UNIT = { week: "week", month: "month", season: "season", year: "year" };
const COLUMN_UNIT = { day: "day", week: "week", month: "month", season: "trimester" };
const PLAN_RANK = { day: 0, week: 1, month: 2, season: 3, year: 4 };
state.plan = { kind: PLAN_LEVELS.some(([k]) => k === store.get("planKind", "")) ? store.get("planKind", "") : "week" };
const wPrev = h("button", "", "‹"), wNext = h("button", "", "›"), wMid = h("button", "pmid"), wSeg = h("span", "seg wlevels");
const wctl = h("span", "pctl on", wPrev, wMid, wNext), wbox = h("span", "wbox hidden", wSeg, wctl);
wSeg.setAttribute("role", "radiogroup"); wSeg.setAttribute("aria-label", "Plan by");
for (const [k, label] of PLAN_LEVELS) {
  const b = h("button", "", label);
  b.dataset.kind = k; b.setAttribute("role", "radio");
  b.onclick = () => { store.set("planKind", k); setPlan({ kind: k }); };
  wSeg.append(b);
}
state.habitWeek = { kind: "week" };                       // the Habits page has its own week (not remembered)
const isHabitsPage = () => !!(state.folio && !state.all && state.file && /^[^/]+\/habits\.kf$/.test(state.file.path));
const planFor = () => isHabitsPage() ? state.habitWeek : state.plan;
const setPlan = p => {
  const v = p.year != null ? { kind: p.kind, year: p.year, index: p.index } : { kind: p.kind };
  if (isHabitsPage()) state.habitWeek = v; else state.plan = v;
  render(false);
};
wPrev.onclick = () => setPlan(state.data.planner.prev);
wNext.onclick = () => setPlan(state.data.planner.next);
wMid.onclick = () => { if (!state.data.planner.current) setPlan(state.data.planner.now); };
function showPlan(pl, on) {
  wbox.classList.toggle("hidden", !on); pctl.classList.toggle("hidden", on);
  wSeg.classList.toggle("hidden", isHabitsPage());          // Habits: one week at a time
  if (!on) return;
  const unit = PLAN_UNIT[pl.kind];
  for (const b of wSeg.children) { const sel = b.dataset.kind === pl.kind; b.classList.toggle("on", sel); b.setAttribute("aria-checked", String(sel)); }
  wctl.classList.toggle("away", !pl.current);
  wMid.textContent = pl.label;
  wMid.title = pl.current ? `This ${unit}. Use ‹ › to step` : `Back to this ${unit}: ${pl.now.label}`;
  for (const [b, dir, to] of [[wPrev, "Previous", pl.prev], [wNext, "Next", pl.next]]) {
    b.title = `${dir} ${unit}: ${to.label}`; b.setAttribute("aria-label", b.title);
  }
}

/* ---------- tool row: tabs, then search, Filter (person, project, show done) and the period ---------- */
const fQ = h("input"), fWho = h("select"), fProj = h("select"), fDone = h("input");
const fClear = h("button", "ghost", "Clear filters"), fCount = span("badge", "");
fQ.type = "search"; fQ.placeholder = "Search"; fQ.value = filt.q; fQ.setAttribute("aria-label", "Search tasks, notes and projects");
fDone.type = "checkbox"; fDone.checked = filt.done;
const fBtn = h("button", "", icon("M4 6h16M7 12h10M10 18h4"), " Filter ", fCount);
fBtn.setAttribute("aria-haspopup", "dialog");
fBtn.style.cssText = "display: inline-flex; align-items: center; gap: 4px";
const fPanel = h("div", "menu panel hidden",
  h("label", "field", "Person", fWho), h("label", "field", "Project", fProj),
  h("label", "check", fDone, "Show done tasks"), h("div", "", fClear));
fPanel.lastChild.style.cssText = "display: flex; justify-content: flex-end";
popup(fBtn, fPanel);
const tabsBox = h("span", "tabs"), tabsRow = h("div", "toolbar", tabsBox,
  h("span", "tools", h("label", "search", icon("M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-3.5-3.5"), fQ),
    h("span", "pop", fBtn, fPanel), pctl, wbox));
const contextLine = h("div", "context"), plannerBody = h("div"), contentBox = h("div", "content", contextLine, plannerBody);
const toast = h("div", "toast hidden");
toast.setAttribute("role", "status");
document.body.append(toast);
function setFilt(k, v) {
  filt[k] = v; store.set(FKEYS[k], k === "done" ? (v ? "1" : "0") : v);
  plannerView();
}
fQ.oninput = () => setFilt("q", fQ.value);
fQ.onkeydown = e => { if (e.key === "Escape") { fQ.value = ""; setFilt("q", ""); } };
fWho.onchange = () => setFilt("who", fWho.value);
fProj.onchange = () => setFilt("proj", fProj.value);
fDone.onchange = () => setFilt("done", fDone.checked);
fClear.onclick = () => {
  fWho.value = ""; fProj.value = ""; fDone.checked = true;
  for (const [k, v] of [["who", ""], ["proj", ""]]) { filt[k] = v; store.set(FKEYS[k], v); }
  setFilt("done", true);
};
function options(sel, names, current, all) {     // a chosen name stays listed even if it has no tasks right now
  const list = [...new Set([...names, ...(current ? [current] : [])])];
  const key = list.join("\n");
  if (sel.dataset.opts !== key) {
    sel.replaceChildren(h("option", "", all), ...list.map(n => h("option", "", n)));
    sel.firstChild.value = "";
    sel.dataset.opts = key;
  }
  sel.value = current;
}

function showToast() {                           // the last edit's message, with Undo while it still applies
  const m = state.msg;
  toast.classList.toggle("hidden", !m);
  if (!m) return toast.replaceChildren();
  toast.classList.toggle("bad", !!m.bad);
  const close = h("button", "", "×"); close.setAttribute("aria-label", "Dismiss");
  close.onclick = () => { state.msg = null; showToast(); };
  const undoBtn = m.undo && h("button", "", "Undo");
  if (undoBtn) undoBtn.onclick = undo;
  toast.replaceChildren(...[span("", m.text), undoBtn, close].filter(Boolean));
}

function plannerView() {
  state.shown = null;                                // set again below once it is drawn
  if (state.switched) {                             // another file: drop a person or project filter it doesn't have
    state.switched = false;
    if (filt.who && filt.who !== "(unassigned)" && !state.data.people.some(g => g.name === filt.who)) { filt.who = ""; store.set(FKEYS.who, ""); }
    if (filt.proj && !state.data.targets.some(t => t.name === filt.proj)) { filt.proj = ""; store.set(FKEYS.proj, ""); }
  }
  const view = $("viewPane"), d = filtered(state.data);
  options(fWho, state.data.people.map(g => g.name), filt.who, "Everyone");
  options(fProj, state.data.projects.flatMap(sec => sec.projects.map(p => p.name)), filt.proj, "All projects");
  const n = [filt.who, filt.proj, !filt.done].filter(Boolean).length;
  fCount.textContent = n ? String(n) : "";
  fBtn.title = n ? `${n} filter${n > 1 ? "s" : ""} on` : "Filter by person or project, or hide done tasks";
  fClear.disabled = !n;
  showPeriod(state.data.period);
  const habitsPage = isHabitsPage();
  showPlan(state.data.planner, state.tab === "planner" || habitsPage);
  if (archiveYear()) pctl.classList.add("hidden");   // an archive page is one year; no period
  contentBox.classList.toggle("wide", state.tab === "planner" || habitsPage);
  showCrumbs();
  const tabs = [];
  for (const [id, label] of TABS) {
    const b = h("button", "tab" + (id === state.tab ? " on" : ""), label);
    b.onclick = () => {
      state.tab = id; store.set("tab", id);
      if (id === "planner" && state.folio && !state.all) return showAll();   // a portfolio has one Planner, for every project
      plannerView(); drawDrawer();
    };
    tabs.push(b);
  }
  tabsBox.replaceChildren(...(habitsPage ? [h("button", "tab on", "Habits")] : tabs));
  const per = d.period, bits = [];               // say only what isn't obvious: a pinned Today, a period
  if (archiveYear()) bits.push(`The archive for ${archiveYear()}: finished tasks, as they were moved here`);
  else if ($("today").value.trim()) bits.push("As of " + d.today_label);
  if (habitsPage) bits.push("Tick a day when you've done it · each habit repeats on the days its frequency says");
  else if (state.tab === "planner") {
    const pl = d.planner, unit = COLUMN_UNIT[pl.column_kind];
    bits.push(`Drag a task onto a ${unit}, or use its Plan cell · ☆ marks a top priority for this ${PLAN_UNIT[pl.kind]}`
      + (per ? " · the period doesn't apply here" : ""));
  }
  else if (per) bits.push(per.label + (per.current ? (per.kind === "month" ? " (this month)" : " (this season)") : ""),
    state.tab === "upcoming" ? "Upcoming always shows the next " + d.upcoming.days + " days" : "undated tasks are hidden");
  contextLine.textContent = bits.join(" · ");
  plannerBody.replaceChildren((habitsPage ? vHabits : { projects: vProjects, timeline: vTimeline, people: vPeople, upcoming: vUpcoming, planner: vPlanner }[state.tab])(d));
  showToast();
  if (view.children.length !== 2 || view.firstChild !== tabsRow) view.replaceChildren(tabsRow, contentBox);
  state.shown = { key: shownKey(), data: state.data };
}

const BELL = "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0";
const guides = depth => Array.from({ length: depth }, () => span("g"));

/* one task row: [guides][status][@project][title] | Who | Effort | Date | + ; the last four are click-to-edit cells */
/* Tab between a row's editable parts: title → Who → Effort → Date → the next row's title (Shift-Tab goes back).
   `applied` is the edit being saved (or nothing); the views are redrawn after it, so the row is found again by its line. */
const TAB_ORDER = ["title", "who", "size", "date"];
function findAgain(row) {                         // -> () => the same task's row after a redraw (by line, and which copy)
  const rows = () => [...plannerBody.querySelectorAll(".task")];
  const line = row.dataset.line, nth = rows().filter(r => r.dataset.line === line).indexOf(row);
  return () => { const same = rows().filter(r => r.dataset.line === line); return same[nth] || same[0]; };
}
async function tabTo(row, kind, dir, applied) {
  const again = findAgain(row);
  const ok = await applied;
  if (applied && ok === false) return;               // refused: stay put (the message says why)
  const here = again();
  if (!here) return;
  const all = [...plannerBody.querySelectorAll(".task")];
  let i = TAB_ORDER.indexOf(kind) + dir, to = here;
  if (i >= TAB_ORDER.length) { to = all[all.indexOf(here) + 1]; i = 0; }
  else if (i < 0) { to = all[all.indexOf(here) - 1]; i = TAB_ORDER.length - 1; }
  if (to && to.open) to.open[TAB_ORDER[i]]();
}

function taskNode(t, { project = false, span: useSpan = false, depth = 0, date, rem, week } = {}) {
  const row = h("div", "task s-" + t.status + (t.notable ? " notable" : ""));
  row.style.setProperty("--d", depth);
  row.title = "line " + t.line;                         // hover shows where the task is in the text
  row.dataset.line = t.line;
  const lead = h("div", "lead", ...guides(depth), statusBox(t));
  if (project) lead.append(span("proj", "@" + t.project));
  const ttl = span("ttl", t.title);
  lead.append(ttl);
  const open = row.open = {};                           // each editable part's editor, so Tab can move between them
  const tabber = kind => (dir, v) => tabTo(row, kind, dir, open[kind].apply(v));
  open.title = () => {                                  // edit the task's text
    if (typeof t.text !== "string") {                   // a server started before title editing existed sends no `text`
      state.msg = { text: "To edit a task's text, restart the server (python3 planner.py --serve).", bad: true };
      return showToast();
    }
    editCell(ttl, "task, like  draft (KA) (m) Oct24", t.text, open.title.apply, false, true, tabber("title"));
  };
  open.title.apply = v => {
    v = v.trim();
    if (!v || v === t.text) return;
    return editTask(t, "text", v, null, `Changed "${t.title}".`);
  };
  ttl.onclick = e => {                                  // with Edit alongside the click jumps to the line instead
    if ($("viewPane").classList.contains("jump") || String(getSelection())) return;
    e.stopPropagation();
    open.title();
  };

  const current = t.assignees.join(", ");
  const who = cellButton("who r", "Change initials", current ? `${current}. Click to change (empty removes)` : "Assign: add initials",
    [current ? span("t", current) : ADD()],
    cell => editCell(cell, "initials: KA, RT (empty removes)", current, open.who.apply, false, false, tabber("who")));
  open.who = () => who.click();
  open.who.apply = v => {
    const next = v.trim().split(/[\s,]+/).filter(Boolean).join(", ");
    if (next === current) return;
    return editTask(t, "who", v, null, next ? `Set "${t.title}" to ${next}.` : `Removed the initials from "${t.title}".`);
  };

  const eff = t.effort && span("eff", t.effort.toUpperCase());
  const size = cellButton("size mid", "Set effort", t.effort ? `effort: ${pts(t.points)}. Click to change` : "Set effort: XS, S, M, L or XL",
    [eff || ADD()],
    cell => pickCell(cell, "Effort", [...EFFORTS.map(([v, n]) => ({ value: v, text: v.toUpperCase(), note: pts(n), badge: true })),
      { value: "", text: "None" }], t.effort || "", open.size.apply, tabber("size")));
  open.size = () => size.click();
  open.size.apply = v => {
    if (v === (t.effort || "")) return;
    return editTask(t, "effort", v, null, v ? `Set the effort of "${t.title}" to ${v.toUpperCase()}.` : `Cleared the effort of "${t.title}".`);
  };

  // Date: own dates, or (in People / Upcoming) the span, which may come from the parent or the subtasks (italic)
  const sp = t.span, inherited = useSpan && !date && sp && sp.how !== "own";
  const full = date ?? (useSpan ? sp && sp.label : t.when);
  const shown = !date && t.loose && (!useSpan || (sp && sp.how === "own")) ? "~" + t.loose : full;
  const rems = rem ? [rem] : t.reminders.map(r => "*" + r.spec);
  const content = [];
  if (rems.length) { const bell = icon(BELL, 12); content.push(bell); }
  content.push(shown ? span("t", shown) : ADD());
  if (t.overdue) content.push(span("sr", " (overdue)"));
  const tip = [full && (inherited ? `${full} (from its ${sp.how === "parent" ? "parent" : "subtasks"})` : full),
    t.overdue && "overdue", rems.length && "reminder " + rems.join(", "), "click to change"].filter(Boolean).join(" · ");
  const dateCell = cellButton("date r" + (t.overdue ? " late" : "") + (inherited ? " inh" : ""), "Set date", tip, content,
    cell => editCell(cell, "Oct24, Oct23--26, ~Q1, ~T1 (empty clears)", t.date_text, open.date.apply, false, false, tabber("date")));
  open.date = () => dateCell.click();
  open.date.apply = v => {
    v = v.trim();
    if (v === (t.date_text || "")) return;
    return editTask(t, "date", v, null, v ? `Set "${t.title}" to ${v}.` : `Cleared the date of "${t.title}".`);
  };

  const sub = cellButton("sub mid", "Add a subtask", "Add subtasks (Enter adds one and opens the next; Esc ends)", [ADD()],
    () => open.sub(""));
  open.sub = (initial = "") => editCell(sub, "new subtask, like  draft (KA) Oct24 (Esc ends)", initial, v => {
    v = v.trim();
    if (!v) return;
    const again = findAgain(row);
    editTask(t, "subtask", v, null, `Added "${v}" under "${t.title}".`)
      .then(ok => { const here = again(); if (here) here.open.sub(ok ? "" : v); });   // keep adding; refused: as typed
  }, true);

  if (week) {                                            // the Planner's backlog: a ☆ and a Plan cell instead of + (subtask)
    row.classList.add("wrow");
    lead.insertBefore(starButton(t, week), ttl);
    const unit = COLUMN_UNIT[week.column_kind];
    const plan = cellButton("plan r", "Plan", t.plan ? `Planned for ${t.plan_label}. Click to plan it for a ${unit} in ${week.label}`
      : `Plan it for a ${unit} in ${week.label}`, [t.plan ? span("t", t.plan_label) : span("add", "Plan")], cell => planPick(cell, t, week));
    row.append(lead, who, size, dateCell, plan, moreCell(t));
    return row;
  }
  row.append(lead, who, size, dateCell, sub, moreCell(t));
  return row;
}

/* ⋯ at the end of a task row: circle it in purple (notable), archive it (in a portfolio), or delete it */
function canArchive() {                          // a portfolio project's .kf page (not an archive), or All projects
  if (!state.folio) return false;
  if (state.all) return true;
  const p = state.file && state.file.path;
  return !!p && p.endsWith(".kf") && p.split("/")[1] !== "archive";
}
function archiveYears() {                        // this year and last year (the server's today)
  const y = +String(state.data.today).slice(0, 4);
  return [y, y - 1];
}
function moreCell(t) {
  const kids = countTasks(t.children || []);
  return cellButton("more mid", "More", "Circle in purple, archive or delete", [span("add", "⋯")], cell => {
    const choices = [{ value: "notable", text: t.notable ? "Remove the purple circle" : "Circle in purple" }];
    if (canArchive()) for (const y of archiveYears()) choices.push({ value: "archive:" + y, text: "Archive to " + y });
    choices.push({ value: "delete", text: kids ? `Delete, with ${tasksN(kids).replace("task", "subtask")}` : "Delete" });
    pickCell(cell, "Task", choices, null, v => {
      if (v === "notable") editTask(t, "notable", t.notable ? "" : "on", null, t.notable ? `Removed the purple circle from "${t.title}".` : `Circled "${t.title}" in purple.`);
      else if (v === "delete") {
        if (kids && !confirm(`Delete "${t.title}" and its ${tasksN(kids).replace("task", "subtask")}?`)) return;
        editTask(t, "delete", "", null, `Deleted "${t.title}"` + (kids ? ` and its ${tasksN(kids).replace("task", "subtask")}.` : "."));
      } else if (v && v.startsWith("archive:")) archiveOp({ line: t.line, title: t.title }, t, +v.slice(8));
    });
  });
}

/* Archive: the server moves the task (or every finished task) into the project's archive/YEAR.kf, writing the archive first.
   On a page, its unsaved edits are saved first and the text box then shows the file as the server left it.
   Undo puts both files back (each only if it hasn't changed since). */
async function archiveOp(body, target, year) {
  let path, version;
  if (state.all && target) { path = target.path; version = state.data.versions[path]; }
  else {
    const f = state.file;
    clearTimeout(autoTimer);
    while (f.saving) await new Promise(ok => setTimeout(ok, 50));
    if (unsaved() && !f.blocked) await save();
    if (unsaved() || f.blocked) { state.msg = { text: "Not archived: this page has changes that aren't saved yet.", bad: true }; return showToast(); }
    path = f.path; version = f.version;
  }
  const seq = ++state.seq;
  let res;
  try {
    const r = await fetch("/api/archive", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, path, version, archive_year: year, all: !!state.all, name: folioName(),
        today: $("today").value.trim() || null, period: state.period, planner: planFor() }) });
    res = await r.json();
    if (!r.ok) throw new Error(res.conflict ? "that project changed on disk; the view is up to date now, so try again" : res.error || r.statusText);
  } catch (err) {
    state.msg = { text: "Not archived: " + err.message, bad: true };
    if (state.file && !state.all) { const [r2, d2] = await fetchFile(state.file); if (r2.ok && !unsaved()) setFile(d2.text, d2.version); }
    return render(false);
  }
  state.folio = res.tree; drawDrawer();
  if (!state.all && state.file && state.file.path === path) setFile(res.text, res.version);
  if (seq !== state.seq) return;
  state.data = res.data;
  const what = body.habit_log ? `${year}'s habit ticks` : body.done ? tasksN(res.moved).replace(/^1 task$/, "1 finished task") : `"${body.title}"` + (res.moved > 1 ? ` and its ${tasksN(res.moved - 1).replace("task", "subtask")}` : "");
  state.msg = { text: `Archived ${what} to ${year}.`, undo: { files: res.undo } };
  plannerView();
}
const pts = n => n + (n === 1 ? " pt" : " pts");
const EFFORTS = [["xs", 1], ["s", 2], ["m", 3], ["l", 5], ["xl", 8]];   // the choices in the Effort cell (planner.py's EFFORT)
const sumPts = tasks => tasks.reduce((n, t) => n + t.points, 0);   // simple sum of what the server sent
const tasksN = n => n + (n === 1 ? " task" : " tasks");

function noteNode(text, depth) { return h("div", "note", ...guides(depth), span("pad"), text); }
const countTasks = list => list.reduce((n, c) => n + 1 + countTasks(c.children), 0);
function treeNode(t, depth = 0, key = "") {      // a task and its subtree; a task with subtasks folds (key: its path of titles)
  const row = taskNode(t, { depth });
  if (t.dim) { row.classList.add("dim"); row.title += " (shown because a subtask matches the filter)"; }
  key += "\n" + t.title;
  let shut = false;
  if (t.children.length && !filterOn()) {          // while searching or filtering, everything is open
    const set = foldSet("collapsedTasks"), n = countTasks(t.children);
    shut = set.has(key);
    const tog = h("button", "tog", icon(CHEVRON, 12));
    tog.title = shut ? `Show ${tasksN(n).replace("task", "subtask")}` : "Hide the subtasks";
    tog.setAttribute("aria-label", tog.title); tog.setAttribute("aria-expanded", String(!shut));
    tog.onclick = e => {
      e.stopPropagation();
      set[set.has(key) ? "delete" : "add"](key);
      store.set("collapsedTasks", JSON.stringify([...set]));
      plannerView();
    };
    row.prepend(tog);
    if (shut) { row.classList.add("shut"); row.querySelector(".lead").append(span("hidden-n", tasksN(n).replace("task", "subtask"))); }
  }
  return h("div", "", row, ...(shut ? [] : [...t.notes.map(n => noteNode(n, depth)), ...t.children.map(c => treeNode(c, depth + 1, key))]));
}
function colHead(title, when) {                  // a section heading that also labels the right-hand columns
  return h("div", "sechead", h("h2", "", title, when && span("when", when)),
    span("c r", "Who"), span("c mid", "Effort"), span("c r", "Date"), span("c", ""), span("c", ""));
}

/* folds, remembered per browser: in Projects, sections ("collapsedSections"), projects ("collapsed") and tasks with
   subtasks ("collapsedTasks", by section, project and the path of titles); in People, people ("collapsedPeople") */
const folds = {};
function foldSet(name) {
  if (!folds[name]) try { folds[name] = new Set(JSON.parse(store.get(name, "[]"))); } catch (e) { folds[name] = new Set(); }
  return folds[name];
}
const CHEVRON = "M9 6l6 6-6 6";
/* a heading that folds its rows away: returns [heading, shut]. While searching or filtering, everything is open. */
/* a fold button: returns [button, shut]. While searching or filtering, everything is open and the button is inactive. */
function foldButton(name, key, what, label) {
  const set = foldSet(name), open = filterOn(), shut = !open && set.has(key);
  const fold = h("button", "fold", icon(CHEVRON, 14), ...label);
  fold.setAttribute("aria-expanded", String(!shut));
  fold.title = open ? `${what[0].toUpperCase() + what.slice(1)}s stay open while a search or filter is on`
    : (shut ? "Show" : "Hide") + ` this ${what}'s tasks`;
  fold.disabled = open;
  fold.onclick = () => {
    set[set.has(key) ? "delete" : "add"](key);
    store.set(name, JSON.stringify([...set]));
    plannerView();
  };
  return [fold, shut];
}
function foldHead(name, key, what, label, count) {   // a project or person heading that folds its rows away
  const [fold, shut] = foldButton(name, key, what, label);
  return [h("h3", "ph" + (shut ? " shut" : ""), fold, count), shut];
}
/* All projects: one heading per project (its folder), which folds everything in it ("collapsedFolders"); inside, its
   tasks by section, and its @ sub-groups with their own fold. A project with no tasks yet still shows, with + Add task. */
function vAllProjects(d) {
  const out = h("div"), by = new Map(state.folio.projects.map(f => [f.name, []]));
  for (const sec of d.projects)
    for (const p of sec.projects) {
      const f = p.folder || p.name;
      if (!by.has(f)) by.set(f, []);
      by.get(f).push({ sec, p });
    }
  const add = (n, f) => n.reduce((a, x) => a + f(x), 0);
  for (const [folder, items] of by) {
    if (d.filtered && !items.length) continue;
    const ps = items.map(x => x.p), ptot = add(ps, p => p.points.total);
    const count = `${add(ps, p => p.done)}/${add(ps, p => p.total)} done` + (ptot ? ` · ${add(ps, p => p.points.left)} of ${pts(ptot)} left` : "");
    const [fold, shut] = foldButton("collapsedFolders", folder, "project", [folder]);
    const head = colHead(fold, null);
    head.classList.add("fhead");
    head.firstChild.append(span("when", count));
    const backlog = ps.find(p => p.path) || d.targets.find(t => t.folder === folder);
    if (canArchive() && add(ps, p => p.done) && !d.filtered && backlog)   // Archive done: the project's whole backlog
      head.firstChild.append(archiveDoneButton({ line: null, path: backlog.path }));
    out.append(head);
    if (shut) { head.classList.add("shut"); continue; }
    if (!items.length) {                          // no tasks yet: + Add task for the project itself
      const own = d.targets.find(t => t.folder === folder && t.name === folder);
      out.append(own ? addTaskRow(own) : h("div", "empty", "No tasks yet."));
      continue;
    }
    let lastSec = null;
    for (const { sec, p } of items) {
      if (sec.title && sec !== lastSec) out.append(h("div", "subsec", sec.title, sec.when ? span("when", sec.when) : null));
      lastSec = sec;
      const key = folder + "\n" + (sec.title || "") + "\n" + p.name;
      if (p.name !== folder) {                     // an @ sub-group: its own heading and fold
        const effort = p.points.total ? ` · ${p.points.left} of ${pts(p.points.total)} left` : "";
        const [ph, pshut] = foldHead("collapsed", key, "group", [span("at", "@"), p.name], span("count", p.done + "/" + p.total + " done" + effort));
        if (canArchive() && p.done && !d.filtered) ph.append(archiveDoneButton(p));
        out.append(ph);
        if (pshut) continue;
      }
      for (const n of p.notes) out.append(noteNode(n, 0));
      for (const t of p.tasks) out.append(treeNode(t, 0, key));
      out.append(addTaskRow(p));
    }
  }
  if (!out.children.length) out.append(d.filtered ? h("div", "empty", "No matching tasks.") : folioWelcome());
  return out;
}
function vProjects(d) {
  if (state.all && state.folio) return vAllProjects(d);
  const out = h("div");
  for (const sec of d.projects) {
    const [sfold, sshut] = foldButton("collapsedSections", sec.title || "", "section", [sec.title || "Projects"]);
    const head = colHead(sfold, sec.when);
    out.append(head);
    if (sshut) {                                   // folded: just the heading, with how many projects it holds
      head.classList.add("shut");
      head.firstChild.append(span("when", sec.projects.length + (sec.projects.length === 1 ? " project" : " projects")));
      continue;
    }
    for (const p of sec.projects) {
      const effort = p.points.total ? ` · ${p.points.left} of ${pts(p.points.total)} left` : "";
      const label = p.folder && p.folder !== p.name ? [span("at", p.folder + " · @"), p.name] : [span("at", "@"), p.name];
      const [head, shut] = foldHead("collapsed", (sec.title || "") + "\n" + (p.folder ? p.folder + "\n" : "") + p.name, "project", label,
        span("count", p.done + "/" + p.total + " done" + effort));
      if (canArchive() && p.done && !d.filtered) head.append(archiveDoneButton(p));
      out.append(head);
      if (shut) continue;
      for (const n of p.notes) out.append(noteNode(n, 0));
      for (const t of p.tasks) out.append(treeNode(t, 0, (sec.title || "") + "\n" + p.name));
      out.append(addTaskRow(p));
    }
  }
  if (!out.children.length) out.append(d.filtered ? h("div", "empty", "No matching tasks.") : welcome());
  return out;
}
function archiveDoneButton(p) {                  // a project heading's "Archive done": every finished task (and its subtasks)
  const b = h("button", "ghost archdone", "Archive done");
  b.title = "Move this project's finished tasks (done, with all their subtasks done) to the archive";
  b.onclick = e => {
    e.stopPropagation();
    pickCell(b, "Archive finished tasks to", archiveYears().map(y => ({ value: y, text: "Archive done to " + y })), null,
      y => archiveOp({ done: true, project_line: p.line || null }, p, y));   // (line null: the whole file)
  };
  return b;
}
function welcome() {                             // no notes yet
  if (state.folio) return folioWelcome();
  return h("div", "welcome", h("h2", "", editor.value.trim() ? "No projects or tasks found" : "No notes yet"),
    h("p", "", "Write tasks in Text mode, like  - finish proposal (KA) (m) Oct24"));
}

function vTimeline(d) {
  const tl = d.timeline, out = h("div");
  if (!tl.rows.length) out.append(h("div", "empty", d.filtered ? "Nothing scheduled matches." : "Nothing scheduled."));
  else {
    const head = h("tr", "", h("th", "", "Task"));
    for (const c of tl.columns) { const th = h("th", "m", c.head); th.title = c.start + " to " + c.end; head.append(th); }
    head.append(h("th", "", "When"));
    const table = h("table", "tl", head);
    for (const t of tl.rows) {
      const label = t.title + (t.assignees.length ? " (" + t.assignees.join(", ") + ")" : "");
      const nm = h("td", "name", h("span", "lead s-" + t.status, statusBox(t), span("proj", "@" + t.project), span("ttl", label)));
      nm.title = "@" + t.project + "  " + label;
      if (t.notable) nm.classList.add("notable");
      const tr = h("tr", t.status === "done" ? "done" : "", nm);
      tr.dataset.line = t.line;
      t.bar.forEach((on, i) => {
        const prev = t.bar[i - 1], next = t.bar[i + 1];
        const cell = h("i", on ? "on" : "");
        if (on && !prev) cell.classList.add("s");           // round only the bar's two ends
        if (on && !next) cell.classList.add("e");
        tr.append(h("td", "c", cell));
      });
      const w = h("td", "w" + (t.overdue ? " late" : ""), (t.loose && t.span.how === "own" ? "~" + t.loose : t.span.label) + (t.overdue ? " · overdue" : ""));
      w.title = t.span.label + (t.span.how === "parent" ? " (from its parent)" : t.span.how === "rollup" ? " (from its subtasks)" : "");
      if (t.span.how !== "own") w.style.fontStyle = "italic";
      tr.append(w);
      table.append(tr);
    }
    out.append(h("div", "tlwrap", table));
  }
  if (tl.unscheduled.length) {
    out.append(h("h4", "grp", "Unscheduled"));
    for (const t of tl.unscheduled) out.append(taskNode(t, { project: true }));
  }
  if (d.targets.length) out.append(addTaskRow(null));
  return out;
}

function vPeople(d) {
  const out = h("div");
  for (const g of d.people) {
    const effort = sumPts(g.tasks);                // the tasks shown, so it follows the filters
    if (!out.children.length) out.append(colHead("People"));
    const [head, shut] = foldHead("collapsedPeople", g.name, "person", [g.name],
      span("count", tasksN(g.tasks.length) + (effort ? ", " + pts(effort) : "")));
    out.append(head);
    if (shut) continue;
    for (const t of g.tasks) out.append(taskNode(t, { project: true, span: true }));
    out.append(addTaskRow(null, g.name === "(unassigned)" ? "" : g.name));
  }
  if (!d.people.length) out.append(h("div", "empty", d.filtered ? "No matching tasks." : "No open tasks."));
  if (!d.people.length && d.targets.length) out.append(addTaskRow(null));
  return out;
}

function vUpcoming(d) {
  const u = d.upcoming, out = h("div", "", colHead(`Next ${u.days} days`, "to " + u.horizon));
  const group = (title, items, row) => {          // empty groups are left out
    if (!items.length) return;
    out.append(h("h4", "grp", title));
    for (const t of items) out.append(row(t));
  };
  group("Overdue", u.overdue, t => taskNode(t, { project: true, span: true }));
  group("In progress", u.doing, t => taskNode(t, { project: true, span: true }));
  group("Due soon", u.due, t => taskNode(t, { project: true, span: true }));
  group("Reminders", u.reminders, t => taskNode(t, { project: true, date: t.date, rem: "*" + t.spec }));
  if (out.children.length === 1) out.append(h("div", "empty", d.filtered ? "Nothing matches in the next " + u.days + " days."
    : "Nothing due, overdue or in progress in the next " + u.days + " days."));
  if (d.targets.length) out.append(addTaskRow(null));
  return out;
}

/* ---------- Planner: plan tasks for a column (>Oct14 / >wk45 / >Nov / >T3 in the task's line, op "plan"), mark top
   priorities for the period (^wk45 / ^Nov / ^T3 / ^yr, op "priority"); the server groups them ---------- */
let dragged = null;                              // the task being dragged (this page only)
function inColumn(t, c, pl) {                    // is the task planned for this column (or a part of it)?
  return !!t.plan && PLAN_RANK[t.plan_kind] <= PLAN_RANK[pl.column_kind] && c.start <= t.plan && t.plan_end <= c.end;
}
function planPick(cell, t, pl) {                 // the column list (Mon … Sat/Sun, weeks, months, trimesters), and Unplan
  const here = pl.columns.find(c => inColumn(t, c, pl));
  const cols = pl.columns.filter(c => c.ok);
  pickCell(cell, "Plan for", [...cols.map(c => ({ value: c.token, text: c.head, note: c.today ? "now" : "" })),
    ...(t.plan ? [{ value: "", text: "Unplan", note: t.plan_label }] : [])], here ? here.token : null, v => planTask(t, v, pl));
}
function planTask(t, token, pl) {
  const col = pl.columns.find(c => c.token === token), was = pl.columns.find(c => inColumn(t, c, pl));
  if (token && col === was && t.plan_kind === pl.column_kind) return;
  if (col && !col.ok) return;
  editTask(t, "plan", token, null, !token ? `Unplanned "${t.title}".` : was ? `Moved "${t.title}" to ${col.head}.`
    : `Planned "${t.title}" for ${col.head}.`);
}
const STAR = { on: '<path d="M12 3.2l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6-4.4-4.2 6-.8z" fill="currentColor"/>',
  off: '<path d="M12 3.2l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6-4.4-4.2 6-.8z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' };
const starred = (t, pl) => t.priorities.some(p => p.kind === pl.star.kind && p.start === pl.star.start && p.end === pl.star.end);
function starButton(t, pl) {                     // ☆: a top priority for the period shown (^wk45, ^Nov, ^T3, ^yr)
  const on = starred(t, pl), b = h("button", "star" + (on ? " on" : ""));
  b.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">${on ? STAR.on : STAR.off}</svg>`;   // fixed markup
  b.title = on ? `Top priority for ${pl.label}. Click to unmark` : pl.star.ok ? `Make it a top priority for ${pl.label}`
    : pl.kind === "year" ? "Year priorities can be marked for this year only" : "Too far away to mark (the notes have no years)";
  b.setAttribute("aria-label", b.title); b.setAttribute("aria-pressed", String(on));
  b.disabled = !on && !pl.star.ok;
  b.onclick = e => {
    e.stopPropagation();
    editTask(t, "priority", (on ? "-" : "") + pl.star.token, b,
      on ? `"${t.title}" is no longer a top priority for ${pl.label}.` : `Made "${t.title}" a top priority for ${pl.label}.`);
  };
  return b;
}

/* The projects on the calendar (chips; remembered per browser as the ones taken off, "plannerHidden", so a new project
   shows up by itself). In a portfolio they are the project folders, otherwise the @ projects. */
const projKey = t => t.folder || t.project || t.name;
function planHidden() { try { return new Set(JSON.parse(store.get("plannerHidden", "[]"))); } catch (e) { return new Set(); } }
function setPlanHidden(set) { store.set("plannerHidden", JSON.stringify([...set])); plannerView(); }
function projectChips(d) {
  const names = state.folio && state.all ? state.folio.projects.map(p => p.name) : [...new Set(d.targets.map(t => t.name))];
  if (names.length < 2) return null;
  const hidden = planHidden(), shown = names.filter(n => !hidden.has(n)), off = names.filter(n => hidden.has(n));
  const chips = shown.map(n => {
    const x = h("button", "", "×");
    x.title = `Take ${n} off the calendar`; x.setAttribute("aria-label", x.title);
    x.onclick = () => { hidden.add(n); setPlanHidden(hidden); };
    return h("span", "pchip", span("", n), x);
  });
  const box = h("div", "pchips", span("plabel", "On the calendar"), ...chips);
  if (off.length) {
    const add = h("select", "", h("option", "", "+ Add project"), ...off.map(n => h("option", "", n)));
    add.firstChild.value = ""; [...add.options].slice(1).forEach((o, i) => { o.value = off[i]; });
    add.setAttribute("aria-label", "Add a project to the calendar");
    add.onchange = () => { if (add.value) { hidden.delete(add.value); setPlanHidden(hidden); } };
    box.append(add);
    if (off.length > 1) {
      const all = h("button", "ghost", "Show all");
      all.onclick = () => setPlanHidden(new Set());
      box.append(all);
    }
  }
  return box;
}
function draggable(el, t) {
  el.draggable = true;
  el.addEventListener("dragstart", e => { dragged = t; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", t.title); });
  el.addEventListener("dragend", () => { dragged = null; });
}
function dropZone(el, onDrop) {
  el.addEventListener("dragover", e => { if (!dragged) return; e.preventDefault(); el.classList.add("over"); });
  el.addEventListener("dragleave", e => { if (!el.contains(e.relatedTarget)) el.classList.remove("over"); });
  el.addEventListener("drop", e => { e.preventDefault(); el.classList.remove("over"); const t = dragged; dragged = null; if (t) onDrop(t); });
}
function weekItem(cls, t, w, extra) {           // a planned task: status, ☆, title (+ meta); a click opens the column list, drag moves it
  const body = h("span", "wbody", span("wt", t.title), ...extra);
  const el = h("div", cls + " s-" + t.status + (t.notable ? " notable" : ""), statusBox(t), starButton(t, w), body);
  el.dataset.line = t.line;
  el.title = projLabel({ name: t.project, folder: t.folder }) + "  " + t.title + (t.plan ? "  · planned " + t.plan_label : "") + "  (line " + t.line + ")";
  el.onclick = e => {
    if ($("viewPane").classList.contains("jump") || e.target.closest("button")) return;   // Edit alongside: the click jumps instead
    e.stopPropagation(); planPick(el, t, w);
  };
  draggable(el, t);
  return el;
}
/* ---------- Habits (a project's habits.kf): tasks with a frequency (*daily, *weekdays, *weekly Mon, Wed, *monthly 1st).
   Ticking a day writes it in the habit's log note (-- done Nov02 Nov03, op "tick"); a day not yet come can't be ticked. ---------- */
const TICK = { on: '<rect x="2.5" y="2.5" width="13" height="13" rx="3.5" fill="currentColor"/><path d="M5.6 9.3l2.2 2.2 4.6-4.8" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  off: '<rect x="3" y="3" width="12" height="12" rx="3.2" fill="none" stroke="currentColor" stroke-width="1.5"/>' };
function tickButton(t, day, due) {               // one habit on one day: ticked, to do (due), or extra (not due)
  const done = t.done.includes(day.date), b = h("button", "tick" + (done ? " on" : due ? " due" : " extra"));
  b.innerHTML = `<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">${done ? TICK.on : TICK.off}</svg>`;   // fixed markup
  b.title = `${t.title}, ${day.head}: ` + (done ? "done. Click to untick" : day.future ? "not yet" : due ? "due. Click when done" : "not due (click to tick anyway)");
  b.setAttribute("aria-label", b.title); b.setAttribute("aria-pressed", String(done));
  b.disabled = day.future && !done;
  b.onclick = e => {
    e.stopPropagation();
    editTask(t, "tick", (done ? "-" : "") + day.token, b, done ? `Unticked "${t.title}" for ${day.head}.` : `Ticked "${t.title}" for ${day.head}.`);
  };
  return b;
}
function habitsIn(pl, c, on) {                   // a Planner column's habits: ticks per day (Week), or how many were done
  const hs = (pl.habits || []).filter(on).filter(t => t.due.some(x => x >= c.start && x <= c.end) || t.done.some(x => x >= c.start && x <= c.end));
  if (!hs.length) return null;
  const box = h("div", "whab");
  if (pl.days.length) {
    for (const day of pl.days.filter(x => x.date >= c.start && x.date <= c.end))
      for (const t of hs) {
        const due = t.due.includes(day.date);
        if (!due && !t.done.includes(day.date)) continue;
        const row = h("div", "whrow", tickButton(t, day, due), span("wt", t.title), c.start !== c.end ? span("wd", day.head.split(" ")[0]) : null);
        row.title = projLabel({ name: t.project, folder: t.folder }) + " · " + (t.every_label || "");
        box.append(row);
      }
  } else {
    const due = hs.reduce((n, t) => n + t.due.filter(x => x >= c.start && x <= c.end).length, 0);
    const done = hs.reduce((n, t) => n + t.done.filter(x => x >= c.start && x <= c.end).length, 0);
    box.append(h("div", "whsum", `Habits: ${done} of ${due} done`));
    box.title = hs.map(t => t.title).join(", ");
  }
  return box.children.length ? box : null;
}
function vHabits(d) {
  const pl = d.planner, out = h("div", "habits");
  for (const y of pl.log_years) {               // last year's ticks: move them to the archive (on the user's click)
    const b = h("button", "", `Move ${y}'s ticks to the archive`);
    b.onclick = () => archiveOp({ habit_log: true }, null, y);
    out.append(h("div", "hbanner", span("", `Your habits still hold ticks from ${y}. `), b));
  }
  const table = h("div", "htable");
  table.style.setProperty("--ndays", pl.days.length);
  table.append(h("div", "hrow hhead", span("hname", "Habit"), span("hevery", "Every"),
    ...pl.days.map(x => span("hday" + (x.today ? " today" : ""), x.head)), span("hcount", "Done"), span("", "")));
  for (const t of pl.habits) {
    const row = h("div", "hrow s-" + t.status + (t.notable ? " notable" : ""));
    row.dataset.line = t.line; row.title = "line " + t.line;
    const name = span("hname", t.title);
    name.onclick = e => {                          // the habit's text, like a task's title (Edit alongside: jump instead)
      if ($("viewPane").classList.contains("jump")) return;
      e.stopPropagation();
      editCell(name, "habit, like  stretch (KA) *daily", t.text, v => { v = v.trim(); if (v && v !== t.text) editTask(t, "text", v, null, `Changed "${t.title}".`); }, false, true);
    };
    const every = cellButton("hevery", "How often", t.every.length ? `${t.every_label}. Click to change` : "Set how often it repeats",
      [t.every.length ? span("t", t.every_label) : span("add", "Set")],
      cell => editCell(cell, "daily, weekdays, weekly Mon, Wed, monthly 1st", t.every.join(", "),
        v => { v = v.trim(); if (v !== t.every.join(", ")) editTask(t, "every", v, null, v ? `"${t.title}" repeats ${v} now.` : `"${t.title}" doesn't repeat now.`); }, true));
    const due = pl.days.filter(x => t.due.includes(x.date) && !x.future).length;
    const done = pl.days.filter(x => t.done.includes(x.date)).length;
    row.append(name, every, ...pl.days.map(x => h("span", "hday" + (x.today ? " today" : ""), tickButton(t, x, t.due.includes(x.date)))),
      span("hcount", t.every.length ? `${done}/${due}` : ""), moreCell(t));
    table.append(row);
  }
  if (!pl.habits.length) table.append(h("div", "empty", "No habits yet: add one below, like  stretch  every  daily."));
  out.append(table);
  out.append(addHabitRow(d));
  return out;
}
function addHabitRow(d) {                        // + Add habit: a title and how often (the server writes the line)
  const own = d.targets[0], btn = h("button", "addtask", span("plus", "+"), "Add habit");
  btn.dataset.key = "habit";
  const row = h("div", "addrow", btn);
  btn.onclick = () => {
    const title = h("input"), every = h("input", "fevery"), list = h("datalist");
    title.type = every.type = "text"; title.placeholder = "new habit"; every.placeholder = "every: daily";
    title.setAttribute("aria-label", "New habit"); every.setAttribute("aria-label", "How often");
    list.id = "everyList";
    for (const v of ["daily", "weekdays", "weekly Mon", "weekly Mon, Wed, Fri", "weekly Sat", "monthly 1st"]) { const o = h("option"); o.value = v; list.append(o); }
    every.setAttribute("list", "everyList");
    const form = h("div", "addform", title, every, list);
    let closed = false;
    const cancel = () => { if (!closed) { closed = true; form.replaceWith(btn); } };
    form.addEventListener("focusout", () => setTimeout(() => { if (!form.contains(document.activeElement)) cancel(); }));
    form.onkeydown = e => {
      e.stopPropagation();
      if (e.key === "Escape") { cancel(); btn.focus(); }
      else if (e.key === "Enter") {
        e.preventDefault();
        const v = title.value.trim(), ev = every.value.trim();
        cancel();
        if (!v || !own) return;
        editTask({ line: own.line, title: own.name }, "task", ev ? { title: v, every: ev } : v, null, `Added the habit "${v}".`)
          .then(ok => { const again = plannerBody.querySelector('.addtask[data-key="habit"]'); if (again && ok) again.click(); });
      }
    };
    btn.replaceWith(form);
    title.focus();
  };
  return row;
}
/* starred (☆ for the period shown) first: in a list, and a backlog's starred task with its subtasks under it */
const starFirst = (tasks, pl) => [...tasks.filter(t => starred(t, pl)), ...tasks.filter(t => !starred(t, pl))];
function starBlocksFirst(items, pl) {
  const top = [], rest = [];
  for (let i = 0; i < items.length; i++) {
    const t = items[i];
    if (!starred(t, pl)) { rest.push(t); continue; }
    let j = i + 1;
    while (j < items.length && items[j].depth > t.depth) j++;
    for (const x of items.slice(i, j)) top.push({ ...x, depth: x.depth - t.depth });
    i = j - 1;
  }
  return [...top, ...rest];
}
const groupsStarFirst = (groups, pl) => [...groups.filter(g => g.tasks.some(t => starred(t, pl))), ...groups.filter(g => !g.tasks.some(t => starred(t, pl)))];
function vPlanner(d) {
  if (!d.targets.length && !d.filtered) return welcome();   // no notes yet
  const pl = d.planner, out = h("div"), hidden = planHidden(), on = t => !hidden.has(projKey(t));
  const unit = PLAN_UNIT[pl.kind], where = pl.current ? "this " + unit : pl.label;
  const chips = projectChips(d);
  if (chips) out.append(chips);
  const meta = t => span("wmeta", projLabel({ name: t.project, folder: t.folder }) + (t.effort ? " · " + t.effort.toUpperCase() : "")
    + (t.plan_kind !== pl.column_kind ? " · " + t.plan_label : ""));
  const prios = pl.priorities.filter(on);         // Top priorities for exactly this period
  const top = h("div", "wprio", h("h4", "grp", "Top priorities", span("when", " " + where)));
  if (prios.length) top.append(...prios.map(t => weekItem("wline", t, pl, [span("wd", projLabel({ name: t.project, folder: t.folder }))])));
  else top.append(h("div", "wempty", pl.star.ok ? `Mark a task with ☆ to make it a top priority for ${where}.`
    : pl.kind === "year" ? "Year priorities can be marked for this year only." : "Too far away to mark priorities (the notes have no years)."));
  out.append(top);
  const days = h("div", "wdays");
  days.style.setProperty("--ncols", pl.columns.length);   // the stylesheet stacks them in a narrow pane
  for (const c of pl.columns) {
    const col = h("div", "wday" + (c.today ? " today" : "") + (c.ok ? "" : " off"), h("div", "whead", c.head + (c.today ? " · now" : "")));
    col.title = c.ok ? `${c.start} to ${c.end}: plan with >${c.token}` : "Too far away to plan here (the notes have no years)";
    for (const t of starFirst(c.tasks.filter(on), pl)) col.append(weekItem("wcard", t, pl, [meta(t)]));
    const hab = habitsIn(pl, c, on);
    if (hab) col.append(hab);
    if (c.ok) dropZone(col, t => planTask(t, c.token, pl));
    days.append(col);
  }
  const side = h("div", "wside", h("h4", "grp", where[0].toUpperCase() + where.slice(1)));
  const groups = groupsStarFirst(pl.projects.filter(g => !hidden.has(projKey(g))), pl);
  for (const g of groups) {
    const total = sumPts(g.tasks), done = sumPts(g.tasks.filter(t => t.status === "done"));   // the tasks shown (follows the filters)
    const sum = h("div", "wsum", `${done}/${pts(total)}`);
    sum.title = `${pts(done)} done of ${pts(total)} planned`;
    side.append(h("div", "wproj", h("div", "wpname", projLabel(g)),
      ...starFirst(g.tasks, pl).map(t => { const c = pl.columns.find(x => inColumn(t, x, pl));
        return weekItem("wline", t, pl, [span("wd", c && t.plan_kind === pl.column_kind ? c.head.split(" ")[0] : t.plan_label)]); }),
      sum));
  }
  if (!groups.length) side.append(h("div", "wempty", d.filtered ? "Nothing planned matches." : "Nothing planned yet."));
  out.append(h("div", "wtop", days, side));
  const back = h("div", "wback", colHead("Backlog", `open tasks not planned for ${where}`));
  back.firstChild.classList.add("wrow");
  back.firstChild.children[4].textContent = "Plan";
  back.firstChild.children[4].classList.add("r");
  const bgroups = groupsStarFirst(pl.backlog.filter(g => !hidden.has(projKey(g))), pl);
  for (const g of bgroups) {
    back.append(h("h3", "ph", h("span", "", ...(g.folder && g.folder !== g.name ? [span("at", g.folder + " · @"), g.name] : [span("at", "@"), g.name]))));
    for (const t of starBlocksFirst(g.tasks, pl)) {   // drag by the title side (the row's inputs stay selectable)
      const row = taskNode(t, { depth: t.depth, week: pl });
      draggable(row.querySelector(".lead"), t);
      back.append(row);
    }
  }
  if (!bgroups.length) back.append(h("div", "empty", hidden.size && !groups.length && !bgroups.length ? "No projects on the calendar: add one above."
    : d.filtered ? "No matching open tasks." : `Every open task is planned for ${where}.`));
  dropZone(back, t => t.plan && planTask(t, "", pl));   // drop a planned task here to unplan it
  out.append(back);
  return out;
}

/* ---------- markdown (small, safe: everything is escaped before any tag is added) ---------- */
const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
function inline(s) {
  s = esc(s);
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (_, c) => "\u0000" + (codes.push("<code>" + c + "</code>") - 1) + "\u0000");
  s = s.replace(/!?\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
       .replace(/\*\*(.+?)\*\*|__(.+?)__/g, (_, a, b) => "<strong>" + (a || b) + "</strong>")
       .replace(/(^|[^\w*])\*([^*\s][^*]*?)\*(?!\w)|(^|[^\w_])_([^_\s][^_]*?)_(?!\w)/g,
                (m, p1, a, p2, b) => (p1 ?? p2) + "<em>" + (a || b) + "</em>")
       .replace(/~~(.+?)~~/g, "<del>$1</del>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[+i]);
}
function markdown(src) {
  const lines = src.replace(/\r\n?/g, "\n").split("\n"), out = [];
  let i = 0;
  const isBlock = l => /^(#{1,6}\s|```|>|\s*([-*+]|\d+\.)\s|(-{3,}|\*{3,})\s*$|\|)/.test(l);
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    let m;
    if (/^```/.test(l)) {
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push("<pre><code>" + esc(buf.join("\n")) + "</code></pre>");
    } else if ((m = /^(#{1,6})\s+(.*)$/.exec(l))) {
      out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`); i++;
    } else if (/^(-{3,}|\*{3,})\s*$/.test(l)) { out.push("<hr>"); i++; }
    else if (/^>/.test(l)) {
      const buf = [];
      while (i < lines.length && /^>/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
      out.push("<blockquote>" + markdown(buf.join("\n")) + "</blockquote>");
    } else if (/^\|/.test(l) && /^\|?\s*:?-+/.test(lines[i + 1] || "")) {
      const row = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      let t = "<table><tr>" + row(l).map(c => "<th>" + inline(c) + "</th>").join("") + "</tr>"; i += 2;
      while (i < lines.length && /^\|/.test(lines[i])) t += "<tr>" + row(lines[i++]).map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>";
      out.push(t + "</table>");
    } else if (/^\s*([-*+]|\d+\.)\s/.test(l)) {
      const items = [];
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s/.test(lines[i])) items.push(lines[i++]);
      out.push(list(items));
    } else {
      const buf = [];
      while (i < lines.length && lines[i].trim() && !(buf.length && isBlock(lines[i]))) buf.push(lines[i++]);
      out.push("<p>" + buf.map(inline).join("<br>") + "</p>");
    }
  }
  return out.join("\n");
}
function list(items) {                                  // nested by indent (tab = 4 spaces)
  const parse = l => { const m = /^(\s*)([-*+]|\d+\.)\s+(.*)$/.exec(l.replace(/\t/g, "    ")); return { d: m[1].length, ord: /\d/.test(m[2]), text: m[3] }; };
  const rows = items.map(parse);
  let pos = 0;
  function build(depth) {
    const ord = rows[pos].ord;
    const tasks = rows[pos] && /^\[[ xX]\]\s/.test(rows[pos].text);
    let html = `<${ord ? "ol" : "ul"}${tasks ? ' class="tasks"' : ""}>`;
    while (pos < rows.length && rows[pos].d >= depth) {
      if (rows[pos].d > depth) { html = html.replace(/<\/li>$/, "") + build(rows[pos].d) + "</li>"; continue; }
      let text = rows[pos++].text, box = "";
      const c = /^\[([ xX])\]\s+(.*)$/.exec(text);
      if (c) { box = `<input type="checkbox" disabled${c[1] === " " ? "" : " checked"}> `; text = c[2]; }
      html += "<li>" + box + inline(text) + "</li>";
    }
    return html + `</${ord ? "ol" : "ul"}>`;
  }
  return build(rows[0].d);
}

/* ---------- portfolio (python planner.py --serve: the Projects folder): the drawer, project pages and All projects ----------
   The logo opens a drawer: All projects (the views over every project's backlog), then the projects. A project
   shows its Quick note, Backlog, Notes (sections and pages, like OneNote), Habits and Archive. Each is a file in the
   project's folder, opened in the text box (autosaved, drafts, conflicts). All projects has no
   text box: the server reads every backlog and edits the task's own file (version-checked). The page shown last is
   remembered in "folioActive" ("" = All projects); open projects in "folioOpen". */
const FOLIO_FILES = [["quicknote", "Quick note", "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"],
  ["backlog", "Backlog", "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"]];
const HABITS_ICON = "M17 2l4 4-4 4M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v1a4 4 0 0 1-4 4H3";
const NOTES_ICON = "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5";
const ARCHIVE_ICON = "M21 8v13H3V8M1 3h22v5H1zM10 12h4";
const ALL_ICON = "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z";
const PLANNER_ICON = "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z";
/* Planner mode exists for a project's Backlog and its Archive, and Habits (its page of tick boxes is drawn in that mode).
   Everything else (the Quick note, notes pages) opens in Markdown if it is a .md, else in Text, with Planner greyed out. */
const pageHasPlanner = path => /^[^/]+\/(backlog\.kf|habits\.kf|archive\/\d{4}\.kf)$/.test(path);
const plannerOK = () => !state.folio || state.all || !state.file || pageHasPlanner(state.file.path);
const modeOf = path => pageHasPlanner(path) ? "planner" : /\.(md|markdown)$/i.test(path) ? "markdown" : "plain";
const extOf = p => ((/\.([^./]+)$/.exec(p) || [])[1] || "").toLowerCase();
const folioName = () => state.folio && state.file ? state.file.path.split("/")[0] : null;   // tasks before any @ belong to it
const archiveYear = () => {                       // an archive page's year: its dates are read in that year
  const m = state.folio && !state.all && state.file && /^[^/]+\/archive\/(\d{4})\.kf$/.exec(state.file.path);
  return m ? +m[1] : null;
};
const projLabel = p => (p.folder && p.folder !== p.name ? p.folder + " · " : "") + "@" + p.name;

const drawer = h("aside", "drawer"), scrim = h("div", "scrim"), dNav = h("nav", "dnav"), dQ = h("input");
const dClose = h("button", "ghost", "×"), dTitle = h("b"), dMenu = h("div", "menu dmenu hidden");
dQ.type = "search"; dQ.placeholder = "Find a project"; dQ.setAttribute("aria-label", "Find a project");
dClose.title = "Close (Esc)"; dClose.setAttribute("aria-label", dClose.title);
const dNew = h("button", "", "+ New project");
drawer.setAttribute("role", "dialog"); drawer.setAttribute("aria-label", "Projects");
drawer.append(h("div", "dhead", dTitle, dClose), h("label", "dsearch", icon("M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-3.5-3.5", 14), dQ),
  dNav, h("div", "dfoot", dNew));
document.body.append(scrim, drawer);
pops.push(open => { if (!open) { dMenu.classList.add("hidden"); const b = dMenu.parentNode && dMenu.parentNode.querySelector(".dmore"); if (b) b.setAttribute("aria-expanded", "false"); } });
function openDrawer(open = true) {
  document.body.classList.toggle("drawer-open", open);
  $("brand").setAttribute("aria-expanded", String(open));
  if (open) { drawDrawer(); dQ.focus(); } else closePops();
}
$("brand").onclick = () => state.folio && openDrawer(!document.body.classList.contains("drawer-open"));
scrim.onclick = () => openDrawer(false);
dClose.onclick = () => openDrawer(false);
dQ.oninput = () => drawDrawer();
dQ.onkeydown = e => { if (e.key === "Escape" && dQ.value) { e.stopPropagation(); dQ.value = ""; drawDrawer(); } };
dNew.onclick = () => ask(dNew.parentNode, "project name", "", 0, async v => {
  const path = await folioOp({ op: "project", name: v });
  foldSet("folioOpen").add(path); store.set("folioOpen", JSON.stringify([...foldSet("folioOpen")]));
  openPage(path + "/backlog.kf");
}, true);

async function folioOp(body) {                     // POST /api/portfolio; -> the new path (the tree is updated)
  const [r, d] = await fileApi(body, "/api/portfolio");
  if (!r.ok) throw new Error(d.error || r.statusText);
  state.folio = d.tree;
  return d.path;
}
async function refreshFolio() {                     // the folder may have changed outside the page
  try { const [r, d] = await fileApi(null, "/api/portfolio"); if (r.ok && d.name) state.folio = d; } catch (e) {}
}

/* a one-line form in the drawer (new or rename): Enter submits (a refusal is shown on the field), Esc or leaving cancels */
function ask(after, placeholder, initial, depth, submit, inside, suggest) {   // suggest: `initial` is a default, fine as it is
  const input = h("input"), form = h("form", "dask", input);
  input.type = "text"; input.placeholder = placeholder; input.value = initial; input.setAttribute("aria-label", placeholder);
  form.style.setProperty("--dd", depth);
  let busy = false;
  const cancel = () => { if (!busy && form.isConnected) { form.remove(); drawDrawer(); } };
  const submitIt = async () => {
    const v = input.value.trim();
    if (!v || (v === initial && !suggest)) return cancel();
    busy = true;
    try { await submit(v); busy = false; form.remove(); drawDrawer(); }
    catch (err) { busy = false; input.setCustomValidity(err.message); input.reportValidity(); }
  };
  form.onsubmit = e => { e.preventDefault(); submitIt(); };
  input.oninput = () => input.setCustomValidity("");
  input.onkeydown = e => {
    if (e.key === "Enter") { e.preventDefault(); submitIt(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
  };
  input.onblur = () => setTimeout(cancel, 150);
  if (inside) after.prepend(form); else after.after(form);
  input.focus(); input.select();
}

const isUnder = (path, dir) => path === dir || path.startsWith(dir + "/");
async function renameItem(path, row, depth) {
  const name = path.split("/").pop(), stem = extOf(name) ? name.slice(0, -extOf(name).length - 1) : name;
  ask(row, "new name", stem, depth, async v => {
    const f = state.file, here = f && isUnder(f.path, path);
    if (here) await leaveFile();
    const to = await folioOp({ op: "rename", path, name: v });
    const opened = foldSet("folioOpen");
    if (!path.includes("/") && opened.delete(path)) { opened.add(to); store.set("folioOpen", JSON.stringify([...opened])); }   // stays open
    if (here) {                                      // the shown page moved: follow it (and its draft)
      const next = to + f.path.slice(path.length), draft = store.get(draftKey(f.path), null);
      if (draft) { store.set(draftKey(next), draft); store.del(draftKey(f.path)); }
      f.path = next; f.name = baseName(next);
      store.set("folioActive", next);
      showFile();
    }
  });
}
async function trashItem(path, what) {
  if (!confirm(`Delete ${what} "${baseName(path)}"? It moves to the .trash folder in Projects, so you can get it back from there.`)) return;
  const here = state.file && isUnder(state.file.path, path);
  if (here) await leaveFile();
  try {
    await folioOp({ op: "trash", path });
    if (here) { store.del(draftKey(state.file.path)); state.file = null; await showAll(); }
    drawDrawer();
  } catch (e) { state.msg = { text: "Not deleted: " + e.message, bad: true, anyMode: true }; showToast(); }
}
function moreButton(row, items) {                   // ⋯ on a drawer row: a small menu (Rename, Delete, New page…)
  const b = h("button", "dmore", "⋯");
  b.title = "More"; b.setAttribute("aria-label", "More"); b.setAttribute("aria-haspopup", "menu"); b.setAttribute("aria-expanded", "false");
  b.onclick = e => {
    e.stopPropagation();
    const open = dMenu.parentNode === row && !dMenu.classList.contains("hidden");
    closePops();
    if (open) return;
    dMenu.replaceChildren(...items.map(([label, fn]) => { const m = h("button", "mi", label); m.onclick = ev => { ev.stopPropagation(); closePops(); fn(); }; return m; }));
    row.append(dMenu); dMenu.classList.remove("hidden"); b.setAttribute("aria-expanded", "true");
    dMenu.firstChild.focus();
  };
  return b;
}
function dRow(depth, iconPath, label, { active, go, more, type, chev, disabled, title } = {}) {
  const item = h("button", "ditem", ...(chev !== undefined ? [icon(CHEVRON, 12)] : []), iconPath ? icon(iconPath, 15) : null, span("", label),
    type ? span("type", type) : null);
  if (chev !== undefined) item.firstChild.classList.add("chev", ...(chev ? ["open"] : []));
  item.style.setProperty("--dd", depth);
  item.disabled = !!disabled;
  if (title) item.title = title;
  if (active) item.setAttribute("aria-current", "page");
  const row = h("div", "drow" + (active ? " on" : ""), item);
  if (more) row.append(moreButton(row, more(row)));
  item.onclick = go || (more ? e => { e.stopPropagation(); row.querySelector(".dmore").click(); } : null);   // no page: its menu
  return row;
}
function drawDrawer() {
  if (!state.folio) return;
  const f = state.folio, here = state.all ? "" : state.file ? state.file.path : null, q = dQ.value.trim().toLowerCase();
  const opened = foldSet("folioOpen");
  dTitle.textContent = f.name; dTitle.title = "Each folder in " + f.name + " is a project";
  const plan = state.all && state.tab === "planner";
  const toTab = tab => () => { state.tab = tab; store.set("tab", tab); showAll(); };
  const rows = [dRow(0, PLANNER_ICON, "Planner", { active: here === "" && plan, go: toTab("planner"), title: "Plan every project's tasks by year, season, month or week" }),
    dRow(0, ALL_ICON, "All projects", { active: here === "" && !plan, go: toTab(state.tab === "planner" ? "projects" : state.tab),
      title: "Every project's backlog together" }),
    h("div", "dlabel", "Projects")];
  for (const p of f.projects) {
    if (q && !p.name.toLowerCase().includes(q)) continue;
    const open = !!q || opened.has(p.name);
    const toggle = () => {
      opened[opened.has(p.name) ? "delete" : "add"](p.name);
      store.set("folioOpen", JSON.stringify([...opened]));
      drawDrawer();
    };
    const head = dRow(0, null, p.name, { chev: open, go: toggle, active: !open && here && isUnder(here, p.name),
      more: row => [["New page", () => newPage(p.name, null, row, 1)], ["New section", () => newSection(p.name, row)],
        ["Rename", () => renameItem(p.path, row, 0)], ["Delete", () => trashItem(p.path, "the project")]] });
    rows.push(head);
    if (!open) continue;
    for (const [key, label, ic] of FOLIO_FILES)
      rows.push(dRow(1, ic, label, { active: here === p.files[key], go: () => openPage(p.files[key]) }));
    rows.push(dRow(1, NOTES_ICON, "Notes", { title: p.notes.length ? "Pages and sections" : "No pages yet: click to add one",
      more: row => [["New page", () => newPage(p.name, null, row, 2)], ["New section", () => newSection(p.name, row)]] }));
    for (const n of p.notes) {
      if (n.kind === "section") {
        rows.push(dRow(2, FOLDER, n.name, { title: n.path,
          more: row => [["New page here", () => newPage(p.name, n.name, row, 3)], ["Rename", () => renameItem(n.path, row, 2)],
            ["Delete", () => trashItem(n.path, "the section")]] }));
        for (const pg of n.pages) rows.push(pageRow(pg, 3, here));
      } else rows.push(pageRow(n, 2, here));
    }
    rows.push(dRow(1, HABITS_ICON, "Habits", { active: here === p.files.habits, go: () => openPage(p.files.habits),
      title: "Repeating tasks (habits.kf)" }));
    if (p.archive.length) {
      rows.push(dRow(1, ARCHIVE_ICON, "Archive", { disabled: true }));
      for (const a of p.archive) rows.push(dRow(2, null, String(a.year), { active: here === a.path, go: () => openPage(a.path) }));
    } else rows.push(dRow(1, ARCHIVE_ICON, "Archive", { disabled: true, title: "Nothing archived yet" }));
  }
  if (!f.projects.length) rows.push(h("div", "empty", "No projects yet."));
  else if (q && rows.length === 2) rows.push(h("div", "empty", "No project matches."));
  dNav.replaceChildren(...rows);
}
function pageRow(pg, depth, here) {
  return dRow(depth, DOC, pg.name, { active: here === pg.path, go: () => openPage(pg.path), type: pg.type === "kf" ? "" : pg.type,
    title: pg.file, more: row => [["Rename", () => renameItem(pg.path, row, depth)], ["Delete", () => trashItem(pg.path, "the page")]] });
}
function newPage(project, section, row, depth) {
  ask(row, "page name (ends .kf, or .md / .txt)", "", depth, async v => {
    const path = await folioOp({ op: "page", project, name: v, section });
    openPage(path);
  });
}
function newSection(project, row) {
  ask(row, "section name", "", 2, async v => { await folioOp({ op: "section", project, name: v }); });
}

function inTree(path) {                              // is this page still in the portfolio? (for "folioActive")
  const parts = path.split("/"), p = state.folio.projects.find(x => x.name === parts[0]);
  if (!p) return false;
  if (Object.values(p.files).includes(path)) return true;
  if (p.archive.some(a => a.path === path)) return true;
  return p.notes.some(n => n.path === path || (n.pages || []).some(pg => pg.path === path));
}
async function startPortfolio(tree) {
  state.folio = tree;
  $("brand").disabled = false; $("brand").title = "Projects and pages";
  const last = store.get("folioActive", "");
  if (last && inTree(last)) await openPage(last); else await showAll();
  if (!last && !tree.projects.length) openDrawer(true);
}
async function openPage(path) {                      // show one of a project's files in the text box (autosaved)
  await leaveFile();
  let r, d;
  try { [r, d] = await fileApi(null, "/api/file?path=" + encodeURIComponent(path)); }
  catch (e) { r = { ok: false }; d = { error: "can't reach the planner server" }; }
  if (!r.ok) {
    state.msg = { text: "Can't open " + baseName(path) + ": " + (d.notOpen ? "it isn't in the portfolio any more" : d.error), bad: true, anyMode: true };
    await refreshFolio(); drawDrawer();
    return showToast();
  }
  state.all = false;
  state.mode = modeOf(path); store.set("mode", state.mode);
  store.set("folioActive", path);
  useFile(d);
  layout();
  openDrawer(false);
  drawDrawer();
}
async function showAll() {                           // All projects: every backlog together, no text box
  await leaveFile();
  state.file = null; state.all = true; state.switched = true; state.msg = null; clearTimeout(autoTimer);
  editor.value = "";
  store.set("folioActive", "");
  openDrawer(false);
  showFile();
  render(true);
  drawDrawer();
}
function showCrumbs() {                              // the header: Project › Notes › Section › Page (click: the drawer)
  const c = $("crumbs");
  c.classList.toggle("hidden", !state.folio);
  if (!state.folio) return;
  let parts;
  if (state.all || !state.file) parts = [state.tab === "planner" ? "Planner" : "All projects"];
  else {
    const [proj, kind, ...rest] = state.file.path.split("/");
    const named = { "backlog.kf": "Backlog", "quicknote.kf": "Quick note", "habits.kf": "Habits" }[kind];
    const strip = n => extOf(n) === "kf" ? n.slice(0, -3) : n;
    parts = named ? [proj, named] : kind === "notes" ? [proj, "Notes", ...rest.slice(0, -1), strip(rest[rest.length - 1])]
      : [proj, "Archive", rest[0].slice(0, 4)];
  }
  const kids = [];
  parts.forEach((t, i) => {
    if (i) kids.push(span("sep", "›"));
    kids.push(i === parts.length - 1 ? h("b", "", t) : span("", t));
  });
  c.replaceChildren(...kids);
  c.title = (state.file ? state.file.path : parts[0]) + " (click for the projects)";
  c.onclick = () => openDrawer(true);
}
function folioWelcome() {                            // an empty page, or All projects with no tasks yet
  const out = h("div", "welcome");
  if (state.all) {
    const any = state.folio.projects.length;
    out.append(h("h2", "", any ? "No tasks yet" : "No projects yet"),
      h("p", "", any ? "Add the first one, or open a project's Backlog from the drawer (click the logo)." : "Start one from the drawer."));
    if (any && state.data.targets.length) out.append(addTaskRow(null));
    else { const b = h("button", "", "Open the drawer"); b.onclick = () => openDrawer(true); out.append(b); }
    return out;
  }
  out.append(h("h2", "", editor.value.trim() ? "No tasks here" : "Nothing here yet"),
    h("p", "", "Add a task, or write in Text mode, like  - finish proposal (KA) (m) Oct24"));
  const own = state.data.targets[0];
  if (own) out.append(addTaskRow(own));
  return out;
}

/* ---------- start ---------- */
if (!["plain", "planner", "markdown"].includes(state.mode)) state.mode = "plain";
render(true);
startFileMode();
