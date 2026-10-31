# KAFEEN Planner

Keep your plans as plain-text notes and view them by **project**, **timeline**, **person** and **what's coming up**.

You write notes the way you already do. A few light markers add status, dates, people, effort and reminders, and `planner.py` turns them into views.

```
Fall Planning  Sep01--Dec19

@HDC
!- meet w. clients (KA)
- finish proposal (KA) (l) Oct24
	~- complete powerpoint (JS) (m) Oct20--23 *Oct19
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
python planner.py --serve notes.txt   # ...and edit notes.txt directly
```

To try it on the included sample:

```
python planner.py example.txt
```

---

## The web page

```
python planner.py --serve             # opens http://localhost:8765
python planner.py --serve notes.txt   # edits notes.txt: Save writes back to it
python planner.py --serve --port 9000 --today Oct12
```

Paste your notes, or press **Load the example** to try it, or use **Open file** in the **⋯** menu (or **+** after the tabs) to pick a `.txt` or `.md` file from your home folder. A file opened this way **saves itself** about a second after each change, and shows up as a **tab** in the header. Open as many as you like (one per project, say) with the **+** after the tabs, click a tab to switch, and **×** to close it (the file itself stays on disk). Next time you start the planner, the same files open again, on the tab you were using, like Notepad. To start a new planning file, press **New file…** at the bottom of the file browser and give it a name. The header shows "Saving…" then "Saved"; a red dot on a tab means its latest changes couldn't be saved yet (they're kept, and come back when you return to the tab). If a file was changed somewhere else in the meantime, nothing is overwritten and you choose which version to keep. Your tabs are remembered in this browser. The first tab is always **Quick note**, a place to jot ideas down without a file. It's kept in your browser (the header says "Kept in this browser"), so it survives reloads, crashes and restarts, and it can't be closed by accident. **Save** while it's showing downloads it as a file.

If you start it with a file (`--serve notes.txt`), the page opens that file and **Save** (or Ctrl/⌘-S) writes straight back to it. The header shows "Saved", or a **• Unsaved · Save** button when you have changes. If the file was changed somewhere else in the meantime, nothing is overwritten: you choose between loading the version on disk and keeping yours. Come back to the page after editing the file elsewhere and it picks up the change. Nothing is saved until you press Save.

Pick how to view it:

| Mode | Shows |
|---|---|
| **Text** | Just your text, editable. Nothing is interpreted. Tab indents; Shift-Tab outdents. |
| **Planner** | Your notes in the planner format, with tabs for Projects, Timeline, People, Upcoming and **Week**. Tasks are listed compactly, with their initials, effort and date in columns on the right. Click a task's circle (empty, half-filled or ticked) to move it to in progress, then done, then back to open: only the mark at the start of that line changes in your text, and **Undo** (in the message at the bottom) puts it back. Click a task's **title** to edit the task's text: the box shows the whole line as you wrote it after the dash (like `finish proposal (KA) (l) Oct24`), so you can change the wording, initials, effort and date at once; Enter saves, Esc cancels. Click a task's **Who** cell to change its initials (it opens with the current ones; an empty box removes them), its **Date** cell to set, change or clear the date, or the **+** at the end of the row to add a subtask; type and press Enter (Esc cancels). Click its **Effort** cell to pick `XS`, `S`, `M`, `L`, `XL` or **None** from a short list. To add a new task, click **+ Add task**: at the end of each project in Projects, under each person in People (their initials are filled in for you), and at the bottom of Timeline and Upcoming, where you also pick the project (it remembers the last one, or uses the project you filtered by). The new task goes at the end of that project. Empty cells show a faint **+** when you point at the row. A date in italics comes from the task's parent or subtasks, and `~Q1`-style dates show their full range when you hover them. These change only what they must: the date token, the effort token, the `(...)` group, or one new line (a subtask one tab deeper than its parent, a new task at the end of its project). A task's effort shows as a small deep-purple badge (`XS`, `S`, `M`, `L`, `XL`; hover it for the points), a bell before a date means it has a reminder, and each project and person shows the points still open. Next to the tabs, the period control (`‹ Oct 2026 › ▾`) picks **All dates**, **By month** or **By season** from its **▾** button. Seasons are Winter (Jan-Apr), Summer (May-Aug) and Fall (Sep-Dec). It starts at the current month or season, shown in the middle (marked "this month" or "this season"). **‹** and **›** step back and forward (hover them to see where they go). When you have stepped away, the date turns blue: click it to come back to this month or season (**This month** / **This season** in the menu does the same). Projects, Timeline and People then show only tasks whose dates fall in it, and the Timeline's columns become its weeks (month) or months (season). Undated tasks are hidden, and Upcoming always shows the next 14 days. Next to it, **search** (tasks, notes and project names), or open **Filter** to pick a **person** or **project**, or untick **Show done tasks** (Projects and Timeline). A parent that doesn't match stays visible but faded when one of its subtasks does. In the Projects tab, click a project's name (in People, a person's initials) to fold its tasks away or open them again (remembered in the browser; everything opens while a search or filter is on). **Clear filters** resets them. In the **⋯** menu, tick **Edit alongside** to edit while you look (then clicking a task, anywhere but its circle or cells, selects its line in the text and scrolls to it instead of opening the title box); the **Today** box works like `--today`. |
| **Markdown** | Your text as rendered markdown. |

**Dark mode** / **Light mode** in the **⋯** menu switches themes (it follows your system setting until you choose). **Text size** (four sizes of **A**) makes the text in the editor and the views smaller or larger, and **Font** picks how the Planner and Markdown views look: System, Rounded, Serif, Legible (clear letter shapes), Condensed (fits more on a line) or Monospace. The text editor keeps its fixed-width font so your tab indents line up. Both are remembered in the browser. The page only talks to your own computer, and it remembers your text and settings in the browser. Clicking a status box changes the text in the page; use **Save** to keep it.

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
| `(xs)` `(s)` `(m)` `(l)` `(xl)` | Effort: extra small, small, medium, large, extra large, worth **1, 1, 3, 5 and 8 points** |
| `Oct24` | Due date |
| `Oct23--26` or `Oct23--Nov03` | Date range: start--end |
| `~Q1` `~Nov` `~wk43` | Loose date: sometime in that quarter, month or week |
| `*Oct17` | Reminder on a date |
| `*weekly Fri` `*monthly 1st` `*daily` | Repeating reminder |
| `>Oct14` | Planned: the day you mean to work on it (the **Week** tab). Separate from the due date: `draft report Oct24 >Oct14` is due Oct 24, planned for Oct 14 |

### The Week tab

The **Week** tab is a weekly planner. Across the top are the days, Monday to Friday and then Saturday/Sunday together, with today highlighted. On the right, **This week** lists what's planned, grouped by project, with the points per project at the bottom. Below is the **Backlog**: every open task that isn't planned for this week, grouped by project.

To plan a task, drag it from the backlog onto a day, or click its **Plan** cell and pick a day (that works on a phone too). Drag a planned task to another day to move it, or back onto the backlog to unplan it; clicking a planned task gives the same day list, with **Unplan**. Planning just adds `>Oct14` to the task's line, so you can also type it. A task you finish stays on its day, crossed out; one you didn't get to stays where it was and is back in the backlog next week, showing the day it was planned for. **‹ ›** next to Filter step through the weeks, and the date between them brings you back to this week.

### Good to know

- **`!`, `~` and `--` only mean status at the start of a line.** Later in the line, `~` marks a loose date and `--` is part of a date range, so they never clash.
- **Don't write years.** A date up to about 3 months back counts as past, so a missed task shows as overdue. Any other date means the coming year.
- **Dates flow both ways.** An undated subtask uses its parent's dates, and a parent's dates stretch to cover its subtasks. A task with no dates anywhere goes to the **Unscheduled** list.
- **Assignees don't pass down.** A subtask with no initials of its own counts as unassigned.
- **Effort is lowercase.** `(m)` is effort; `(M)` is someone's initials. Only the first effort on a line counts, and one stuck to a word, as in `file(s)`, is just text. A good order is `task (KA) (m) Oct24`.
- **Effort is per task.** Totals simply add up each task's own points: a parent's effort doesn't come from its subtasks, and subtasks don't take their parent's.
- **Don't forget the dash.** A line at the left edge without one becomes a new heading.
- **Tabs or spaces.** If your editor turns tabs into spaces, use 4 spaces per level.

---

## The views

| View | Shows |
|---|---|
| `projects` | Every heading and project as a tree, with done counts, effort (`[M]`, and the points left per project), dates, notes and an OVERDUE flag. |
| `timeline` | Open tasks on a 12-month bar chart starting this month, plus the Unscheduled list. `<` means it ended before this month, `>` that it runs past the chart. |
| `people` | Open tasks grouped by assignee, soonest first, with each person's open points, plus an `(unassigned)` group. |
| `upcoming` | What's overdue, everything in progress, then what's due and which reminders fire in the next 14 days. |
| `week` | This week's plan: what's planned for each day (Saturday and Sunday together), the planned tasks per project with their points, and the backlog of open tasks not planned this week. |

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
| `changelog.txt` | What changed in each version |
| `README.md` | This guide |
| `AGENTS.md` | The exact format spec and code map, for AI agents and anyone changing the code |
