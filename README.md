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
python planner.py --serve             # open the web page on your Projects folder (see below)
python planner.py --serve notes.txt   # ...or edit just notes.txt
python planner.py ./Projects week     # the views over all your projects, in the terminal
```

To try it on the included sample:

```
python planner.py example.kf
```

---

## The web page

```
python planner.py --serve             # opens http://localhost:8765 on your Projects folder
python planner.py --serve notes.txt   # edits notes.txt: Save writes back to it
python planner.py --serve --port 9000 --today Oct12
python planner.py --serve --host 0.0.0.0   # reachable from other machines on your network
```

`--host` is an option of `--serve` and does nothing without it (`python planner.py --host 0.0.0.0` alone is an error). `--serve --host 0.0.0.0` makes the page available to every machine that can reach this one, at `http://THIS-MACHINES-ADDRESS:8765`. There is **no login and no address check** then: anyone who can open the page can read and change your notes, so use it only on a network you trust. It doesn't open a browser (the server is usually headless), and by default (without `--host`) only this computer can connect.

If the page ever freezes or draws wrongly, open it as `http://localhost:8765/?debug=1`: a small overlay lists each request's time and any error, which helps to report the problem.


`--serve` needs nothing else: it finds the `Projects` folder next to `planner.py` (see [Projects](#projects)) and shows your projects. Everything saves itself about a second after each change.

If you start it with a file (`--serve notes.txt`), the page opens that file and **Save** (or Ctrl/⌘-S) writes straight back to it. The header shows "Saved", or a **• Unsaved · Save** button when you have changes. If the file was changed somewhere else in the meantime, nothing is overwritten: you choose between loading the version on disk and keeping yours. Come back to the page after editing the file elsewhere and it picks up the change. Nothing is saved until you press Save.

Pick how to view it:

| Mode | Shows |
|---|---|
| **Text** | Just your text, editable. Nothing is interpreted. Tab indents; Shift-Tab outdents. |
| **Planner** | Your notes in the planner format, with tabs for Projects, Timeline, People, Upcoming and **Planner**. Tasks are listed compactly, with their initials, effort and date in columns on the right. Click a task's circle (empty, half-filled or ticked) to move it to in progress, then done, then back to open: only the mark at the start of that line changes in your text, and **Undo** (in the message at the bottom) puts it back. Click a task's **title** to edit the task's text: the box shows the whole line as you wrote it after the dash (like `finish proposal (KA) (l) Oct24`), so you can change the wording, initials, effort and date at once; Enter saves, Esc cancels. Click a task's **Who** cell to change its initials (it opens with the current ones; an empty box removes them), its **Date** cell to set, change or clear the date, or the **+** at the end of the row to add a subtask; type and press Enter (Esc cancels). Click its **Effort** cell to pick `XS`, `S`, `M`, `L`, `XL` or **None** from a short list. To add a new task, click **+ Add task**: at the end of each project in Projects, under each person in People (their initials are filled in for you), and at the bottom of Timeline and Upcoming, where you also pick the project (it remembers the last one, or uses the project you filtered by). Type the title, then Tab to the small **Who**, **Effort** and **Date** fields if you like (or type `(KA) (m) Oct24` in the title as usual). Set **My initials** and **Default effort** in the **⋯** menu and they're filled in for you. Press Enter: the task goes at the end of that project and the form opens again for the next one; Esc stops. The **+** at the end of a row works the same way for subtasks. **Tab** also moves between a task's parts while you edit: title → Who → Effort → Date → the next task (Shift-Tab goes back), saving each as you go; in the Effort list, type `s`, `m`, `l` or `x` to jump to a size. Empty cells show a faint **+** when you point at the row. A date in italics comes from the task's parent or subtasks, and `~Q1`-style dates show their full range when you hover them. These change only what they must: the date token, the effort token, the `(...)` group, or one new line (a subtask one tab deeper than its parent, a new task at the end of its project). A task's effort shows as a small deep-purple badge (`XS`, `S`, `M`, `L`, `XL`; hover it for the points), a bell before a date means it has a reminder, and each project and person shows the points still open. Next to the tabs, the period control (`‹ Oct 2026 › ▾`) picks **All dates**, **By month** or **By season** from its **▾** button. Seasons are Winter (Jan-Apr), Summer (May-Aug) and Fall (Sep-Dec). It starts at the current month or season, shown in the middle (marked "this month" or "this season"). **‹** and **›** step back and forward (hover them to see where they go). When you have stepped away, the date turns blue: click it to come back to this month or season (**This month** / **This season** in the menu does the same). Projects, Timeline and People then show only tasks whose dates fall in it, and the Timeline's columns become its weeks (month) or months (season). Undated tasks are hidden, and Upcoming always shows the next 14 days. Next to it, **search** (tasks, notes and project names), or open **Filter** to pick a **person** or **project**, or untick **Show done tasks** (Projects and Timeline). A parent that doesn't match stays visible but faded when one of its subtasks does. In the Projects tab every level folds: click a section's title (like **Fall Planning**) to fold its projects, a project's name to fold its tasks, or the small arrow left of a task's circle to fold its subtasks (a folded task says how many it hides). In People, click a person's initials. Folds are remembered in the browser, and everything opens while a search or filter is on. **Clear filters** resets them. In the **⋯** menu, tick **Edit alongside** to edit while you look (then clicking a task, anywhere but its circle or cells, selects its line in the text and scrolls to it instead of opening the title box); the **Today** box works like `--today`. |
| **Markdown** | Your text as rendered markdown. |

**Dark mode** / **Light mode** in the **⋯** menu switches themes (it follows your system setting until you choose). **Text size** (four sizes of **A**) makes the text in the editor and the views smaller or larger, and **Font** picks how the Planner and Markdown views look: System, Rounded, Serif, Legible (clear letter shapes), Condensed (fits more on a line) or Monospace. The text editor keeps its fixed-width font so your tab indents line up. Both are remembered in the browser. The page only talks to your own computer, and it remembers your text and settings in the browser. Every change you make in the views (a status, a cell, a new task) changes the text: a file opened from the page saves itself, while a file given on the command line is written when you press **Save**.

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
| `(!)- task` | Notable: circled in purple (put `(!)` in front of any of the three, like `(!)!- task`) |
| `-- note` | A note on the task directly above. Never a task. |

### Details (anywhere after the task text, in any order)

| Write | Means |
|---|---|
| `(KA)` or `(KA, RT)` | Assignee(s), as initials |
| `(xs)` `(s)` `(m)` `(l)` `(xl)` | Effort: extra small, small, medium, large, extra large, worth **1, 2, 3, 5 and 8 points** |
| `Oct24` | Due date |
| `Oct23--26` or `Oct23--Nov03` | Date range: start--end |
| `~Q1` `~T1` `~Nov` `~wk43` | Loose date: sometime in that quarter, trimester, month or week. Trimesters follow the calendar like quarters: `~T1` is Winter (Jan-Apr), `~T2` Summer (May-Aug), `~T3` Fall (Sep-Dec), the same months as the seasons |
| `*Oct17` | Reminder on a date |
| `*daily` `*weekdays` `*weekly Fri` `*weekly Mon, Wed, Fri` `*monthly 1st` | Repeating reminder (in `habits.kf`, a habit's frequency) |
| `-- done Nov02 Nov03` | A habit's log: the days it was done (the latest such days so far) |
| `>Oct14` `>wk45` `>Nov` `>T3` | Planned: when you mean to work on it, a day, a week, a month or a trimester (the **Planner** tab). Separate from the due date: `draft report Oct24 >Oct14` is due Oct 24, planned for Oct 14 |
| `^wk45` `^Nov` `^T3` `^yr` | A top priority for that week, month, trimester or this year (the ☆ in the Planner). A task can have several |

### The Planner tab

The **Planner** plans by **Year**, **Season**, **Month** or **Week** (pick one next to Filter; **‹ ›** step, and the date between them brings you back to now). The columns are the next step down: a year's trimesters (Winter, Summer, Fall), a season's months, a month's weeks, a week's days (Monday to Friday, then Saturday/Sunday together). On the right, **This week** (or month, season, year) lists what's planned, grouped by project, with the points done out of those planned per project (like `4/16 pts`). Below is the **Backlog**: every open task that isn't planned for that period.

To plan a task, drag it from the backlog onto a column, or click its **Plan** cell and pick one (that works on a phone too). Drag a planned task to another column to move it, or back onto the backlog to unplan it. Planning adds `>Oct14`, `>wk45`, `>Nov` or `>T3` to the task's line, so you can also type it. A task planned for a day also shows in its week, month and season. A finished task stays where it was planned, crossed out; one you didn't get to stays put and is back in the backlog next time, showing its old plan.

Click the **☆** on a task to make it a **top priority** for the period you're looking at (it adds `^wk45`, `^Nov`, `^T3` or `^yr`); they're listed at the top, and a starred task also comes first in its day, in the list on the right and in the backlog (with its subtasks). Since the notes have no years, a column or star too far away (like Winter of this year, once it's past) is greyed out.

**On the calendar** at the top shows which projects are on the Planner: click **×** on one to take it off, and **+ Add project** to put it back. There is one Planner for all your projects: it's first in the drawer, and the Planner tab on any project page takes you there.

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

## Projects

Your projects live in the **`Projects`** folder next to `planner.py`, one sub-folder per project. `python planner.py --serve` finds it by itself (and makes it if it's missing). Each project keeps its files side by side, so they stay plain text you can open anywhere and sync with any folder-sync tool:

```
Projects/
  Example/              a sample project to look around in; delete it whenever you like
    backlog.kf          the project's planning notes
    quicknote.kf        a quick note for this project
    habits.kf           repeating tasks (habits)
    notes/              notes pages (.kf, .txt or .md), in sections (sub-folders) if you like
    archive/2026.kf     finished tasks, by year
  HDC/ ...
  .trash/               anything you delete goes here, never gone for good
```

**+ New project** in the drawer makes the folder with all of these ready: an empty `backlog.kf`, `quicknote.kf` and `habits.kf`, and the `notes/` and `archive/` folders. A folder you add yourself becomes a project too, and any of its files that are missing are made the first time you save them.

Git ignores `Projects/` except for `Example`, so your own projects stay out of the repository.

Turn an existing notes file into a project with:

```
python planner.py --import notes.txt           # one project, named after the file
python planner.py --import notes.txt --split   # one project per @ line
```

Your lines are copied exactly; nothing in `notes.txt` changes. In the terminal, `python planner.py ./Projects` (or `… ./Projects week`) shows the views over every project, the week with each day's habits. Write the `./`: a bare `Projects` means the Projects view.

In the page, **click the KAFEEN logo** to open the project drawer:

- **All projects** shows every project's backlog together, in the usual Projects / Timeline / People / Upcoming tabs. In the Projects tab each project has one heading, with its counts; click it to fold away everything in that project (its `@` sub-groups fold on their own too). The **Planner** (first in the drawer) plans all of them together. Click a task's circle or cells to change it, as usual: the change is written straight into that project's `backlog.kf`.
- Under each project: its **Quick note**, **Backlog**, **Notes** (pages, grouped in sections if you like, like OneNote), **Habits** and **Archive**. Click one to open it. The Backlog, Archive and Habits open in Planner mode. The Quick note and notes pages open in Text (`.md` pages in Markdown), with **Planner** greyed out. Everything saves itself about a second after each change.
- **⋯** on a project, section or page has New page, New section, Rename and Delete. **+ New project** is at the bottom, and **Find a project** at the top.

The header shows where you are (`HDC › Notes › Kickoff call`); click it to open the drawer. The page you were on opens again next time.

**Circle, archive, delete.** Every task row ends in a faint **⋯**. Click it to **Circle in purple** (marks a notable task with a purple box; it writes `(!)` in front of the task), **Archive to 2026** (or last year), or **Delete** (the task goes with its subtasks and notes; it asks first if there are subtasks). Archiving moves the task and its subtasks, word for word, into the project's `archive/2026.kf`, under the same `@` group, and the year appears under **Archive** in the drawer. To clear out a project, point at its heading and click **Archive done**: every finished task (done, with all its subtasks done) moves to the archive; a finished subtask of a task that's still open stays where it is. **Undo** in the message at the bottom puts everything back. An archive page shows that year's dates (no years are written in the notes, so `Mar10` in `2025.kf` means March 10, 2025).

**Habits.** Each project has a **Habits** page (`habits.kf`) for repeating tasks. Every habit is a task with how often it repeats: `- stretch *daily`, `- gym (KA) *weekly Mon, Wed, Fri`, `- standup *weekdays`, `- rent *monthly 1st`. The page shows this week with a tick box per day; click one when you've done it (days that haven't come yet can't be ticked). Ticks are written in a note under the habit, `-- done Nov02 Nov03`. Click **Every** to change how often, and **+ Add habit** to add one (a name and how often). **‹ ›** steps through the weeks. Your habits also show in the **Planner**: on the Week level, each day lists the habits due that day, with the same tick boxes; on the other levels, each column says how many were done. In January, the page offers to move last year's ticks to the archive. To retire a habit, mark it done (or delete it from its **⋯**).

---

## Files

| File | What it is |
|---|---|
| `planner.py` | The viewer and the small local server: one file, standard library only |
| `web/index.html`, `web/app.css`, `web/app.js` | The web page (editor, three modes, dark mode), served by `planner.py --serve` |
| `example.kf` | Sample notes that use every rule |
| `Projects/` | Your projects; `Projects/Example` is a sample project |
| `example/` | `example.kf` split into projects, with a quick note and notes pages: a reference for the tests |
| `test_planner.py` | Automated tests: run `python -m unittest` |
| `changelog.txt` | What changed in each version |
| `README.md` | This guide |
| `AGENTS.md` | The exact format spec and code map, for AI agents and anyone changing the code |
