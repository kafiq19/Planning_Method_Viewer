# AGENTS.md

Instructions for AI agents (and developers) working in this repo. Human-facing docs live in `README.md`. This file is the **normative spec**: if the code and this file disagree, fix one of them so they match, and say which one you changed.

## What this repo is

`planner.py` parses a plain-text planning-notes format and prints four views: `projects`, `timeline`, `people` and `upcoming`. `planner.py` uses only the Python standard library (3.8+). It also serves a small web page (`web/index.html`) with `--serve`. `example.txt` is the reference input and exercises every rule.

## Ground rules

1. **The note format belongs to the user.** It is a light layer over how they already write notes. Do not add, rename or repurpose markers unless the user asks. Propose format changes in plain words first.
2. **Keep it stdlib-only.** No `pip` dependencies, in Python or in the page (no CDN scripts, no JS libraries). Parsing lives only in `planner.py`; the page never re-implements the note format, it asks the server. Keep the repo small: `planner.py`, `web/index.html`, `test_planner.py`, the docs and the example.
3. **Parsing never changes the notes.** The tool edits them only on an explicit user action (clicking a task's status box, or its date / +who / +sub actions). An edit touches only its target line and only the characters it must; adding a subtask inserts one new line and changes no existing line (except giving a final line with no line ending one). Wording, order, indentation, trailing whitespace and line endings stay exactly as they were. An edit made from an out-of-date view is refused, not guessed at. When you edit or generate notes for the user, follow the grammar below exactly and preserve the same things.
4. **Keep `README.md` (humans), this file (machines) and the docstring at the top of `planner.py` in sync** whenever behaviour changes. A new view or field must reach `to_data` and `web/index.html` as well as the CLI.
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
| Assignees | `\(\s*([A-Z]{1,4}(?:\s*,\s*[A-Z]{1,4})*)\s*\)` | `assignees` (all matches) |
| Reminder | `\*(daily\|weekly\s+[A-Za-z]{3}[a-z]*\|monthly\s+\d{1,2}(?:st\|nd\|rd\|th)?\|MON\d{1,2})\b` | `reminders` (all matches) |
| Range | `(?<![\w*~])(MON)(\d{1,2})--(MON)?(\d{1,2})\b` | `start`, `end` (first match only) |
| Loose date | `(?<!\S)~(Q[1-4]\|wk\d{1,2}\|MON)\b` | `start`, `end`, `loose` (only if no range was found) |
| Date | `(?<![\w*~])(MON)(\d{1,2})\b` | `start = end` (only if neither of the above was found) |

Each task has at most one date span. Later date tokens on the same line stay in the title.

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
- Section (heading) dates are display-only. Tasks do not inherit them.

### Valid-note checklist (for agents writing notes)

- Every task line starts with `- `, `~- ` or `!- ` after its indentation.
- Subtasks are indented exactly one more tab than their parent.
- Notes start with `-- ` and go directly under the task they describe.
- Dates are `MonDD` with no space (`Oct24`, `Nov03`). Ranges are `Oct23--26` or `Oct23--Nov03`. Loose dates are `~Q1`, `~Nov` or `~wk43`.
- Initials go in parentheses: `(KA)` or `(KA, RT)`.
- Never write years. Never put free text at the left edge unless it is meant to be a heading.

---

## Code map (`planner.py`)

| Symbol | Role |
|---|---|
| `RE_*` constants | Token regexes from the table above |
| `PAST_DAYS`, `UPCOMING_DAYS` | Date window (90) and look-ahead for `upcoming` (14) |
| `resolve`, `resolve_after`, `loose_span`, `next_reminder` | Date resolution |
| `fd`, `fspan` | Date formatting. The year is shown only when it isn't TODAY's year. |
| `timeline_months`, `timeline_rows`, `people_groups`, `upcoming_groups` | Shared collectors: the text views and `to_data` both use them, so the logic exists once |
| `Task` | Parsed task (headings reuse it). `line` is its 1-based line in the source text, counting blank lines, and `col` is where the text after the dash starts in that line. `_parse` extracts tokens and records where each sat in `at` (`assignees`, `reminders`, `date`: spans relative to `col`) plus the date token's original text in `date_text`. `walk`, `rollup`, `span`, `overdue` and `label` derive the rest. |
| `Project` | Name, section, root tasks and notes |
| `parse(text)` | Line classifier and stack builder. Returns `list[Project]`. |
| `view_projects`, `view_timeline`, `view_people`, `view_upcoming` | Each returns `list[str]` |
| `task_data`, `flat`, `to_data(projects)` | JSON-ready dicts of all four views, for the web page. Every task carries `line`. |
| `EditError`, `_task_at`, `EDITS` | Edits, all `f(text, line, value, title=None) -> text`. Each raises `EditError` if the line isn't a task, `title` doesn't match its parsed title (stale view) or the value is invalid, and re-parses its result to check it reads back as intended. `EDITS` maps the `/api/edit` op names to them. |
| `set_status` (op `status`) | Swaps the `!`/`~` mark before the dash (`STATUS_MARK`). |
| `set_date` (op `date`) | Replaces the task's own date token in place; if it has none, inserts one before the first reminder or at the end of the line; an empty value removes the token and the spaces before it. Refused if the result wouldn't resolve to that date (for example an earlier invalid `Feb30` takes priority). |
| `add_assignees` (op `assign`) | Adds initials (`RT` or `RT, JS`) to the last `(...)` group, or inserts a new group before the first date or reminder token (`finish proposal (KA) Oct24`), or at the end. Skips initials already there. |
| `add_subtask` (op `subtask`) | Inserts `- value` as the last subtask: after the task's last subtree line (subtasks and their notes, before blank lines), one tab deeper (4 spaces if the parent is indented with spaces only), with the parent line's line ending. |
| `set_today`, `make_server(port)`, `serve(port)` | `make_server` builds a `127.0.0.1`-only `http.server` (port 0 = any free port, used by the tests); `serve` runs it and opens the browser. `GET /` returns `web/index.html`. `POST /api/parse` takes `{text, today}` and returns `to_data`. `POST /api/edit` takes `{text, line, title, op, value, today}` (op: `status`, `date`, `assign`, `subtask`) and returns `{text, data}` (the new text and its `to_data`); 409 if the edit is refused, 400 if the request is malformed. `TODAY` is reset on every request. |
| `VIEWS`, `take_option`, `main` | CLI: an optional file path, view names (any case), `--today`, and `--serve [--port N]` (default 8765). Reads stdin when no path is given. Bad arguments (unknown view or missing file, two files, a missing or invalid `--today`/`--port`) exit with code 1 and a one-line `planner.py: …` message, never a traceback. |

## Web page (`web/index.html`)

One self-contained file (inline CSS and JS, no dependencies). Three modes, chosen with the toggle in the header:

- **Plain:** editable text area only; text is never changed. Tab indents (Shift-Tab outdents) because the format is tab-based.
- **Planner:** the four views as tabs, drawn from `/api/parse`. Clicking a task's status box (in any tab, including timeline rows) cycles open → in progress → done → open through `/api/edit`. The page swaps in only the changed characters, so the cursor and scroll in the side editor stay put, and shows a message with **Undo** (which works while the text is unchanged since). If the user typed while the request was out, the edit is dropped. Task rows (not timeline rows) also show **date**, **+who** and **+sub** on hover, each opening a one-line input (Enter applies, Esc cancels; the date input starts with the current token from `date_text`, and empty clears it). Every edit gets the same message and Undo. Nothing else in the views edits text. "Edit alongside" shows the text area next to it. The "Today" field is the web form of `--today`.
- **Markdown:** a built-in renderer (`markdown()`). It escapes all input before adding tags and only allows `http(s)` links. Works offline.

Files come in through "Open file" or drag and drop and go out through "Save" (a download). Text, mode, tab and theme are remembered in `localStorage`. Dark mode follows the OS until the toggle is used. All note text is inserted as text, never as HTML, in Planner mode. Each task row carries `data-line` and shows `line N` on hover.

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

For the web page, run `python planner.py --serve --today Oct12`, open the page, load `example.txt`, switch through the three modes and four tabs, and toggle dark mode. The same checks below apply in the Projects, Timeline and Upcoming tabs. In Planner mode, click a few status boxes in different tabs and check that only that line's mark changes in the text, that Undo restores it, and that the cursor in "Edit alongside" doesn't jump. A quick API check without a browser: `POST /api/parse` with `{"text": "...", "today": "Oct12"}`, or `POST /api/edit` with `{"text": "...", "line": 17, "op": "status", "value": "done", "title": "site visit prep"}`. Also try date, +who and +sub on a few tasks and check the text. `test_planner.py` starts a real server for both.

Then check these against `example.txt`:
- `site visit prep` is OVERDUE.
- `use Q3 numbers…` is a note under `complete powerpoint`.
- `plan agenda` shows `(via parent)` Feb 16-18.
- `update handbook` is in Unscheduled.
- `annual report` spans Jan–Mar.
- The `Dec15--Jan10`-style year-crossing logic still works.

When you add behaviour, add a line to `example.txt` that exercises it.

## Known limitations / open ideas

- Assignee inheritance (decide with the user).
- Edits from the views: status, date, adding initials and adding a subtask. Not yet: removing initials, editing titles or notes, deleting or moving tasks. Each new edit must follow rule 3 and get the same "only this line changed" tests.
- Editing from the CLI is not supported yet.
- A date in a note (`-- … Oct24`) is not parsed. That is intended.
