#!/usr/bin/env python3
"""
planner.py (KAFEEN Planner) - turn plain-text planning notes into four views:
projects, timeline, people, and what's coming up.
Standard library only (Python 3.8+).

USAGE
  python planner.py                    paste your notes, then press
                                       Ctrl-D (Mac/Linux) or Ctrl-Z then Enter (Windows)
  python planner.py notes.txt          read notes from a file instead
  python planner.py notes.txt people   show one view only:
                                       projects | timeline | people | upcoming
  --today Oct10                        pretend today is another date (for testing)
  --serve [notes.txt] [--port 8765]    open the web page; with a file, Save writes back to it. Without one, open
                                       files from the page: each is a tab, saved automatically and reopened next time
                                       (paste/open/edit notes, dark mode;
                                       click a task's box to change its status, its title to edit
                                       its text, or its Who / Effort / Date / + cells to edit it or add a subtask,
                                       or + Add task to add a task to a project)

NOTE FORMAT (quick reference)
  Fall Planning  Sep01--Dec19   heading: left edge, no marker, optional dates
  @HDC                          project: runs until the next @ or heading
  - task  ~- task  !- task      open / in progress / done
  <Tab>                         one level deeper = subtask
  -- text                       note on the task above (never a task)
  (KA)  (KA, RT)                assignees
  (xs) (s) (m) (l) (xl)         effort: 1, 1, 3, 5 or 8 points (lowercase only)
  Oct24                         due date
  Oct23--26  Oct23--Nov03       date range
  ~Q1  ~Nov  ~wk43              loose date: sometime in that period
  *Oct17  *weekly Fri  *monthly 1st  *daily     reminder
"""
import os
import re
import sys
from datetime import date, timedelta

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS = {m: i for i, m in enumerate(MONTH_NAMES, 1)}
MON = "(?:" + "|".join(MONTH_NAMES) + ")"
WEEKDAYS = {d: i for i, d in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}

RE_EFFORT = re.compile(r"(?<!\w)\(\s*(xs|s|m|l|xl)\s*\)")     # lowercase, so (S) stays initials
RE_ASSIGN = re.compile(r"\(\s*([A-Z]{1,4}(?:\s*,\s*[A-Z]{1,4})*)\s*\)")
RE_REMIND = re.compile(r"\*(daily|weekly\s+[A-Za-z]{3}[a-z]*|monthly\s+\d{1,2}(?:st|nd|rd|th)?|"
                       + MON + r"\d{1,2})\b")
RE_RANGE = re.compile(r"(?<![\w*~])(" + MON + r")(\d{1,2})--(" + MON + r")?(\d{1,2})\b")
RE_LOOSE = re.compile(r"(?<!\S)~(Q[1-4]|wk\d{1,2}|" + MON + r")\b")
RE_DATE = re.compile(r"(?<![\w*~])(" + MON + r")(\d{1,2})\b")

PAST_DAYS = 90      # a date up to ~3 months back counts as past (so overdue stays overdue);
                    # anything earlier in the calendar means next year
UPCOMING_DAYS = 14  # window for the "upcoming" view
BOX = {"open": "[ ]", "doing": "[~]", "done": "[x]"}
EFFORT = {"xs": 1, "s": 1, "m": 3, "l": 5, "xl": 8}   # effort size -> points
TODAY = date.today()


# ---------- dates ----------

def in_window(d):
    lo = TODAY - timedelta(PAST_DAYS)
    return lo <= d < lo + timedelta(365)


def resolve(month, day):
    """Year-less date -> real date: within the last ~3 months or the coming year."""
    for y in (TODAY.year - 1, TODAY.year, TODAY.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if in_window(d):
            return d
    return None


def resolve_after(month, day, start):
    """End of a range: first occurrence on or after the start."""
    for y in (start.year, start.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d >= start:
            return d
    return None


def month_end(y, m):
    return date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)


def loose_span(label):
    """~Q1 / ~Nov / ~wk43 -> (start, end) of the nearest matching period."""
    lo = TODAY - timedelta(PAST_DAYS)
    for y in (TODAY.year - 1, TODAY.year, TODAY.year + 1):
        try:
            if label.startswith("Q"):
                m = (int(label[1]) - 1) * 3 + 1
                s, e = date(y, m, 1), month_end(y, m + 2)
            elif label.startswith("wk"):
                s = date.fromisocalendar(y, int(label[2:]), 1)
                e = s + timedelta(days=6)
            else:
                m = MONTHS[label]
                s, e = date(y, m, 1), month_end(y, m)
        except ValueError:
            continue
        if e >= lo:
            return s, e
    return None


def next_reminder(spec):
    """Next date a reminder fires (today or later), or None if it has passed."""
    m = re.fullmatch("(" + MON + r")(\d{1,2})", spec)
    if m:
        d = resolve(MONTHS[m.group(1)], int(m.group(2)))
        return d if d and d >= TODAY else None
    parts = spec.lower().split()
    if parts[0] == "daily":
        return TODAY
    if parts[0] == "weekly":
        wd = WEEKDAYS.get(parts[1][:3])
        return None if wd is None else TODAY + timedelta(days=(wd - TODAY.weekday()) % 7)
    if parts[0] == "monthly":
        n = int(re.match(r"\d+", parts[1]).group())
        y, mo = TODAY.year, TODAY.month
        for _ in range(13):
            try:
                d = date(y, mo, n)
                if d >= TODAY:
                    return d
            except ValueError:
                pass
            mo += 1
            if mo > 12:
                mo, y = 1, y + 1
    return None


def fd(d):
    s = f"{MONTH_NAMES[d.month - 1]} {d.day}"
    return s if d.year == TODAY.year else f"{s} {d.year}"


def fspan(s, e, loose=None):
    if loose:
        return f"~{loose} ({fd(s)} - {fd(e)})"
    if s == e:
        return fd(s)
    if (s.year, s.month) == (e.year, e.month):
        return f"{fd(s).split(' ')[0]} {s.day}-{e.day}" + ("" if s.year == TODAY.year else f" {s.year}")
    return f"{fd(s)} - {fd(e)}"


# ---------- model ----------

class Task:
    def __init__(self, text, status="open", level=0, line=None):
        self.status, self.level, self.line = status, level, line   # line: 1-based, in the source text
        self.col = 0                     # where `text` starts in that line (set by parse)
        self.text = text                 # the text after the dash, tokens and all
        self.assignees, self.reminders, self.notes, self.children = [], [], [], []
        self.start = self.end = self.loose = None
        self.parent = self.project = None
        self.title = self._parse(text)

    def _parse(self, text):
        # Where each token sat in `text` (start, end), so an edit can change just that token.
        self.at = {"assignees": [], "reminders": [], "date": None, "effort": None}
        self.date_text = self.effort = None
        self.points = 0
        original, keep = text, list(range(len(text)))   # keep[i]: index in `original` of text[i]

        def cut(ms):
            nonlocal text, keep
            spans = [(keep[m.start()], keep[m.end() - 1] + 1) for m in ms]
            for m in reversed(ms):
                text, keep = text[:m.start()] + text[m.end():], keep[:m.start()] + keep[m.end():]
            return spans

        def cut_date(m):
            self.at["date"] = cut([m])[0]
            self.date_text = original[self.at["date"][0]:self.at["date"][1]]

        m = RE_EFFORT.search(text)           # first, so cutting initials can't glue it to a word
        if m:
            self.effort, self.points = m.group(1), EFFORT[m.group(1)]
            self.at["effort"] = cut([m])[0]
        ms = list(RE_ASSIGN.finditer(text))
        for m in ms:
            self.assignees += [a.strip() for a in m.group(1).split(",")]
        self.at["assignees"] = cut(ms)
        ms = list(RE_REMIND.finditer(text))
        for m in ms:
            self.reminders.append((m.group(1), next_reminder(m.group(1))))
        self.at["reminders"] = cut(ms)

        m = RE_RANGE.search(text)
        if m:
            s = resolve(MONTHS[m.group(1)], int(m.group(2)))
            em = MONTHS[m.group(3) or m.group(1)]
            e = s and resolve_after(em, int(m.group(4)), s)
            if e:
                self.start, self.end = s, e
                cut_date(m)
        if self.end is None:
            m = RE_LOOSE.search(text)
            span = m and loose_span(m.group(1))
            if span:
                self.start, self.end = span
                self.loose = m.group(1)
                cut_date(m)
        if self.end is None:
            m = RE_DATE.search(text)
            d = m and resolve(MONTHS[m.group(1)], int(m.group(2)))
            if d:
                self.start = self.end = d
                cut_date(m)
        return " ".join(text.split())

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def rollup(self):
        """Own dates stretched to cover all dated descendants."""
        spans = [(t.start, t.end) for t in self.walk() if t.end]
        if not spans:
            return None
        return min(s for s, _ in spans), max(e for _, e in spans)

    def span(self):
        """(start, end, how) where how is 'own', 'rollup' or 'parent'."""
        if self.end:
            r = self.rollup()
            return r[0], r[1], "own"
        r = self.rollup()
        if r:
            return r[0], r[1], "rollup"
        p = self.parent
        while p:
            if p.end:
                return p.start, p.end, "parent"
            p = p.parent
        return None

    def overdue(self):
        sp = self.span()
        return self.status != "done" and sp is not None and sp[1] < TODAY

    def label(self):
        s = self.title
        if self.assignees:
            s += " (" + ", ".join(self.assignees) + ")"
        return s


def effort_points(tasks):
    """(points not done yet, all points). Each task counts only its own effort (no rollup)."""
    tasks = list(tasks)
    return sum(t.points for t in tasks if t.status != "done"), sum(t.points for t in tasks)


def pts(n):
    return f"{n} pt" + ("" if n == 1 else "s")


class Project:
    def __init__(self, name, section, line=None):
        self.name, self.section, self.line = name, section, line   # line: the @ line (for "(no project)", its first line)
        self.tasks, self.notes = [], []

    def all_tasks(self):
        for t in self.tasks:
            yield from t.walk()


def parse(text):
    projects, section, project, stack = [], None, None, []

    def ensure_project():
        nonlocal project
        if project is None:
            project = Project("(no project)", section, n)
            projects.append(project)
        return project

    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        ws = raw[:len(raw) - len(raw.lstrip())]
        level = ws.count("\t") + ws.count(" ") // 4
        line = raw.strip()

        if line.startswith("@"):
            project = Project(line[1:].strip(), section, n)
            projects.append(project)
            stack = []
            continue

        if line.startswith("--"):
            target = stack[-1] if stack else ensure_project()   # the task right above
            target.notes.append(line[2:].strip())
            continue

        m = re.match(r"^([!~]?)-\s*(.*)$", line)
        if m:
            status = {"!": "done", "~": "doing", "": "open"}[m.group(1)]
            t = Task(m.group(2), status, level, n)
            t.col = len(ws) + m.start(2)
            t.text = m.group(2)              # the task's text after the dash, as written (for the `text` edit)
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                t.parent = stack[-1]
                stack[-1].children.append(t)
            else:
                ensure_project().tasks.append(t)
            t.project = ensure_project()
            stack.append(t)
            continue

        if level == 0:
            section = Task(line, line=n)   # reuse the date parsing for headings
            project, stack = None, []
            continue

        # indented plain text: treat as a note on the latest task
        target = stack[-1] if stack else ensure_project()
        target.notes.append(line)

    return projects


# ---------- views ----------

def view_projects(projects):
    out = ["PROJECTS", "========"]
    current = object()
    for p in projects:
        if p.section is not current:
            current = p.section
            if current:
                head = current.title
                if current.end:
                    head += f"   ({fspan(current.start, current.end, current.loose)})"
                out += ["", head, "-" * len(head)]
        tasks = list(p.all_tasks())
        done = sum(t.status == "done" for t in tasks)
        left, total = effort_points(tasks)
        out.append(f"\n@{p.name}   {done}/{len(tasks)} done" + (f"   {left} of {pts(total)} left" if total else ""))
        for n in p.notes:
            out.append(f"    -- {n}")

        def render(t, depth):
            line = "    " * depth + f"{BOX[t.status]} {t.label()}"
            if t.effort:
                line += f" [{t.effort.upper()}]"
            if t.end:
                line += f"   {fspan(t.start, t.end, t.loose)}"
            if t.overdue():
                line += "   OVERDUE"
            for spec, _ in t.reminders:
                line += f"   *{spec}"
            out.append(line)
            for n in t.notes:
                out.append("    " * (depth + 1) + f"-- {n}")
            for c in t.children:
                render(c, depth + 1)

        for t in p.tasks:
            render(t, 1)
    return out


def timeline_months():
    """The 12 (year, month) columns of the timeline, starting this month."""
    months = []
    y, m = TODAY.year, TODAY.month
    for _ in range(12):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


# ---------- periods (the page's Month / Season picker) ----------

SEASONS = [("Winter", 1, 4), ("Summer", 5, 8), ("Fall", 9, 12)]   # (name, first month, last month), inclusive


def period_from(obj):
    """Request value {kind, year, index} -> (kind, year, index), or None for "all dates".

    kind "month": index 1-12. kind "season": index 0-2 into SEASONS.
    With no year and index, the period that contains TODAY.
    """
    if obj is None:
        return None
    if not isinstance(obj, dict) or obj.get("kind") not in ("month", "season"):
        raise ValueError("period.kind must be month or season")
    kind, year, index = obj["kind"], obj.get("year"), obj.get("index")
    if year is None and index is None:
        return period_at(kind, TODAY)
    hi = 12 if kind == "month" else len(SEASONS) - 1
    lo = 1 if kind == "month" else 0
    if type(year) is not int or not 1900 <= year <= 2999 or type(index) is not int or not lo <= index <= hi:
        raise ValueError(f"bad period {obj!r}")
    return kind, year, index


def period_range(kind, year, index):
    """-> (first day, last day) of the period."""
    if kind == "month":
        return date(year, index, 1), month_end(year, index)
    _, a, b = SEASONS[index]
    return date(year, a, 1), month_end(year, b)


def period_at(kind, d):
    """The period of this kind that contains date d -> (kind, year, index)."""
    if kind == "month":
        return kind, d.year, d.month
    return kind, d.year, next(i for i, (_, a, b) in enumerate(SEASONS) if a <= d.month <= b)


def period_step(kind, year, index, step):
    """The period `step` periods later (negative = earlier), crossing years."""
    n, base = (12, 1) if kind == "month" else (len(SEASONS), 0)
    k = year * n + index - base + step
    return kind, k // n, k % n + base


def period_label(kind, year, index, short=False):
    """"Oct 2026"; "Fall 2026 (Sep-Dec)", or "Fall 2026" when short."""
    if kind == "month":
        return f"{MONTH_NAMES[index - 1]} {year}"
    name, a, b = SEASONS[index]
    return f"{name} {year}" + ("" if short else f" ({MONTH_NAMES[a - 1]}-{MONTH_NAMES[b - 1]})")


def period_columns(kind, year, index):
    """Timeline columns [(heading, start, end)]: the months of a season, or the weeks
    (Mon-Sun, cut to the month) of a month."""
    start, end = period_range(kind, year, index)
    if kind == "season":
        _, a, b = SEASONS[index]
        return [(MONTH_NAMES[m - 1], date(year, m, 1), month_end(year, m)) for m in range(a, b + 1)]
    cols, d = [], start
    while d <= end:
        e = min(d + timedelta(days=6 - d.weekday()), end)
        cols.append((f"{d.day}-{e.day}" if e > d else str(d.day), d, e))
        d = e + timedelta(days=1)
    return cols


def timeline_rows(projects, done=False):
    """Open tasks (and done ones with `done`) -> (rows sorted by date, unscheduled). Row = (start, end, project, task, how)."""
    rows, unscheduled = [], []
    for p in projects:
        for t in p.all_tasks():
            if t.status == "done" and not done:
                continue
            sp = t.span()
            if sp:
                rows.append((sp[0], sp[1], p, t, sp[2]))
            else:
                unscheduled.append((p, t))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows, unscheduled


def view_timeline(projects):
    months = timeline_months()
    first, last = date(*months[0], 1), month_end(*months[-1])
    W = 44
    header = " ".join(MONTH_NAMES[mo - 1][0] for _, mo in months)
    out = ["TIMELINE", "========",
           f"{fd(first).split(' ')[0]} {first.year} - {MONTH_NAMES[last.month - 1]} {last.year}"
           "   (# = scheduled that month; done tasks hidden)",
           "", " " * W + "  " + header]

    rows, unscheduled = timeline_rows(projects)

    for s, e, p, t, how in rows:
        bar = []
        for yy, mm in months:
            ms, me = date(yy, mm, 1), month_end(yy, mm)
            bar.append("#" if s <= me and e >= ms else ".")
        bar = " ".join(bar)
        if e < first:
            bar = "<" + bar[1:]
        if e > last:
            bar = bar[:-1] + ">"
        mark = "~" if t.status == "doing" else " "
        name = f"{mark}@{p.name}  {t.label()}"
        if len(name) > W:
            name = name[:W - 3] + "..."
        info = fspan(s, e, t.loose if how == "own" else None)
        if how == "parent":
            info += " (via parent)"
        if t.overdue():
            info += "  OVERDUE"
        out.append(f"{name:<{W}}  {bar}  {info}")

    if unscheduled:
        out += ["", "Unscheduled:"]
        for p, t in unscheduled:
            out.append(f"  {BOX[t.status]} @{p.name}  {t.label()}")
    return out


def people_groups(projects):
    """Open tasks per assignee, soonest first, (unassigned) last -> [(name, [(project, task)])]."""
    people = {}
    for p in projects:
        for t in p.all_tasks():
            if t.status == "done":
                continue
            for a in t.assignees or ["(unassigned)"]:
                people.setdefault(a, []).append((p, t))
    names = sorted(k for k in people if k != "(unassigned)")
    if "(unassigned)" in people:
        names.append("(unassigned)")
    far = date.max
    return [(n, sorted(people[n], key=lambda pt: (pt[1].span() or (far, far))[1])) for n in names]


def view_people(projects):
    out = ["PEOPLE", "======", "(open and in-progress tasks)"]
    for name, items in people_groups(projects):
        left = effort_points(t for _, t in items)[0]
        out.append(f"\n{name}   {len(items)} task(s)" + (f", {pts(left)}" if left else ""))
        for p, t in items:
            sp = t.span()
            size = f" [{t.effort.upper()}]" if t.effort else ""
            when = f"   {fspan(sp[0], sp[1])}" if sp else ""
            flag = "   OVERDUE" if t.overdue() else ""
            out.append(f"    {BOX[t.status]} @{p.name}  {t.title}{size}{when}{flag}")
    return out


def upcoming_groups(projects):
    """-> (horizon, overdue, due, doing, reminders); dated lists are (date, project, task[, spec])."""
    horizon = TODAY + timedelta(days=UPCOMING_DAYS)
    overdue, due, doing, reminders = [], [], [], []
    for p in projects:
        for t in p.all_tasks():
            if t.status == "done":
                continue
            sp = t.span()
            if t.overdue() and sp[2] != "parent":
                overdue.append((sp[1], p, t))
            elif sp and sp[2] != "parent" and TODAY <= sp[1] <= horizon:
                due.append((sp[1], p, t))
            if t.status == "doing":
                doing.append((p, t))
            for spec, d in t.reminders:
                if d and d <= horizon:
                    reminders.append((d, spec, p, t))
    return horizon, overdue, due, doing, reminders


def view_upcoming(projects):
    horizon, overdue, due, doing, reminders = upcoming_groups(projects)
    out = ["UPCOMING", "========", f"Today is {fd(TODAY)}; looking ahead {UPCOMING_DAYS} days to {fd(horizon)}"]

    def section(title, rows):
        out.append(f"\n{title}")
        if not rows:
            out.append("    (none)")
        out.extend(rows)

    section("Overdue", [f"    {fd(d):<9} @{p.name}  {t.label()}" for d, p, t in sorted(overdue, key=lambda r: r[0])])
    section("In progress", [f"    [~] @{p.name}  {t.label()}" for p, t in doing])
    section("Due soon", [f"    {fd(d):<9} @{p.name}  {t.label()}" for d, p, t in sorted(due, key=lambda r: r[0])])
    section("Reminders", [f"    {fd(d):<9} @{p.name}  {t.label()}   (*{spec})"
                          for d, spec, p, t in sorted(reminders, key=lambda r: r[0])])
    return out


# ---------- structured data (for the web page) ----------

def iso(d):
    return d.isoformat() if d else None


def task_data(t, keep=None):
    """A task and its subtasks as dicts. With `keep(task)`, only kept tasks and the
    ancestors of kept tasks are included (an ancestor that isn't kept gets "dim");
    returns None if nothing is kept."""
    kids = [k for k in (task_data(c, keep) for c in t.children) if k]
    if keep and not keep(t) and not kids:
        return None
    sp = t.span()
    d = {
        "title": t.title, "text": t.text, "status": t.status, "line": t.line, "date_text": t.date_text, "assignees": t.assignees, "notes": t.notes,
        "effort": t.effort, "points": t.points,
        "when": fspan(t.start, t.end, t.loose) if t.end else None, "loose": t.loose,
        "span": {"start": iso(sp[0]), "end": iso(sp[1]), "how": sp[2],
                 "label": fspan(sp[0], sp[1], t.loose if sp[2] == "own" else None)} if sp else None,
        "overdue": t.overdue(),
        "reminders": [{"spec": spec, "next": iso(d)} for spec, d in t.reminders],
        "children": kids,
    }
    if keep and not keep(t):
        d["dim"] = True
    return d


def flat(p, t):
    """A task with its project, for the flat lists (timeline, people, upcoming)."""
    d = task_data(t)
    d["project"] = p.name
    d["children"] = []
    return d


def to_data(projects, period=None):
    """Everything the four views show, as plain dicts and lists (JSON-ready).

    With `period` (from period_from), Projects, Timeline and People show only tasks
    whose span overlaps it, and the timeline's columns are that period.
    Upcoming is always the next UPCOMING_DAYS days.
    """
    if period:
        ps, pe = period_range(*period)
        cols = period_columns(*period)

        def inside(t):
            sp = t.span()
            return sp is not None and sp[0] <= pe and sp[1] >= ps
    else:
        months = timeline_months()
        cols = [(MONTH_NAMES[m - 1][0] + (f" {y % 100:02d}" if i == 0 or m == 1 else ""), date(y, m, 1), month_end(y, m))
                for i, (y, m) in enumerate(months)]
        inside = None

    sections, seen = [], {}
    for p in projects:
        tasks = list(p.all_tasks())
        shown = [d for d in (task_data(t, inside) for t in p.tasks) if d]
        if period and not shown:
            continue
        key = id(p.section)
        if key not in seen:
            sec = p.section
            seen[key] = {"title": sec.title if sec else None,
                         "when": fspan(sec.start, sec.end, sec.loose) if sec and sec.end else None,
                         "projects": []}
            sections.append(seen[key])
        seen[key]["projects"].append({
            "name": p.name, "line": p.line, "notes": p.notes,
            "done": sum(t.status == "done" for t in tasks), "total": len(tasks),
            "points": dict(zip(("left", "total"), effort_points(tasks))),
            "tasks": shown})

    first, last = cols[0][1], cols[-1][2]
    rows, unscheduled = timeline_rows(projects, done=True)   # the page hides done ones unless "Show done tasks"
    if period:
        rows = [r for r in rows if r[0] <= last and r[1] >= first]
        unscheduled = []
    people = [(n, [(p, t) for p, t in items if not inside or inside(t)]) for n, items in people_groups(projects)]
    horizon, overdue, due, doing, reminders = upcoming_groups(projects)
    return {
        "today": iso(TODAY), "today_label": fd(TODAY),
        "period": period and {
            "kind": period[0], "year": period[1], "index": period[2], "label": period_label(*period),
            "short": period_label(*period, short=True),
            "start": iso(ps), "end": iso(pe),
            "current": period == period_at(period[0], TODAY),
            **{k: dict(zip(("kind", "year", "index"), v), label=period_label(*v, short=True)) for k, v in (
                ("prev", period_step(*period, -1)), ("next", period_step(*period, 1)),
                ("now", period_at(period[0], TODAY)))}},
        "projects": sections,
        "targets": [{"name": p.name, "line": p.line, "section": p.section.title if p.section else None} for p in projects],
        "timeline": {
            "columns": [{"head": h, "start": iso(a), "end": iso(b)} for h, a, b in cols],
            "rows": [dict(flat(p, t), bar=[s <= b and e >= a for _, a, b in cols],
                          before=e < first, after=e > last) for s, e, p, t, _ in rows],
            "unscheduled": [flat(p, t) for p, t in unscheduled]},
        "people": [{"name": n, "points": effort_points(t for _, t in items)[0], "tasks": [flat(p, t) for p, t in items]}
                   for n, items in people if items],
        "upcoming": {
            "horizon": fd(horizon), "days": UPCOMING_DAYS,
            "overdue": [flat(p, t) for _, p, t in sorted(overdue, key=lambda r: r[0])],
            "due": [flat(p, t) for _, p, t in sorted(due, key=lambda r: r[0])],
            "reminders": [dict(flat(p, t), spec=spec, date=fd(d)) for d, spec, p, t in sorted(reminders, key=lambda r: r[0])],
            "doing": [flat(p, t) for p, t in doing]},
    }


# ---------- editing (only on an explicit user action) ----------

STATUS_MARK = {"open": "", "doing": "~", "done": "!"}


class EditError(ValueError):
    """The edit can't be applied to this text (stale line, not a task, bad status)."""


def _task_at(text, line, title):
    """-> (lines with their endings, the parsed task on `line`), or EditError."""
    lines = text.splitlines(keepends=True)      # same split points as parse()
    if type(line) is not int or not 1 <= line <= len(lines):
        raise EditError(f"line {line!r} is not in the text")
    task = _find(text, line)
    if task is None or (title is not None and task.title != title):
        raise EditError(f"line {line} is no longer that task (the text has changed)")
    return lines, task


def _find(text, line):
    return next((t for p in parse(text) for t in p.all_tasks() if t.line == line), None)


def _content_end(raw):
    return len(raw.rstrip())                    # before trailing whitespace and the line ending


def _drop(raw, s, e, col):
    """`raw` without the token at [s, e) and the spaces before it (but not before `col`)."""
    while s > col and raw[s - 1] in " \t":
        s -= 1
    return raw[:s] + raw[e:]


def set_status(text, line, status, title=None):
    """Return `text` with the task on `line` (1-based) set to `status`.

    Only the status mark before the task's dash changes. Every other character
    of the text, including that line's indentation, wording and line ending,
    stays exactly as it was. If `title` is given it must match the task's parsed
    title, so an edit made from an out-of-date view is refused, not misapplied.
    """
    if status not in STATUS_MARK:
        raise EditError(f"unknown status {status!r} (use open, doing or done)")
    lines, _ = _task_at(text, line, title)
    raw = lines[line - 1]
    ws = raw[:len(raw) - len(raw.lstrip())]
    body = raw[len(ws):]
    if body[0] in "!~":
        body = body[1:]
    lines[line - 1] = ws + STATUS_MARK[status] + body
    return "".join(lines)


def set_date(text, line, when, title=None):
    """Set, replace or (with an empty `when`) clear the task's own date token.

    An existing date token is replaced in place. A new one goes before the
    first reminder, or at the end of the line. Nothing else on the line moves.
    """
    lines, t = _task_at(text, line, title)
    when = when.strip()
    probe = Task("x " + when) if when else None
    if probe and (probe.end is None or probe.title != "x"):
        raise EditError(f"{when!r} is not a date (use Oct24, Oct23--26, Oct23--Nov03, ~Q1, ~Nov or ~wk43)")
    raw = lines[line - 1]
    if t.at["date"]:
        s, e = (t.col + i for i in t.at["date"])
        raw = raw[:s] + when + raw[e:] if when else _drop(raw, s, e, t.col)
    elif not when:
        raise EditError("that task has no date to clear")
    elif t.at["reminders"]:
        p = t.col + t.at["reminders"][0][0]
        raw = raw[:p] + when + " " + raw[p:]
    else:
        p = _content_end(raw)
        raw = raw[:p] + " " + when + raw[p:]
    lines[line - 1] = raw
    out = "".join(lines)
    n = _find(out, line)
    if (n.start, n.end) != ((probe.start, probe.end) if probe else (None, None)):
        raise EditError(f"the line wouldn't read as {when or 'undated'!r}; another date-like word "
                        "earlier in the line takes priority, so edit it by hand")
    return out


def add_assignees(text, line, initials, title=None):
    """Add initials ("RT" or "RT, JS") to the task.

    They join the task's last (...) group, or a new group goes before the
    first effort, date or reminder (as in `finish proposal (KA) (m) Oct24`), or at the end.
    """
    lines, t = _task_at(text, line, title)
    new = _initials(initials)
    if not new:
        raise EditError(f"{initials!r}: initials are 1-4 capital letters, separated by commas")
    new = [a for a in new if a not in t.assignees]
    if not new:
        raise EditError("already assigned")
    raw = lines[line - 1]
    if t.at["assignees"]:
        s, e = (t.col + i for i in t.at["assignees"][-1])
        p = s + max(i for i, c in enumerate(raw[s:e]) if c.isupper()) + 1
        raw = raw[:p] + ", " + ", ".join(new) + raw[p:]
    else:
        tokens = t.at["reminders"] + [t.at[k] for k in ("effort", "date") if t.at[k]]
        group = "(" + ", ".join(new) + ")"
        if tokens:
            p = t.col + min(s for s, _ in tokens)
            raw = raw[:p] + group + " " + raw[p:]
        else:
            p = _content_end(raw)
            raw = raw[:p] + " " + group + raw[p:]
    lines[line - 1] = raw
    out = "".join(lines)
    if _find(out, line).assignees != t.assignees + new:
        raise EditError("the initials wouldn't read back correctly, so edit the line by hand")
    return out


def set_effort(text, line, size, title=None):
    """Set, replace or (with an empty `size`) clear the task's effort: xs, s, m, l or xl.

    An existing (size) token is replaced in place. A new one goes before the
    first date or reminder (as in `finish proposal (KA) (m) Oct24`), or at the
    end of the line. Nothing else on the line moves.
    """
    lines, t = _task_at(text, line, title)
    size = size.strip().strip("()").strip().lower()
    if size and size not in EFFORT:
        raise EditError(f"{size!r} is not an effort (use xs, s, m, l or xl; empty clears it)")
    raw = lines[line - 1]
    token = f"({size})"
    if t.at["effort"]:
        s, e = (t.col + i for i in t.at["effort"])
        raw = raw[:s] + token + raw[e:] if size else _drop(raw, s, e, t.col)
    elif not size:
        raise EditError("that task has no effort to clear")
    else:
        tokens = t.at["reminders"] + ([t.at["date"]] if t.at["date"] else [])
        if tokens:
            p = t.col + min(s for s, _ in tokens)
            raw = raw[:p] + ("" if raw[p - 1].isspace() else " ") + token + " " + raw[p:]
        else:
            p = _content_end(raw)
            raw = raw[:p] + " " + token + raw[p:]
    lines[line - 1] = raw
    out = "".join(lines)
    n = _find(out, line)
    if (n.effort, n.title, n.start, n.end) != (size or None, t.title, t.start, t.end):
        raise EditError("the effort wouldn't read back correctly, so edit the line by hand")
    return out


def _initials(value):
    """ "KA, RT" or "KA RT" -> ["KA", "RT"] (duplicates dropped); EditError if any isn't 1-4 capitals."""
    found = [a for a in re.split(r"[\s,]+", value.strip()) if a]
    if any(not re.fullmatch(r"[A-Z]{1,4}", a) for a in found):
        raise EditError(f"{value!r}: initials are 1-4 capital letters, separated by commas")
    return [a for i, a in enumerate(found) if a not in found[:i]]


def set_assignees(text, line, initials, title=None):
    """Replace the task's initials with `initials` ("KA, RT"); an empty value removes them.

    The first (...) group takes the new list in place and any later groups are
    removed with the spaces before them. With no group yet, the initials are
    added as add_assignees does. Nothing else on the line moves.
    """
    lines, t = _task_at(text, line, title)
    new = _initials(initials)
    if not new and not t.assignees:
        raise EditError("that task has no initials to remove")
    if new == t.assignees:
        return text
    if not t.at["assignees"]:
        return add_assignees(text, line, ", ".join(new), title)
    raw = lines[line - 1]
    groups = [(t.col + s, t.col + e) for s, e in t.at["assignees"]]
    for s, e in reversed(groups[1:]):          # from the end, so earlier positions stay valid
        raw = _drop(raw, s, e, t.col)
    s, e = groups[0]
    raw = raw[:s] + "(" + ", ".join(new) + ")" + raw[e:] if new else _drop(raw, s, e, t.col)
    lines[line - 1] = raw
    out = "".join(lines)
    n = _find(out, line)
    if (n.assignees, n.title, n.start, n.end, n.effort) != (new, t.title, t.start, t.end, t.effort):
        raise EditError("the initials wouldn't read back correctly, so edit the line by hand")
    return out


def set_text(text, line, task_text, title=None):
    """Replace the task's text after the dash (title and tokens, as written) with `task_text`.

    The indentation, status mark, dash, trailing whitespace and line ending stay;
    no other line changes. Refused if the line wouldn't read back as a task at
    the same place in the outline.
    """
    lines, t = _task_at(text, line, title)
    task_text = task_text.strip()
    if not task_text or any(c in task_text for c in "\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"):
        raise EditError("a task is one line of text (to remove a task, edit the text by hand)")
    raw = lines[line - 1]
    lines[line - 1] = raw[:t.col] + task_text + raw[_content_end(raw):]
    out = "".join(lines)
    n = _find(out, line)
    same = lambda a, b: (a and a.line) == (b and b.line)
    if n is None or n.level != t.level or n.status != t.status or n.text != task_text \
            or not same(n.parent, t.parent) or n.project.line != t.project.line:
        raise EditError("the line wouldn't read back as that task, so edit it by hand")
    return out


def add_subtask(text, line, task_text, title=None):
    """Add `- task_text` as the last subtask of the task on `line`.

    The new line goes after the task's last subtask (and its notes), indented
    one tab deeper than the task. Existing lines are not changed, except that
    a final line with no line ending gets one.
    """
    lines, t = _task_at(text, line, title)
    task_text = task_text.strip()
    if not task_text or any(c in task_text for c in "\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"):
        raise EditError("a subtask is one line of text")
    raw = lines[line - 1]
    ws = raw[:len(raw) - len(raw.lstrip())]
    indent = ws + ("    " if ws and "\t" not in ws else "\t")
    ending = raw[_content_end(raw):].lstrip(" \t") or "\n"
    last = line                                 # last non-blank line of the task's subtree
    for i in range(line, len(lines)):
        r = lines[i]
        c = r.strip()
        if not c:
            continue
        rws = r[:len(r) - len(r.lstrip())]
        lvl = rws.count("\t") + rws.count(" ") // 4
        if c.startswith("@") or (not c.startswith("--") and re.match(r"^[!~]?-", c) and lvl <= t.level) \
                or (lvl == 0 and not c.startswith("--") and not re.match(r"^[!~]?-", c)):
            break
        last = i + 1
    if not lines[last - 1].endswith(tuple("\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")):
        lines[last - 1] += ending
        new_line = indent + "- " + task_text
    else:
        new_line = indent + "- " + task_text + ending
    lines.insert(last, new_line)
    out = "".join(lines)
    n = _find(out, last + 1)
    if n is None or n.parent is None or n.parent.line != line:
        raise EditError("the new subtask wouldn't land under that task, so add it by hand")
    return out


def add_task(text, line, task_text, title=None):
    """Add `- task_text` as the last top-level task of the project on `line` (its @ line).

    `title` is the project's name. The new line goes after the project's last line
    (its tasks and notes, before blank lines and the next @ or heading), indented
    like the project's first task. Existing lines are not changed, except that a
    final line with no line ending gets one.
    """
    lines = text.splitlines(keepends=True)
    if type(line) is not int or not 1 <= line <= len(lines):
        raise EditError(f"line {line!r} is not in the text")
    p = next((p for p in parse(text) if p.line == line), None)
    if p is None or (title is not None and p.name != title):
        raise EditError(f"line {line} is no longer that project (the text has changed)")
    task_text = task_text.strip()
    if not task_text or any(c in task_text for c in "\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"):
        raise EditError("a task is one line of text")
    raw = lines[line - 1]
    first = p.tasks[0] if p.tasks else None
    fr = lines[first.line - 1] if first else ""
    indent = fr[:len(fr) - len(fr.lstrip())]
    ending = raw[_content_end(raw):].lstrip(" \t") or "\n"
    last = line                                 # last non-blank line of the project
    for i in range(line, len(lines)):
        r = lines[i]
        c = r.strip()
        if not c:
            continue
        rws = r[:len(r) - len(r.lstrip())]
        lvl = rws.count("\t") + rws.count(" ") // 4
        if c.startswith("@") or (lvl == 0 and not c.startswith("--") and not re.match(r"^[!~]?-", c)):
            break
        last = i + 1
    if not lines[last - 1].endswith(tuple("\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")):
        lines[last - 1] += ending
        new_line = indent + "- " + task_text
    else:
        new_line = indent + "- " + task_text + ending
    lines.insert(last, new_line)
    out = "".join(lines)
    n = _find(out, last + 1)
    if n is None or n.parent is not None or n.project.line != line:
        raise EditError("the new task wouldn't land in that project, so add it by hand")
    return out


EDITS = {"text": set_text, "status": set_status, "date": set_date, "effort": set_effort, "assign": add_assignees, "who": set_assignees,
         "subtask": add_subtask, "task": add_task}


# ---------- the notes file (--serve notes.txt) ----------

class FileConflict(Exception):
    """The file on disk is not the version the page last loaded or saved."""


def file_version(data):
    import hashlib
    return None if data is None else hashlib.sha256(data).hexdigest()


def read_notes(path):
    """-> (text, version); ("", None) if the file doesn't exist yet. Text is exact (no newline translation)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return "", None
    return data.decode("utf-8"), file_version(data)


def write_notes(path, text, version, force=False):
    """Write `text` to `path` if the file is still at `version` (or `force`); -> new version.

    Browsers turn every line ending in a text box into \\n, so if the file on disk
    uses \\r\\n throughout, the text is written back with \\r\\n. The write is atomic
    (temp file, then rename) and keeps the file's permissions.
    """
    import tempfile
    try:
        with open(path, "rb") as f:
            old = f.read()
    except FileNotFoundError:
        old = None
    if not force and file_version(old) != version:
        raise FileConflict("the file changed on disk since it was loaded")
    if old and b"\r\n" in old and old.count(b"\r\n") == old.count(b"\n") and "\r" not in text:
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".planner-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if old is not None:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return file_version(data)


# ---------- web page ----------

def set_today(val):
    """--today value: Oct12 or 2026-10-12."""
    global TODAY
    m = re.fullmatch("(" + MON + r")(\d{1,2})", val)
    TODAY = date(date.today().year, MONTHS[m.group(1)], int(m.group(2))) if m else date.fromisoformat(val)


NOTE_SUFFIXES = (".txt", ".md", ".markdown")


def make_server(port, notes_path=None, browse_root=None):
    """The local server (127.0.0.1 only). Port 0 picks a free port.

    With `notes_path`, GET/POST /api/file read and save that one file. Without
    it, the page can list folders under `browse_root` (default: the home folder)
    with GET /api/browse, open .txt / .md files there with POST /api/open (several
    at once: the page shows them as tabs and autosaves them; `create` makes a new
    empty one), and close them with POST /api/close; /api/file then reads and saves
    an open file, named by `path`. Only open files are ever written.
    """
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pathlib import Path
    from urllib.parse import parse_qs, urlsplit

    default_today = TODAY
    page = Path(__file__).resolve().parent / "web" / "index.html"
    root = os.path.realpath(browse_root or os.path.expanduser("~"))
    opened = []                                     # files opened from the page (resolved paths), most recent last

    def inside(p):
        """`p` resolved, if it is `root` or under it; else None."""
        p = os.path.realpath(p)
        return p if p == root or p.startswith(root.rstrip(os.sep) + os.sep) else None

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _trusted(self):
            """Only this page may use the API: blocks other sites (Origin) and DNS rebinding (Host)."""
            hosts = {f"localhost:{self.server.server_address[1]}", f"127.0.0.1:{self.server.server_address[1]}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") in hosts and (origin is None or origin in {"http://" + h for h in hosts}):
                return True
            self._json(403, {"error": "forbidden"})
            return False

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/file":
                if not self._trusted():
                    return
                self._file(parse_qs(urlsplit(self.path).query).get("path", [None])[0])
            elif path == "/api/browse":
                if not self._trusted():
                    return
                self._browse(parse_qs(urlsplit(self.path).query).get("dir", [None])[0])
            elif path == "/api/example":            # the sample notes, for the page's "Load the example"
                if not self._trusted():
                    return
                self._json(200, {"text": (Path(__file__).resolve().parent / "example.txt").read_text(encoding="utf-8")})
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path not in ("/api/parse", "/api/edit", "/api/file", "/api/open", "/api/close"):
                return self._send(404, b"not found", "text/plain")
            if not self._trusted():
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "send JSON"})
            global TODAY
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if self.path == "/api/file":
                    return self._save(req)
                if self.path == "/api/open":
                    return self._open(req)
                if self.path == "/api/close":
                    return self._close(req)
                TODAY = default_today
                if req.get("today"):
                    set_today(req["today"])
                text = req.get("text", "")
                period = period_from(req.get("period"))
                if self.path == "/api/parse":
                    return self._json(200, to_data(parse(text), period))
                op = EDITS.get(req["op"])
                if op is None:
                    raise EditError(f"unknown edit {req['op']!r} ({', '.join(EDITS)})")
                if not isinstance(req["value"], str):
                    raise EditError("value must be text")
                text = op(text, req["line"], req["value"], req.get("title"))
                self._json(200, {"text": text, "data": to_data(parse(text), period)})
            except EditError as e:
                self._json(409, {"error": str(e)})
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                self._json(400, {"error": f"bad request: {e}"})

        def _target(self, path):
            """The file a request means: the command-line file, or `path` if it is open; else None."""
            if notes_path is not None:
                return notes_path if path in (None, notes_path) else None
            p = isinstance(path, str) and os.path.realpath(path)
            return p if p in opened else None

        def _not_open(self, path):
            """409 notOpen: e.g. the server was restarted; the page opens the file again and retries."""
            self._json(409, {"error": f"{os.path.basename(str(path))} isn't open", "notOpen": True})

        def _file(self, path=None):
            """{name, path, text, version, picked} for the command-line file or an open file;
            {name: null} without a path and without a command-line file."""
            if path is None and notes_path is None:
                return self._json(200, {"name": None})
            p = self._target(path)
            if p is None:
                return self._not_open(path)
            try:
                text, version = read_notes(p)
            except (OSError, UnicodeDecodeError) as e:
                return self._json(500, {"error": f"can't read {p}: {e}"})
            self._json(200, {"name": os.path.basename(p), "path": p, "text": text, "version": version,
                             "picked": notes_path is None})

        def _browse(self, folder):
            """Folders and notes files in `folder` (under the browse root): {dir, parent, entries}."""
            if notes_path is not None:
                return self._json(409, {"error": "a notes file was given on the command line"})
            start = os.path.dirname(opened[-1]) if opened else (os.getcwd() if inside(os.getcwd()) else root)
            d = inside(folder or start)
            if d is None or not os.path.isdir(d):
                return self._json(403, {"error": "you can only open files in your home folder"})
            try:
                found = list(os.scandir(d))
            except OSError as e:
                return self._json(403, {"error": f"can't open that folder: {e.strerror or e}"})
            entries = []
            for e in found:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir():
                        entries.append({"name": e.name, "kind": "dir", "path": os.path.join(d, e.name)})
                    elif e.is_file() and e.name.lower().endswith(NOTE_SUFFIXES):
                        entries.append({"name": e.name, "kind": "file", "path": os.path.join(d, e.name)})
                except OSError:
                    continue
            entries.sort(key=lambda x: (x["kind"] != "dir", x["name"].casefold()))
            self._json(200, {"dir": d, "home": root, "parent": None if d == root else os.path.dirname(d), "entries": entries})

        def _open(self, req):
            """Open the notes file at req["path"] (under the browse root) and return it; opening an
            open file again is fine. With "create", make it first (empty; refused if it exists)."""
            if notes_path is not None:
                return self._json(409, {"error": "a notes file was given on the command line"})
            p = isinstance(req.get("path"), str) and inside(req["path"])
            if not p or not p.lower().endswith(NOTE_SUFFIXES) or not os.path.isdir(os.path.dirname(p)):
                return self._json(403, {"error": "you can open .txt and .md files in your home folder"})
            if req.get("create"):
                if os.path.lexists(p):
                    return self._json(409, {"error": f"{os.path.basename(p)} already exists"})
                try:
                    write_notes(p, "", None)
                except (OSError, FileConflict) as e:
                    return self._json(500, {"error": f"can't create {os.path.basename(p)}: {e}"})
            if not os.path.isfile(p):
                return self._json(404, {"error": f"{os.path.basename(p)} isn't there any more"})
            if p in opened:
                opened.remove(p)
            opened.append(p)
            self._file(p)

        def _close(self, req):
            """Stop serving the open file req["path"] (nothing is written)."""
            p = isinstance(req.get("path"), str) and os.path.realpath(req["path"])
            if p in opened:
                opened.remove(p)
            self._json(200, {"closed": True})

        def _save(self, req):
            p = self._target(req.get("path"))
            if p is None:
                return self._not_open(req.get("path"))
            if not isinstance(req.get("text"), str):
                return self._json(400, {"error": "bad request: text must be a string"})
            try:
                version = write_notes(p, req["text"], req.get("version"), bool(req.get("force")))
            except FileConflict as e:
                _, current = read_notes(p)
                return self._json(409, {"error": str(e), "conflict": True, "version": current})
            except OSError as e:
                return self._json(500, {"error": f"can't save {p}: {e}"})
            self._json(200, {"version": version})

        def log_message(self, *args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def serve(port, notes_path=None):
    import threading
    import webbrowser

    server = make_server(port, notes_path)
    url = f"http://localhost:{port}"
    print(f"Planner running at {url}  (Ctrl-C to stop)")
    if notes_path:
        print(f"Editing {notes_path}" + ("" if os.path.exists(notes_path) else " (new file, created on first Save)"))
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


VIEWS = {"projects": view_projects, "timeline": view_timeline,
         "people": view_people, "upcoming": view_upcoming}


def take_option(args, flag):
    """Remove `flag VALUE` from args and return VALUE (None if the flag is absent)."""
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args) or args[i + 1].startswith("--"):
        sys.exit(f"planner.py: {flag} needs a value")
    val = args[i + 1]
    del args[i:i + 2]
    return val


def main(argv):
    args, path, chosen = list(argv[1:]), None, []
    today = take_option(args, "--today")
    if today is not None:
        try:
            set_today(today)
        except ValueError:
            sys.exit(f"planner.py: bad --today value {today!r} (use Oct12 or 2026-10-12)")
    if "--serve" in args:
        args.remove("--serve")
        port = take_option(args, "--port") or "8765"
        if not port.isdigit() or not 0 < int(port) < 65536:
            sys.exit(f"planner.py: bad --port value {port!r}")
        if len(args) > 1 or any(a.lower() in VIEWS for a in args):
            sys.exit("planner.py: --serve takes at most one notes file (and no view names)")
        notes = os.path.realpath(args[0]) if args else None    # follow a symlink to the real file
        if notes:
            if os.path.isdir(notes) or not os.path.isdir(os.path.dirname(notes)):
                sys.exit(f"planner.py: can't edit {args[0]!r}: not a file in an existing folder")
            try:
                read_notes(notes)
            except (OSError, UnicodeDecodeError) as e:
                sys.exit(f"planner.py: can't read {args[0]!r}: {e}")
        return serve(int(port), notes)
    for a in args:
        if a.lower() in VIEWS:
            chosen.append(a.lower())
        elif not os.path.isfile(a):
            sys.exit(f"planner.py: {a!r} is not a file or a view ({' | '.join(VIEWS)})")
        elif path is not None:
            sys.exit(f"planner.py: only one notes file at a time (got {path!r} and {a!r})")
        else:
            path = a

    if path:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            sys.exit(f"planner.py: can't read {path!r}: {e}")
    else:
        print("Paste your notes, then press Ctrl-D (Mac/Linux) or Ctrl-Z then Enter (Windows):\n",
              file=sys.stderr)
        text = sys.stdin.read()

    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    projects = parse(text)
    if not projects:
        print("No projects or tasks found.")
        return
    for name in chosen or list(VIEWS):
        print("\n".join(VIEWS[name](projects)))
        print()


if __name__ == "__main__":
    main(sys.argv)
