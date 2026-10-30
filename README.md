# Planner

Keep your plans as plain-text notes and view them by **project**, **timeline**, **person** and **what's coming up**.

You write notes the way you already do. A few light markers add status, dates, people and reminders, and `planner.py` turns them into views.

```
Fall Planning  Sep01--Dec19

@HDC
!- meet w. clients (KA)
- finish proposal (KA) Oct24
	~- complete powerpoint (JS) Oct20--23 *Oct19
		-- use Q3 numbers from Lisa's deck
	- send to board Oct24
~- annual report ~Q1
```

---

## Quick start

You need Python 3.8 or newer. Nothing else to install.

```
python planner.py                     # paste your notes, then press
                                      #   Ctrl-D (Mac/Linux) or Ctrl-Z then Enter (Windows)
python planner.py notes.txt           # or read your notes from a file
python planner.py notes.txt timeline  # show just one view
python planner.py --serve             # open the web page (see below)
```

To try it on the included sample:

```
python planner.py example.txt
```

---

## The web page

```
python planner.py --serve             # opens http://localhost:8765
python planner.py --serve --port 9000 --today Oct12
```

Paste your notes, or use **Open file** (or drag a file onto the page) to load a `.txt` or `.md`. **Save** downloads your edited text. Pick how to view it:

| Mode | Shows |
|---|---|
| **Plain** | Just your text, editable. Nothing is interpreted. Tab indents; Shift-Tab outdents. |
| **Planner** | Your notes in the planner format, with tabs for Projects, Timeline, People and Upcoming. Click a task's box (`[ ]`, `[~]`, `[x]`) to move it to in progress, then done, then back to open: only the mark at the start of that line changes in your text, and **Undo** puts it back. Hover a task for **date** (set, change, or clear with an empty box), **+who** (add initials) and **+sub** (add a subtask at the end of its subtasks); type and press Enter. These change only what they must: the date token, the `(...)` group, or one new tab-indented line. Tick **Edit alongside** to edit while you look. The **Today** box works like `--today`. |
| **Markdown** | Your text as rendered markdown. |

The **Dark / Light** button switches themes (it starts from your system setting). The page only talks to your own computer, and it remembers your text and settings in the browser. Clicking a status box changes the text in the page; use **Save** to keep it in a file.

---

## The rules

### Structure

| Write | Means |
|---|---|
| `Fall Planning` | **Heading.** Starts at the left edge, with no marker. Can carry dates: `Fall Planning  Sep01--Dec19` |
| `@HDC` | **Project.** Everything below it belongs to it until the next `@` or heading. |
| Tab | **One level deeper.** A task indented under another is its subtask. A task with subtasks is a sub-initiative. |

### Status (at the start of a line)

| Write | Means |
|---|---|
| `- task` | Open |
| `~- task` | In progress |
| `!- task` | Done |
| `-- note` | A note on the task directly above. Never a task. |

### Details (anywhere after the task text, in any order)

| Write | Means |
|---|---|
| `(KA)` or `(KA, RT)` | Assignee(s), as initials |
| `Oct24` | Due date |
| `Oct23--26` or `Oct23--Nov03` | Date range: start--end |
| `~Q1` `~Nov` `~wk43` | Loose date: sometime in that quarter, month or week |
| `*Oct17` | Reminder on a date |
| `*weekly Fri` `*monthly 1st` `*daily` | Repeating reminder |

### Good to know

- **`!`, `~` and `--` only mean status at the start of a line.** Later in the line, `~` marks a loose date and `--` is part of a date range, so they never clash.
- **Don't write years.** A date up to about 3 months back counts as past, so a missed task shows as overdue. Any other date means the coming year.
- **Dates flow both ways.** An undated subtask uses its parent's dates, and a parent's dates stretch to cover its subtasks. A task with no dates anywhere goes to the **Unscheduled** list.
- **Assignees don't pass down.** A subtask with no initials of its own counts as unassigned.
- **Don't forget the dash.** A line at the left edge without one becomes a new heading.
- **Tabs or spaces.** If your editor turns tabs into spaces, use 4 spaces per level.

---

## The views

| View | Shows |
|---|---|
| `projects` | Every heading and project as a tree, with done counts, dates, notes and an OVERDUE flag. |
| `timeline` | Open tasks on a 12-month bar chart starting this month, plus the Unscheduled list. `<` means it ended before this month, `>` that it runs past the chart. |
| `people` | Open tasks grouped by assignee, soonest first, plus an `(unassigned)` group. |
| `upcoming` | What's overdue, what's due and which reminders fire in the next 14 days, plus everything in progress. |

Done tasks appear only in the `projects` view.

To see the views as of another day, use `--today`, for example `python planner.py notes.txt --today Nov01`.

---

## Files

| File | What it is |
|---|---|
| `planner.py` | The viewer and the small local server: one file, standard library only |
| `web/index.html` | The web page (editor, three modes, dark mode), served by `planner.py --serve` |
| `example.txt` | Sample notes that use every rule |
| `test_planner.py` | Automated tests: run `python -m unittest` |
| `README.md` | This guide |
| `AGENTS.md` | The exact format spec and code map, for AI agents and anyone changing the code |
