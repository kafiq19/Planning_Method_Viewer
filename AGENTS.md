# AGENTS.md

Instructions for AI agents (and developers) working in this repo. Human-facing docs live in `README.md`. This file is the **normative spec**: if the code and this file disagree, fix one of them so they match, and say which one you changed.

## What this repo is

`planner.py` parses a plain-text planning-notes format and prints four views: `projects`, `timeline`, `people` and `upcoming`. `planner.py` uses only the Python standard library (3.8+). It also serves a small web page (`web/index.html`) with `--serve`. `example.txt` is the reference input and exercises every rule.

## Ground rules

1. **The note format belongs to the user.** It is a light layer over how they already write notes. Do not add, rename or repurpose markers unless the user asks. Propose format changes in plain words first.
2. **Keep it stdlib-only.** No `pip` dependencies, in Python or in the page (no CDN scripts, no JS libraries). Parsing lives only in `planner.py`; the page never re-implements the note format, it asks the server. Keep the repo small: `planner.py`, `web/index.html`, `test_planner.py`, the docs, `changelog.txt` and the example.
3. **Parsing never changes the notes.** The tool edits them only on an explicit user action (clicking a task's status box, or its date / size / +who / +sub actions, or + Add task). An edit touches only its target line and only the characters it must; adding a subtask or task inserts one new line and changes no existing line (except giving a final line with no line ending one). Wording, order, indentation, trailing whitespace and line endings stay exactly as they were. An edit made from an out-of-date view is refused, not guessed at. When you edit or generate notes for the user, follow the grammar below exactly and preserve the same things.
4. **Keep `README.md` (humans), this file (machines) and the docstring at the top of `planner.py` in sync** whenever behaviour changes, and add an entry at the top of `changelog.txt` (current series: 1.2.x; bump the patch number for each change unless the user picks another version). A new view or field must reach `to_data` and `web/index.html` as well as the CLI.
5. **Verify every change** by running the commands in [Testing](#testing).

---

## Format specification

### Lexical

- Input is UTF-8 text, processed line by line. Blank or whitespace-only lines are ignored.
- **Indent level** = (number of `\t` in leading whitespace) + floor(number of spaces in leading whitespace / 4).
- `content` = the line with leading and trailing whitespace stripped.

### Line classification

Rules are checked **in this order**, and the first match wins:

| # | Condition on `content` | Kind | Effect |
|---|---|---|---|
| 1 | starts with `@` | **project** | New project named `content[1:].strip()`, inside the current section. Clears the task stack. |
| 2 | starts with `--` | **note** | Appended to the most recent task (top of the stack). If there is none, it attaches to the current project. Indent is ignored. |
| 3 | matches `^([!~]?)-\s*(.*)$` | **task** | Status: `!` = done, `~` = doing, none = open. Parent = nearest earlier task on the stack with a strictly lower indent level. |
| 4 | indent level == 0 | **heading** (section) | New section. Its text is parsed for dates the same way tasks are. Clears the current project and the task stack. |
| 5 | otherwise (indented free text) | **note** | Same as rule 2. |

A task that appears before any `@` line goes into an implicit project named `(no project)`.

### Inline tokens (tasks and headings)

These are extracted in this order. Each token is removed from the text, and whatever remains (whitespace collapsed) is the title.

| Token | Regex (MON = `Jan\|Feb\|…\|Dec`, case-sensitive) | Field |
|---|---|---|
| Effort | `(?<!\w)\(\s*(xs\|s\|m\|l\|xl)\s*\)` (lowercase only) | `effort` (`xs`/`s`/`m`/`l`/`xl`) and `points` (1/1/3/5/8, `EFFORT`) (first match only) |
| Assignees | `\(\s*([A-Z]{1,4}(?:\s*,\s*[A-Z]{1,4})*)\s*\)` | `assignees` (all matches) |
| Reminder | `\*(daily\|weekly\s+[A-Za-z]{3}[a-z]*\|monthly\s+\d{1,2}(?:st\|nd\|rd\|th)?\|MON\d{1,2})\b` | `reminders` (all matches) |
| Range | `(?<![\w*~])(MON)(\d{1,2})--(MON)?(\d{1,2})\b` | `start`, `end` (first match only) |
| Loose date | `(?<!\S)~(Q[1-4]\|wk\d{1,2}\|MON)\b` | `start`, `end`, `loose` (only if no range was found) |
| Date | `(?<![\w*~])(MON)(\d{1,2})\b` | `start = end` (only if neither of the above was found) |

Each task has at most one date span and at most one effort. Later date or effort tokens on the same line stay in the title. Effort is taken first, so removing initials can't glue it to a word; `file(s)` (no space before) is not effort, and `(S)` / `(XL)` are initials.

### Date resolution (no years are ever written)

`TODAY` defaults to `date.today()`. Set it with `--today Oct12` or `--today 2026-10-12`. Set `PAST_DAYS = 90`.

- **Single date `MonDD`:** the unique year *y* in {TODAY.year−1, TODAY.year, TODAY.year+1} such that `TODAY − 90d ≤ date < TODAY − 90d + 365d`. If no valid date exists (for example `Feb30`), the token is ignored and stays in the title.
- **Range end:** the first occurrence of the end month and day **on or after** the resolved start. If the end month is omitted, it is the start month. `Dec15--Jan10` crosses the year correctly.
- **Loose `~Q1` / `~Nov` / `~wkNN`:** the earliest candidate period (quarter, calendar month or ISO week Mon–Sun), across those three years, whose end is `≥ TODAY − 90d`.
- **One-off reminder `*MonDD`:** resolved like a single date. Its next-fire date is `None` if it is before TODAY.
- **Repeating reminders:** `daily` fires TODAY. `weekly Ddd` fires on the next matching weekday, which can be TODAY. `monthly N` fires on the next day N that is ≥ TODAY, skipping months that don't have that day.

### Derived semantics

- `rollup(task)` = (min start, max end) over the task and all its dated descendants.
- `span(task)`:
  1. If the task has its own dates, return `rollup` and mark it `own`. This means a parent's span **stretches** to cover its children.
  2. Otherwise, if any descendant is dated, return `rollup` and mark it `rollup`.
  3. Otherwise, return the own dates of the nearest dated ancestor and mark it `parent` (inherited).
  4. Otherwise, return `None`, which means the task is **unscheduled**.
- **Overdue** = status ≠ done, and span is not `None`, and span end < TODAY.
- **Assignees are not inherited.**
- **Effort is not inherited and does not roll up.** A task without its own token has 0 points. `effort_points(tasks)` = (points of tasks not done, all points), a simple sum of each task's own points. Projects show it over all their tasks (ignoring the period, like the done count); people show the not-done sum of their listed tasks.
- Section (heading) dates are display-only. Tasks do not inherit them.

### Valid-note checklist (for agents writing notes)

- Every task line starts with `- `, `~- ` or `!- ` after its indentation.
- Subtasks are indented exactly one more tab than their parent.
- Notes start with `-- ` and go directly under the task they describe.
- Dates are `MonDD` with no space (`Oct24`, `Nov03`). Ranges are `Oct23--26` or `Oct23--Nov03`. Loose dates are `~Q1`, `~Nov` or `~wk43`.
- Initials go in parentheses: `(KA)` or `(KA, RT)`.
- Effort is `(xs)`, `(s)`, `(m)`, `(l)` or `(xl)`, lowercase, with a space before it. Write it after the initials and before the date: `finish proposal (KA) (m) Oct24`.
- Never write years. Never put free text at the left edge unless it is meant to be a heading.

---

## Code map (`planner.py`)

| Symbol | Role |
|---|---|
| `RE_*` constants | Token regexes from the table above |
| `PAST_DAYS`, `UPCOMING_DAYS` | Date window (90) and look-ahead for `upcoming` (14) |
| `EFFORT`, `effort_points`, `pts` | Effort size → points (`xs` 1, `s` 1, `m` 3, `l` 5, `xl` 8); `(not-done points, all points)` over some tasks; `"3 pts"` formatting |
| `resolve`, `resolve_after`, `loose_span`, `next_reminder` | Date resolution |
| `fd`, `fspan` | Date formatting. The year is shown only when it isn't TODAY's year. |
| `timeline_months`, `timeline_rows`, `people_groups`, `upcoming_groups` | Shared collectors: the text views and `to_data` both use them, so the logic exists once |
| `Task` | Parsed task (headings reuse it). `line` is its 1-based line in the source text, counting blank lines, and `col` is where the text after the dash starts in that line. `_parse` extracts tokens into `effort` / `points` (`None` / 0 without one), `assignees`, `reminders` and the dates, and records where each sat in `at` (`effort`, `assignees`, `reminders`, `date`: spans relative to `col`) plus the date token's original text in `date_text`. `walk`, `rollup`, `span`, `overdue` and `label` derive the rest. |
| `Project` | Name, section, `line` (its `@` line; for the implicit `(no project)`, its first line), root tasks and notes |
| `parse(text)` | Line classifier and stack builder. Returns `list[Project]`. |
| `view_projects`, `view_timeline`, `view_people`, `view_upcoming` | Each returns `list[str]`. Projects and People show a task's effort as `[M]` after its title; the project line adds `N of M pts left`, a person's line `, N pts`. |
| `SEASONS`, `period_from`, `period_range`, `period_at`, `period_step`, `period_label`, `period_columns` | The page's Month / Season picker. Seasons are Winter Jan-Apr, Summer May-Aug, Fall Sep-Dec (inclusive). A period is `(kind, year, index)`: month index 1-12, season index 0-2. `period_from` validates a request's `{kind, year, index}` (with only `kind`, it returns the period containing TODAY). `period_columns` gives the timeline columns: the 4 months of a season, or the Mon-Sun weeks of a month, cut to the month. |
| `task_data(t, keep)`, `flat`, `to_data(projects, period)` | JSON-ready dicts of all four views, for the web page. Every task carries `line`, `effort`, `points` and `loose` (the loose-date token, like `Q1`, or `null`); each project has `line` and `points: {left, total}`, `targets` lists every project (`{name, line, section}`, unfiltered, for the page's project picker) and each people group `points` (not-done sum of its tasks). With `keep`, `task_data` drops tasks that aren't kept and have no kept subtasks, and marks kept-for-context ancestors `dim`. With a period, `to_data` shows only tasks whose span overlaps it in Projects (projects and sections with none are dropped), Timeline (columns = the period; Unscheduled is empty) and People; Upcoming is unchanged. It adds `period: {kind, year, index, label, short, start, end, current, prev, next, now}` (`label` is `Fall 2026 (Sep-Dec)`, `short` is `Fall 2026`) (`null` without one); `prev`, `next` and `now` are `{kind, year, index, label}` with a short label (`Summer 2026`), and `current` says whether this is the period containing TODAY. `timeline.columns` is `[{head, start, end}]` in both cases. |
| `EditError`, `_task_at`, `EDITS` | Edits, all `f(text, line, value, title=None) -> text`. Each raises `EditError` if the line isn't a task, `title` doesn't match its parsed title (stale view) or the value is invalid, and re-parses its result to check it reads back as intended. `EDITS` maps the `/api/edit` op names to them. |
| `set_status` (op `status`) | Swaps the `!`/`~` mark before the dash (`STATUS_MARK`). |
| `set_effort` (op `effort`) | Replaces the task's effort token in place; if it has none, inserts `(size)` before the first date or reminder token, or at the end; an empty value removes the token and the spaces before it. Takes `xs`, `s`, `m`, `l`, `xl` in any case, with or without parentheses, and writes them lowercase. Refused if the title or dates would read back differently. |
| `set_date` (op `date`) | Replaces the task's own date token in place; if it has none, inserts one before the first reminder or at the end of the line; an empty value removes the token and the spaces before it. Refused if the result wouldn't resolve to that date (for example an earlier invalid `Feb30` takes priority). |
| `set_assignees` (op `who`) | Replaces the task's initials: the first `(...)` group takes the new list in place and later groups are removed with the spaces before them; empty removes them all (refused if there are none). With no group yet it adds one as `add_assignees` does. Takes `KA, RT` or `KA RT`; duplicates are dropped (`_initials`). |
| `add_assignees` (op `assign`) | Adds initials (`RT` or `RT, JS`) to the last `(...)` group, or inserts a new group before the first effort, date or reminder token (`finish proposal (KA) (m) Oct24`), or at the end. Skips initials already there. |
| `add_task` (op `task`) | `line` is the project's `line` and `title` its name. Inserts `- value` as the project's last top-level task: after its last line (tasks and notes, before blank lines, the next `@` or a heading), indented like its first task, with the `@` line's line ending. |
| `add_subtask` (op `subtask`) | Inserts `- value` as the last subtask: after the task's last subtree line (subtasks and their notes, before blank lines), one tab deeper (4 spaces if the parent is indented with spaces only), with the parent line's line ending. |
| `FileConflict`, `file_version`, `read_notes`, `write_notes` | The notes file for `--serve notes.txt`. A version is the SHA-256 of the file's bytes (`None` = no file yet). `read_notes` returns the exact text (no newline translation). `write_notes` refuses with `FileConflict` unless the file is still at the given version (or `force`), restores `\r\n` endings if the file used them throughout (browsers send `\n`), writes atomically (temp file + rename) and keeps the file's permissions. |
| `set_today`, `make_server(port, notes_path, browse_root)`, `serve(port, notes_path)` | `make_server` builds a `127.0.0.1`-only `http.server` (port 0 = any free port, used by the tests); `serve` runs it and opens the browser. Every `/api/*` request must have a `localhost:PORT`/`127.0.0.1:PORT` `Host` and, if it sends one, a matching `Origin` (else 403), and POSTs must be `application/json` (else 415), so other websites can't use the API. `GET /` returns `web/index.html`. `GET /api/file` returns `{name, text, version}` (`{name: null}` without a file). `GET /api/example` returns `{text}`, the contents of `example.txt` (read-only, for the page's "Load the example"). Without a command-line file: `GET /api/browse?dir=` returns `{dir, home, parent, entries: [{name, kind: dir|file, path}]}` (no dot-files; only `.txt`, `.md`, `.markdown` files; `NOTE_SUFFIXES`), and `POST /api/open {path}` opens such a file (or `{path: null}` closes it); both refuse paths outside `browse_root` (default the home folder, resolved, so `..` and symlinks can't escape) with 403, and answer 409 when a file was given on the command line. `GET /api/file` then also returns `path` and `picked`. `POST /api/file` takes `{text, version, force}` and returns `{version}`, or 409 `{conflict: true, version}` if the file changed on disk. Only the open file (the command-line `notes_path`, or the one opened with `/api/open`) can ever be written; besides it, only `example.txt` is read. `POST /api/parse` takes `{text, today, period}` and returns `to_data`. `POST /api/edit` takes `{text, line, title, op, value, today, period}` (op: `status`, `date`, `effort`, `assign`, `who`, `subtask`, `task`) and returns `{text, data}` (the new text and its `to_data`); 409 if the edit is refused, 400 if the request is malformed. `TODAY` is reset on every request. |
| `VIEWS`, `take_option`, `main` | CLI: an optional file path, view names (any case), `--today`, and `--serve [notes.txt] [--port N]` (default 8765; the file may not exist yet, but its folder must, and a symlink is resolved to its target). Reads stdin when no path is given. Bad arguments (unknown view or missing file, two files, a missing or invalid `--today`/`--port`) exit with code 1 and a one-line `planner.py: …` message, never a traceback. |

## Web page (`web/index.html`)

One self-contained file (inline CSS and JS, no dependencies; icons are inline SVG). The app's name is **KAFEEN Planner**: page title, favicon (an inline SVG data URI) and the header's brand (a logo mark of three timeline bars in an accent-coloured rounded square, "KAFEEN" in heavy spaced capitals, "Planner" in muted text). **Header:** the brand, the file name in file mode, "Saved" or a **• Unsaved · Save** pill (shown only when there is something to save), the mode switch (**Text / Planner / Markdown**; the stored mode value for Text is still `plain`), and a **⋯** menu with Open file (hidden in file mode), Save (Ctrl/⌘-S; a download without a file), Edit alongside, Dark/Light mode ("follows system" until chosen), **Text size** and **Font**, and Today (Planner mode only). **Text size** is four "A" buttons (`SIZES`: Small 0.9, Default 1, Large 1.15, Larger 1.3) that set the CSS variable `--fz`; every font size, the Who / Effort / Date column widths and the row height in the views' styles (from `.context` and the planner-views block through Markdown) are `calc(Npx * var(--fz))`, and the text editor's size follows it too. The header and the tool row keep their size. **Font** is a select of six installed-font stacks (`FONTS`: System, Rounded, Serif, Legible, Condensed, Monospace; no downloaded fonts, rule 2) that sets `--vfont` on `.content` and `.md`; the text editor stays monospace so tab indents line up. `applyText` applies both; they are remembered in `localStorage` keys `textSize` and `font`. Keep it to at most seven choices each. Pop-up menus (`popup`, `closePops`) open one at a time and close on a click outside or Esc. Three modes:

- **Text** (mode `plain`): editable text area only; text is never changed. Tab indents (Shift-Tab outdents) because the format is tab-based.
- **Planner:** the four views as tabs, drawn from `/api/parse`. Views are plain lists on one page (no cards): section headings label the right-hand **Who / Effort / Date** columns, projects and people are headings with their counts (in the Projects tab a project heading is a fold button: its tasks and notes hide and show, remembered in `localStorage` key `collapsed` by section + project name; while `filterOn()` everything is open and the buttons are inactive), subtasks keep a faint guide line per level, and colour is kept for meaning only (status, red for overdue, the effort badge). Rows are compact (about 28px) in a content column up to 900px wide, with fixed columns Who 76px, Effort 44px, Date 172px and a 22px **+** column. Each row is `taskNode(t, {project, span, depth, date, rem})`; a reminder is a bell icon before the date (the rule on hover). A loose date shows as its token (`~Q1`, from the task's `loose`) with the full range on hover; a date taken from the parent or the subtasks is shown in italics, with where it came from on hover. When the pane is under 480px wide (a CSS container query on `.content`, so it applies to Edit alongside as well as phones), a task's details move onto a line under its title, indented to the title (`--d` = depth), and empty cells take no room. Upcoming leaves out empty groups. The Timeline's task column stays put when the table scrolls sideways. Clicking a task's status circle (drawn as inline SVG: a ring for open, half-filled for in progress, filled with a check for done; `MARK`) in any tab, including timeline rows, cycles open → in progress → done → open through `/api/edit`. The page swaps in only the changed characters, so the cursor and scroll in the side editor stay put, and shows a toast at the bottom of the window (`showToast`) with **Undo** (which works while the text is unchanged since) and × to dismiss; it never moves the layout. If the user typed while the request was out, the edit is dropped. There are no hover menus: in task rows (not timeline rows) the **Who**, **Effort** and **Date** cells and the **+** cell are buttons (`cellButton`). Clicking Effort opens a single-choice list under the cell (`pickCell`: XS, S, M, L, XL with their points from the page's `EFFORTS`, and None; the current one is ticked and focused; arrows move, Enter or a click picks, Esc, Tab or a click outside cancels) that sets or clears the effort (op `effort`). Clicking any other opens a one-line input over the cell's line, right-aligned to the cell but kept inside the row so a narrow pane never pushes it off the left edge (`editCell`; Enter applies, Esc or leaving cancels): Who replaces the initials (op `who`; it starts with the current ones and empty removes them), Date sets or clears the own date (`date`; it starts with `date_text`), and **+** adds a subtask (`subtask`). **+ Add task** (`addTaskRow`, `openAdd`) adds a top-level task (op `task`): at the end of each project in Projects; under each person in People, prefilled with ` (KA)` and the cursor before it; at the bottom of Timeline and Upcoming (and People when it has no one). Outside Projects the form has a project picker from `targets` (default: the Filter's project, then the last one used, `localStorage` key `addTo`, then the first). Empty cells show a faint **+** while the pointer is on the row (always on touch screens). Every edit gets the same toast and Undo. Nothing else in the views edits text. **Effort** is shown minimally: a small deep-purple `XS`/`S`/`M`/`L`/`XL` badge (`--effort`, white text) in the Effort column (tooltip `effort: 3 pts`), `· N of M pts left` next to each project heading (from `points`), and `, N pts` next to each person, summed in the page from the listed tasks' `points` so it follows the filters (plain addition of a server field, not parsing).
- **Tool row** (sticky at the top of the Planner pane): the four tabs, then search, **Filter** and the period control. Below it, a quiet context line (`contextLine`) appears only when it has something to say: "As of Oct 12" when Today is set, and the period (`Oct 2026 (this month)`) with "undated tasks are hidden", or in Upcoming "Upcoming always shows the next 14 days".
- **Period** (last in the tool row): one compact control `‹ Oct 2026 › ▾` (`pctl`). The date button (`pMid`) shows `period.short` (`Oct 2026`, `Fall 2026`; or "All dates"), and the context line below gives the full `period.label` with the months; when the period isn't the current one it is accent-coloured and clicking it returns to `period.now`, otherwise it opens the menu. **▾** (`pCaret`) opens the menu: **All dates / By month / By season**, and **This month** / **This season**, which also returns to `period.now` (disabled, "you're here", when `period.current`). Choosing a month or season sends `{kind}`, and the server picks the one containing today. `‹` and `›` appear only with a period; their tooltip and `aria-label` name where they go (`Previous month: Sep 2026`, from `period.prev` / `period.next`). The page never does date math. The period is remembered in `localStorage`; if the server rejects a stored one, the page falls back to All dates. Edits send the period too, so the redrawn views keep it. The period is page-only (no CLI option yet).
- **Filters** (all tabs): a search box in the tool row (case-insensitive, over task titles, task notes and project names; Esc clears), and a **Filter** button whose panel holds a person picker (initials from `people`, plus `(unassigned)`), a project picker, **Show done tasks** (Projects and Timeline; `to_data` sends done tasks in `timeline.rows` and `timeline.unscheduled`, drawn faded, while the CLI timeline still lists open tasks only; People and Upcoming never show done tasks) and **Clear filters**. The button shows how many of person, project and show-done are set. `filtered(d)` applies them to a copy of the `/api/parse` data before the views draw it, so the views stay unchanged. In the Projects tree, a non-matching parent of a matching task stays visible but dimmed; projects and sections with no matches are hidden. Filters only select from fields the server already sent (`title`, `notes`, `assignees`, `project`, `status`), so the page still never reads the note format. Filter choices are remembered in `localStorage`. They are page-only: if the CLI gets filters, move this logic into `planner.py` so it exists once. "Edit alongside" (in ⋯) shows the text area next to it. The "Today" field (in ⋯) is the web form of `--today`.
- **Markdown:** a built-in renderer (`markdown()`). It escapes all input before adding tags and only allows `http(s)` links. Works offline.

**Open file** (in ⋯, or a click on the header's file chip) opens an in-page file browser (`picker`, a `<dialog>`): the server lists folders and `.txt` / `.md` files under the home folder (`GET /api/browse`), starting in the folder the server was started from, and choosing one opens it on the server (`POST /api/open`). Such a **picked file** works like file mode (same `/api/file`, version checks, CRLF and atomic writes) but **autosaves** `AUTOSAVE_MS` (1 s) after each change, typed or from the views; a conflict or a failed write stops autosave (`blocked`) until resolved or Save is pressed. ⋯ gets **Close file** (stop saving to it). The page remembers the path (`lastPath`), so after a server restart the header offers **Reopen fall.txt**. If the listing fails (no server, or a server started before this version, whose `/api/browse` is a 404), the dialog says so (restart the server) and offers **Load a file's text instead** (the hidden file input, which sits outside the menu so its click can't reopen the picker). A drop only loads the text when no file is open. The header's **file chip** shows a document icon and the open file's name ("Untitled" without one), with the full path on hover, then "Saved" / "Saving…" or the Save pill. **File mode** (`--serve notes.txt`): the page loads that file, hides "Open file", ignores drops, and "Save" (or Ctrl/⌘-S) writes it through `/api/file` with the version it last loaded or saved. The header shows the name and "Saved", or the **• Unsaved · Save** pill. If the file changed on disk, Save offers "Load disk version" (with a confirm if there are unsaved edits) or "Keep mine and overwrite". When the window regains focus the page re-checks the file: it reloads silently if there are no unsaved edits, otherwise shows the same choice. Unsaved edits from the last session are kept only if they were made on the exact version now on disk. Leaving with unsaved edits asks first. A command-line file is never saved automatically; only a file opened from the page autosaves. Text, mode, tab, theme, text size and font are remembered in `localStorage`. Dark mode follows the OS until it is chosen in ⋯. All note text is inserted as text, never as HTML, in Planner mode. Each task row carries `data-line` and shows `line N` on hover.

**Polish:** grey text and the overdue red pass 4.5:1 contrast on white and on the row hover colour; keyboard focus shows an accent outline (`:focus-visible`); under 720px wide the panes stack, the tool row wraps, and a task's Who / Effort / Date move onto a line under its title. With no tasks and no file, Planner mode shows a short hint and **Load the example** (`welcome()`, only while the text box is empty, from `/api/example`).

To add a view, write `view_x(projects) -> list[str]`, register it in `VIEWS`, and document it in both READMEs.

## Testing

Run the test suite (stdlib `unittest`, no installs). It must pass before any change is done:

```
python -m unittest -v
```

`test_planner.py` pins TODAY to 2026-10-12 and covers line classification, inline tokens, date resolution, derived semantics, the `example.txt` checklist below, `to_data` and the CLI. When you add or change behaviour, add a test for it.

Also run the CLI by hand:

```
python planner.py example.txt --today Oct12
python planner.py example.txt timeline --today Oct12
python planner.py --today Oct12 < example.txt
```

For the web page, run `python planner.py --serve --today Oct12`, open the page, load `example.txt`, switch through the three modes and four tabs, and toggle dark mode. The same checks below apply in the Projects, Timeline and Upcoming tabs. For file mode, run `python planner.py --serve copy-of-example.txt --today Oct12`: make an edit, Save, and check the file; then change the file in another editor and check that focusing the page reloads it, or offers the choice if you have unsaved edits. In Planner mode, click a few status boxes in different tabs and check that only that line's mark changes in the text, that Undo restores it, and that the cursor in "Edit alongside" doesn't jump. A quick API check without a browser: `POST /api/parse` with `{"text": "...", "today": "Oct12"}`, or `POST /api/edit` with `{"text": "...", "line": 17, "op": "status", "value": "done", "title": "site visit prep"}`. Also try date, size, +who and +sub on a few tasks and check the text. `test_planner.py` starts a real server for both.

Then check these against `example.txt`:
- `site visit prep` is OVERDUE.
- `use Q3 numbers…` is a note under `complete powerpoint`.
- `plan agenda` shows `(via parent)` Feb 16-18.
- `update handbook` is in Unscheduled.
- `annual report` spans Jan–Mar.
- The `Dec15--Jan10`-style year-crossing logic still works.

When you add behaviour, add a line to `example.txt` that exercises it.

## Roadmap

The improvement plan agreed with the user. Work through it in order unless the user says otherwise; each step follows the ground rules, gets tests, and updates the docs listed in rule 4.

### Done

1. **Groundwork:** `test_planner.py`; source line numbers on tasks (`Task.line`); one-line CLI errors instead of tracebacks.
2. **Edits from the views:** status (click the box), date, add initials, add subtask (`/api/edit`), each with Undo.
3. **File mode:** `--serve notes.txt` loads and saves that file, with version checks so an outside change is never overwritten silently.
6. **Filters:** search, person, project and show-done in the web page.
- **Month / Season view** (user request): pick a month or a season (Winter Jan-Apr, Summer May-Aug, Fall Sep-Dec) and step through them.

### 4. `check` view: warnings for likely mistakes (next)

The parser silently ignores what it doesn't understand: the text just stays in the title, or a line becomes something the user didn't mean. `check` lists those places with line numbers. It only reads; it never fixes anything itself.

- **Code:** `check(text) -> list[(line, code, message)]` in `planner.py`. It walks the raw lines with the same classification as `parse` and compares them with the parse result (line numbers come from `Task.line`). It must reuse the `RE_*` constants and `parse` rather than define a second grammar; new regexes are only for the near misses below. `view_check` prints it, `VIEWS` gets `check`, and `to_data` gets a `check` list. The CLI view needs the text as well as the projects, so `main` passes it.
- **Warnings** (code: example → message):
  - `date-space`: `Oct 24` → "a date has no space: Oct24".
  - `date-spelling`: `oct24`, `Sept5`, `October24` → "months are Jan…Dec, capitalised: Oct24".
  - `bad-date`: `Feb30`, `Oct32` → "no such date; it stays in the title".
  - `extra-date`: a second date token left in the title → "only the first date on a line counts".
  - `backwards-range`: `Oct26--20` (resolves to next year) → "the range ends before it starts".
  - `bad-loose`: `~Q5`, `~wk54`, `~ Nov` → "loose dates are ~Q1-4, ~Jan…Dec, ~wk1-53".
  - `bad-reminder`: `*weekly Fry`, `*monthly 32nd`, `*tomorrow` → "this reminder never fires".
  - `bad-initials`: `(ka)`, `(KAREN)` → "initials are 1-4 capital letters". Must not flag the effort tokens `(xs)`, `(s)`, `(m)`, `(l)`, `(xl)`.
  - `bad-effort`: `(xxs)`, `(xxl)`, `(med)`, or a second effort token → "effort is (xs), (s), (m), (l) or (xl), once per task".
  - `skipped-level`: a subtask indented two or more levels below its parent, or an indented task with no parent → "indent one tab per level".
  - `missing-dash`: a left-edge line with no marker that has initials or a date, or a heading followed directly by tasks with no `@project` (they land in `(no project)`) → "this became a heading; did you mean `- …`?"
  - `dash-lookalike`: a line starting with `–`, `—` or `•` → "only `-` marks a task".
  - `orphan-note`: a note before any project or task → "this note has nothing to attach to".
- **Web page:** a fifth tab, "Check (N)". Clicking a warning opens Edit alongside and selects that line in the text box.
- **Tests:** one per warning; `example.txt` must produce no warnings (it is the clean reference, so the bad cases live in the tests, not in `example.txt`).
- **Later, with the user's agreement:** a "fix" button per warning, done as one more `/api/edit` op under rule 3.

### 5. Calendar export (`.ics`)

`python planner.py notes.txt --ics plan.ics`, plus a download button on the page: one event per dated open task (all-day; a range spans its days; a loose date spans its period, marked "sometime in"), and reminders as events, with `*daily`, `*weekly Fri` and `*monthly 1st` as repeating events (`RRULE`). Each event's `UID` comes from project + title so re-importing updates rather than duplicates. Stdlib only (`.ics` is plain text).

### Other open ideas

- Assignee inheritance (decide with the user).
- More edits: editing a title or note, deleting or moving a task. Each must follow rule 3 and get the same "only this line changed" tests.
- Editing, filtering and the Month / Season period from the CLI (for example `--month Nov`, `--season Fall`). The period logic is already in `planner.py`; the text views would need to take it.
- A date in a note (`-- … Oct24`) is not parsed. That is intended.
