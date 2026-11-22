#!/usr/bin/env python3
"""
planner.py (KAFEEN Planner) - turn plain-text planning notes into five views:
projects, timeline, people, what's coming up, and the week.
Standard library only (Python 3.8+).

Notes files end in .kf (the KAFEEN format; .txt works the same).

USAGE
  python planner.py                    paste your notes, then press
                                       Ctrl-D (Mac/Linux) or Ctrl-Z then Enter (Windows)
  python planner.py notes.txt          read notes from a file instead
  python planner.py ./Projects week    a projects folder: the views over every project (week: with habits)
  python planner.py notes.txt people   show one view only:
                                       projects | timeline | people | upcoming | week
  --today Oct10                        pretend today is another date (for testing); without it the
                                       server follows the clock, moving on at midnight
  --import notes.txt [FOLDER] [--split]  make a project from notes.txt in Projects/, or in FOLDER
                                       (--split: one project per @ line)
  --serve [--port 8765] [--host ADDR]  open the web page on the Projects folder next to planner.py (made if it's
                                       missing): one sub-folder per project (backlog.kf, quicknote.kf, habits.kf,
                                       notes/, archive/YYYY.kf). --host 0.0.0.0 serves the whole network (no
                                       login; for a trusted LAN). Click the logo for the projects: All projects
                                       (every backlog together) and each project's pages
  --serve notes.txt [--port 8765] [--host ADDR]  the web page on that one file instead; Save writes back to it
                                       The page: tabs Projects / Timeline / People / Upcoming / Week;
                                       click a task's box, title or Who / Effort / Date / + cells
                                       to edit it (Tab moves between them), + Add task (with Who / Effort /
                                       Date fields) to add tasks one after another, fold any level in Projects,
                                       sort a project's tasks by status from its heading,
                                       and plan tasks for days in Week (and print the plan on one page)
                                       The page is live: notes changed on disk show at once (2.1.0)
  --setup-hub [FOLDER] [--new-code]    make the Projects folder (or FOLDER) the sync hub; prints the pairing code
  --serve --hub [--host ADDR]          serve the hub: paired devices keep their Projects folder in step (2.1.1)
  --autostart on|off [--hub]           start KAFEEN (or the hub) when you log in: systemd (Linux), LaunchAgent
                                       (macOS), Startup folder (Windows) (2.1.4). --no-browser: --serve opens none
  --pair HUB CODE [--name NAME]        pair this computer's Projects folder with the hub (2.1.2); then --serve
                                       keeps it in step, live, and catches up after being offline. --unpair stops

NOTE FORMAT (quick reference)
  Fall Planning  Sep01--Dec19   heading: left edge, no marker, optional dates
  @HDC                          project: runs until the next @ or heading
  - task  ~- task  !- task      open / in progress / done
  /- task                       on hold: paused with its subtasks (never overdue, not upcoming)
  (!)- task                     notable: circled in purple (before any status mark)
  <Tab>                         one level deeper = subtask
  -- text                       note on the task above (never a task)
  (KA)  (KA, RT)                assignees
  (xs) (s) (m) (l) (xl)         effort: 1, 2, 3, 5 or 8 points (lowercase only)
  Oct24                         due date
  Oct23--26  Oct23--Nov03       date range
  ~Q1  ~T1  ~Nov  ~wk43         loose date: sometime in that period (T1-T3: trimesters
                                Winter Jan-Apr, Summer May-Aug, Fall Sep-Dec)
  *Oct17  *weekly Fri  *monthly 1st  *daily     reminder
  *weekdays  *weekly Mon, Wed, Fri                repeating: in habits.kf, a habit's frequency
  -- done Nov02 Nov03           a habit's log: the days it was done
  - gym (m) *weekly Mon, Wed   a habit's effort counts once per day due (the Planner's totals); habits show in Upcoming
  >Oct14  >wk45  >Nov  >T3      planned: when you mean to work on it (the Planner; separate from the date);
                                several are fine: >Oct14 >Oct16
  ^wk45  ^Nov  ^T3  ^yr         a top priority for that week, month, trimester or this year
"""
import os
import re
import sys
from datetime import date, datetime, timedelta

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS = {m: i for i, m in enumerate(MONTH_NAMES, 1)}
MON = "(?:" + "|".join(MONTH_NAMES) + ")"
WEEKDAYS = {d: i for i, d in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}

RE_TASK = re.compile(r"^(\(!\))?([!~/]?)-\s*(.*)$")             # a task line's content: (!) notable, ! done, ~ doing, / on hold
RE_EFFORT = re.compile(r"(?<!\w)\(\s*(xs|s|m|l|xl)\s*\)")     # lowercase, so (S) stays initials
RE_ASSIGN = re.compile(r"\(\s*([A-Z]{1,4}(?:\s*,\s*[A-Z]{1,4})*)\s*\)")
DAYNAME = r"(?:[Mm]on|[Tt]ue|[Ww]ed|[Tt]hu|[Ff]ri|[Ss]at|[Ss]un)[a-z]*"
RE_REMIND = re.compile(r"\*(daily|weekdays|weekly\s+[A-Za-z]{3}[a-z]*(?:\s*,\s*" + DAYNAME + r")*|monthly\s+\d{1,2}(?:st|nd|rd|th)?|"
                       + MON + r"\d{1,2})\b")
RE_LOG = re.compile(r"done((?:\s+" + MON + r"\d{1,2})+)\s*")       # a habit's log note: -- done Nov02 Nov03
LOG_END = None       # the last day a habit log can mean (None: TODAY; an archive page: the end of its year)
RE_PLAN = re.compile(r"(?<!\S)>(?:(" + MON + r")(\d{1,2})|wk(\d{1,2})|(" + MON + r")|(T[1-3]))\b")   # >Oct14 >wk45 >Nov >T3
RE_PRIO = re.compile(r"(?<!\S)\^(wk\d{1,2}|" + MON + r"|T[1-3]|yr)\b")             # ^wk45 ^Nov ^T3 ^yr: a top priority for that period
RE_RANGE = re.compile(r"(?<![\w*~>])(" + MON + r")(\d{1,2})--(" + MON + r")?(\d{1,2})\b")
RE_LOOSE = re.compile(r"(?<!\S)~(Q[1-4]|T[1-3]|wk\d{1,2}|" + MON + r")\b")
RE_DATE = re.compile(r"(?<![\w*~>])(" + MON + r")(\d{1,2})\b")

PAST_DAYS = 90      # a date up to ~3 months back counts as past (so overdue stays overdue);
                    # anything earlier in the calendar means next year
UPCOMING_DAYS = 14  # window for the "upcoming" view
SCAN_SECONDS = 2    # 2.1.0: how often the server looks for notes changed on disk (by hand, or by sync)
BOX = {"open": "[ ]", "doing": "[~]", "done": "[x]", "hold": "[/]"}


def box(t):
    """A task's box in the text views: [/] for one on hold, also through its parent (unless done)."""
    return BOX["hold"] if t.held and t.status != "done" else BOX[t.status]
EFFORT = {"xs": 1, "s": 2, "m": 3, "l": 5, "xl": 8}   # effort size -> points
TODAY = date.today()
TODAY_PINNED = False            # --today given: the server keeps that day; otherwise it reads the clock per request


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
    """~Q1 / ~T1 / ~Nov / ~wk43 -> (start, end) of the nearest matching period.
    T1-T3 are the trimesters, the same months as SEASONS (T1 = Winter, Jan-Apr)."""
    lo = TODAY - timedelta(PAST_DAYS)
    for y in (TODAY.year - 1, TODAY.year, TODAY.year + 1):
        try:
            if label.startswith("Q"):
                m = (int(label[1]) - 1) * 3 + 1
                s, e = date(y, m, 1), month_end(y, m + 2)
            elif label.startswith("T"):
                _, a, b = SEASONS[int(label[1]) - 1]
                s, e = date(y, a, 1), month_end(y, b)
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


PLAN_RANK = {"day": 0, "week": 1, "month": 2, "season": 3, "year": 4}


def plan_of(m):
    """A RE_PLAN match -> (kind, token, start, end): day (>Oct14), week (>wk45), month (>Nov) or
    season (>T3), resolved like dates and loose dates; None if there is no such date."""
    if m.group(1):
        d = resolve(MONTHS[m.group(1)], int(m.group(2)))
        return d and ("day", m.group(1) + m.group(2), d, d)
    token = "wk" + m.group(3) if m.group(3) else m.group(4) or m.group(5)
    span = loose_span(token)
    kind = "week" if m.group(3) else "month" if m.group(4) else "season"
    return span and (kind, token, span[0], span[1])


def priority_of(token):
    """^wk45 / ^Nov / ^T3 / ^yr (without the ^) -> (kind, start, end); ^yr is TODAY's year. None if invalid."""
    if token == "yr":
        return "year", date(TODAY.year, 1, 1), date(TODAY.year, 12, 31)
    span = loose_span(token)
    kind = "week" if token.startswith("wk") else "season" if token.startswith("T") else "month"
    return span and (kind, span[0], span[1])


def plan_labels(t):
    """All of a task's plans, earliest first, once each: "Oct 14, Oct 16" ("" without any)."""
    seen = sorted({(a, b, k) for k, _, a, b in t.plans})
    return ", ".join(plan_label(k, a, b) for a, b, k in seen)


def plan_label(kind, start, end):
    """How a plan reads: "Oct 14", "Nov 2 - 8", "Nov", "Fall" (with the year when it isn't TODAY's)."""
    if kind == "day":
        return fd(start)
    if kind == "week":
        return fspan(start, end)
    yr = "" if start.year == TODAY.year else f" {start.year}"
    if kind == "month":
        return MONTH_NAMES[start.month - 1] + yr
    if kind == "season":
        return next(n for n, a, _ in SEASONS if a == start.month) + yr
    return str(start.year)


def repeats(spec):
    """Is this reminder a repeating one (a habit's frequency), not a one-off *Oct13?"""
    return not re.fullmatch(MON + r"\d{1,2}", spec)


def reminder_days(spec, a, b):
    """The days from `a` to `b` (inclusive) on which the reminder fires, in order."""
    m = re.fullmatch("(" + MON + r")(\d{1,2})", spec)
    if m:
        d = resolve(MONTHS[m.group(1)], int(m.group(2)))
        return [d] if d and a <= d <= b else []
    parts = spec.lower().split(None, 1)
    if parts[0] == "daily":
        test = lambda d: True
    elif parts[0] == "weekdays":
        test = lambda d: d.weekday() < 5
    elif parts[0] == "weekly":
        wds = {WEEKDAYS.get(x.strip()[:3]) for x in parts[1].split(",")} - {None}
        test = lambda d: d.weekday() in wds
    elif parts[0] == "monthly":
        n = int(re.match(r"\d+", parts[1]).group())
        test = lambda d: d.day == n
    else:
        return []
    return [a + timedelta(days=i) for i in range((b - a).days + 1) if test(a + timedelta(days=i))]


def next_reminder(spec):
    """Next date a reminder fires (today or later), or None if it has passed (or never fires)."""
    days = reminder_days(spec, TODAY, TODAY + timedelta(days=400))
    return days[0] if days else None


def every_label(spec):
    """How a frequency reads: Daily, Weekdays, Mon, Wed, Fri, Monthly 1st."""
    parts = spec.split(None, 1)
    if parts[0].lower() == "weekly":
        return ", ".join(x.strip()[:3].capitalize() for x in parts[1].split(","))
    return spec[0].upper() + spec[1:]


def resolve_past(month, day):
    """A habit log's MonDD: the latest such day on or before LOG_END (TODAY by default); None if there is none."""
    end = LOG_END or TODAY
    for y in (end.year, end.year - 1, end.year - 4):          # (a Feb 29 may be four years back)
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d <= end:
            return d
    return None


def log_of(note):
    """A note's habit log dates (`done Nov02 Nov03`), or None if it isn't a log."""
    m = RE_LOG.fullmatch(note)
    if not m:
        return None
    return [d for d in (resolve_past(MONTHS[x[:3]], int(x[3:])) for x in m.group(1).split()) if d]


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
        self.notable = False
        self.title = self._parse(text)

    def _parse(self, text):
        # Where each token sat in `text` (start, end), so an edit can change just that token.
        self.at = {"assignees": [], "reminders": [], "date": None, "effort": None, "plans": [], "priorities": []}
        self.date_text = self.effort = self.plan = self.plan_end = self.plan_kind = self.plan_token = None
        self.priorities = []                 # [(token, kind, start, end)]: ^wk45 and so on
        self.plans = []                      # [(kind, token, start, end)]: >Oct14 >wk45 >Nov >T3, as written
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
        ms = []                              # ^wk45 ^Nov ^T3 ^yr: top priorities (every valid one)
        for m in RE_PRIO.finditer(text):
            pr = priority_of(m.group(1))
            if pr:
                self.priorities.append((m.group(1),) + pr)
                ms.append(m)
        self.at["priorities"] = cut(ms)
        ms = []                              # >Oct14 >wk45 >Nov >T3: when it is planned for (every valid one)
        for m in RE_PLAN.finditer(text):
            pl = plan_of(m)
            if pl:
                self.plans.append(pl)
                ms.append(m)
        self.at["plans"] = cut(ms)
        if self.plans:                       # plan, plan_end, plan_kind, plan_token: the earliest one
            self.plan_kind, self.plan_token, self.plan, self.plan_end = min(self.plans, key=lambda x: (x[2], x[3]))

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

    def log(self):
        """The days this habit was done (from its `-- done …` notes), sorted."""
        return sorted({d for n in self.notes for d in (log_of(n) or [])})

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

    @property
    def held(self):
        """On hold (2.0.20): its own `/` mark or an ancestor's (a held task's subtasks are paused too)."""
        t = self
        while t:
            if t.status == "hold":
                return True
            t = t.parent
        return False

    def overdue(self):
        sp = self.span()
        return self.status != "done" and not self.held and sp is not None and sp[1] < TODAY

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
        self.path = self.folder = None   # in a portfolio's All projects: its backlog's path and its project folder

    def all_tasks(self):
        for t in self.tasks:
            yield from t.walk()


def parse(text, name=None):
    """-> list[Project]. Tasks before any @ line go into a project called `name`
    (a portfolio project's own name for its backlog), or "(no project)"."""
    projects, section, project, stack = [], None, None, []

    def ensure_project():
        nonlocal project
        if project is None:
            project = Project(name or "(no project)", section, n)
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

        m = RE_TASK.match(line)
        if m:
            status = {"!": "done", "~": "doing", "/": "hold", "": "open"}[m.group(2)]
            t = Task(m.group(3), status, level, n)
            t.notable = bool(m.group(1))     # (!) before the mark: circled in purple
            t.col = len(ws) + m.start(3)
            t.text = m.group(3)              # the task's text after the dash, as written (for the `text` edit)
            t.raw = line                     # the whole line as written, without its indentation (2.0.24: copy a day)
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
            line = "    " * depth + f"{box(t)} {t.label()}"
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

    kind "month": index 1-12. kind "season": index 0-2 into SEASONS. kind "week" (2.0.22): ISO year and week.
    With no year and index, the period that contains TODAY.
    """
    if obj is None:
        return None
    if not isinstance(obj, dict) or obj.get("kind") not in ("week", "month", "season"):
        raise ValueError("period.kind must be week, month or season")
    kind, year, index = obj["kind"], obj.get("year"), obj.get("index")
    if year is None and index is None:
        return period_at(kind, TODAY)
    if kind == "week":
        try:
            if type(year) is not int or not 1900 <= year <= 2999 or type(index) is not int:
                raise ValueError
            date.fromisocalendar(year, index, 1)
        except ValueError:
            raise ValueError(f"bad period {obj!r}") from None
        return kind, year, index
    hi = 12 if kind == "month" else len(SEASONS) - 1
    lo = 1 if kind == "month" else 0
    if type(year) is not int or not 1900 <= year <= 2999 or type(index) is not int or not lo <= index <= hi:
        raise ValueError(f"bad period {obj!r}")
    return kind, year, index


def period_range(kind, year, index):
    """-> (first day, last day) of the period."""
    if kind == "week":
        mon = date.fromisocalendar(year, index, 1)
        return mon, mon + timedelta(days=6)
    if kind == "month":
        return date(year, index, 1), month_end(year, index)
    _, a, b = SEASONS[index]
    return date(year, a, 1), month_end(year, b)


def period_at(kind, d):
    """The period of this kind that contains date d -> (kind, year, index)."""
    if kind == "week":
        return (kind,) + tuple(d.isocalendar()[:2])
    if kind == "month":
        return kind, d.year, d.month
    return kind, d.year, next(i for i, (_, a, b) in enumerate(SEASONS) if a <= d.month <= b)


def period_step(kind, year, index, step):
    """The period `step` periods later (negative = earlier), crossing years."""
    if kind == "week":
        return period_at(kind, period_range(kind, year, index)[0] + timedelta(weeks=step))
    n, base = (12, 1) if kind == "month" else (len(SEASONS), 0)
    k = year * n + index - base + step
    return kind, k // n, k % n + base


def period_label(kind, year, index, short=False):
    """"Oct 2026"; "Fall 2026 (Sep-Dec)", or "Fall 2026" when short; a week "Oct 12-18 2026", or
    "Week 42: Oct 12-18 2026"."""
    if kind == "week":
        a, b = period_range(kind, year, index)
        span = f"{MONTH_NAMES[a.month - 1]} {a.day}-{b.day}" if a.month == b.month else \
            f"{MONTH_NAMES[a.month - 1]} {a.day} - {MONTH_NAMES[b.month - 1]} {b.day}"
        return ("" if short else f"Week {index}: ") + f"{span} {b.year}"
    if kind == "month":
        return f"{MONTH_NAMES[index - 1]} {year}"
    name, a, b = SEASONS[index]
    return f"{name} {year}" + ("" if short else f" ({MONTH_NAMES[a - 1]}-{MONTH_NAMES[b - 1]})")


def period_columns(kind, year, index):
    """Timeline columns [(heading, start, end)]: the months of a season, or the weeks
    (Mon-Sun, cut to the month) of a month."""
    start, end = period_range(kind, year, index)
    if kind == "week":                                    # its seven days
        return [(f"{DAY_NAMES[k]} {(start + timedelta(days=k)).day}", start + timedelta(days=k), start + timedelta(days=k))
                for k in range(7)]
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
        mark = "/" if t.held and t.status != "done" else "~" if t.status == "doing" else " "
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
            out.append(f"  {box(t)} @{p.name}  {t.label()}")
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
            out.append(f"    {box(t)} @{p.name}  {t.title}{size}{when}{flag}")
    return out


def week_monday(obj=None):
    """Request value {year, index} (ISO year and week) -> that week's Monday; None -> this week's."""
    if obj is None:
        return TODAY - timedelta(days=TODAY.weekday())
    if not isinstance(obj, dict) or type(obj.get("year")) is not int or type(obj.get("index")) is not int:
        raise ValueError(f"bad week {obj!r}")
    return date.fromisocalendar(obj["year"], obj["index"], 1)


def week_label(monday):
    """"Oct 12 - 18", "Oct 26 - Nov 1", with the year when it isn't TODAY's."""
    sun = monday + timedelta(days=6)
    return fspan(monday, sun)


def week_days(monday):
    """The Week view's six columns: [(heading, days)]; Saturday and Sunday share the last one."""
    days = [monday + timedelta(days=i) for i in range(7)]
    heads = [f"{n} {d.day}" for n, d in zip(("Mon", "Tue", "Wed", "Thu", "Fri"), days)]
    return list(zip(heads, [[d] for d in days[:5]])) + [(f"Sat/Sun {days[5].day}-{days[6].day}", days[5:])]


# ---------- the Planner: Year / Season / Month / Week / Day (a planner period is (kind, year, index)) ----------
# Day: index = day of the year (1-366). Week: ISO year and week. Month: index 1-12. Season: index 0-2 (SEASONS).
# Year: index 0. Its columns are the next level down: days (Sat/Sun together), weeks, months, trimesters; a day
# has one column, itself.

PLANNER_KINDS = ("year", "season", "month", "week", "day")
COLUMN_KIND = {"day": "day", "week": "day", "month": "week", "season": "month", "year": "season"}
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _day_of(y, i):
    """Day `i` (1-366) of year `y`; ValueError if the year has no such day."""
    d = date(y, 1, 1) + timedelta(days=i - 1) if type(i) is int and i >= 1 else None
    if d is None or d.year != y:
        raise ValueError(f"{y} has no day {i}")
    return d


def planner_at(kind, d):
    """The planner period of `kind` containing day `d`."""
    if kind == "day":
        return "day", d.year, d.timetuple().tm_yday
    if kind == "week":
        y, w, _ = d.isocalendar()
        return "week", y, w
    if kind == "year":
        return "year", d.year, 0
    return period_at(kind, d)


def planner_from(obj):
    """A request's {kind, year, index} (only kind: the one containing TODAY; None: this week) -> a planner period."""
    if obj is None:
        return planner_at("week", TODAY)
    if not isinstance(obj, dict) or obj.get("kind") not in PLANNER_KINDS:
        raise ValueError(f"bad planner period {obj!r}")
    kind = obj["kind"]
    if "year" not in obj and "index" not in obj:
        return planner_at(kind, TODAY)
    y, i = obj.get("year"), obj.get("index", 0)
    if type(y) is not int or type(i) is not int or not 1900 <= y <= 2999:
        raise ValueError(f"bad planner period {obj!r}")
    if kind == "day":
        _day_of(y, i)                                       # ValueError if there is no such day
    elif kind == "week":
        date.fromisocalendar(y, i, 1)                       # ValueError if there is no such week
    elif kind in ("month", "season"):
        return period_from(obj)
    elif i != 0:
        raise ValueError(f"bad planner period {obj!r}")
    return kind, y, i


def planner_range(kind, y, i):
    if kind == "day":
        d = _day_of(y, i)
        return d, d
    if kind == "week":
        m = date.fromisocalendar(y, i, 1)
        return m, m + timedelta(days=6)
    if kind == "year":
        return date(y, 1, 1), date(y, 12, 31)
    return period_range(kind, y, i)


def planner_step(kind, y, i, step):
    if kind == "day":
        return planner_at("day", _day_of(y, i) + timedelta(days=step))
    if kind == "week":
        return planner_at("week", date.fromisocalendar(y, i, 1) + timedelta(days=7 * step))
    if kind == "year":
        return "year", y + step, 0
    return period_step(kind, y, i, step)


def planner_label(kind, y, i):
    """"Mon Oct 12", "Oct 12 - 18", "Nov 2026", "Fall 2026", "2026"."""
    if kind == "day":
        d = _day_of(y, i)
        return f"{DAY_NAMES[d.weekday()]} {fd(d)}"
    if kind == "week":
        return week_label(date.fromisocalendar(y, i, 1))
    if kind == "year":
        return str(y)
    return period_label(kind, y, i, short=True)


def planner_columns(kind, y, i):
    """[(heading, start, end, token)]: where tasks can be planned in this period. A week's six days (Sat/Sun
    together, planned as Saturday), a month's Mon-Sun weeks (headed by their days in the month), a
    season's months, a year's trimesters. `token` is the plan token for the column (without the >)."""
    ps, pe = planner_range(kind, y, i)
    if kind == "day":
        return [(f"{DAY_NAMES[ps.weekday()]} {ps.day}", ps, ps, f"{MONTH_NAMES[ps.month - 1]}{ps.day:02d}")]
    if kind == "week":
        return [(head, ds[0], ds[-1], f"{MONTH_NAMES[ds[0].month - 1]}{ds[0].day:02d}") for head, ds in week_days(ps)]
    if kind == "month":
        out, m = [], ps - timedelta(days=ps.weekday())
        while m <= pe:
            sun = m + timedelta(days=6)
            out.append((fspan(max(m, ps), min(sun, pe)), m, sun, f"wk{m.isocalendar()[1]}"))
            m += timedelta(days=7)
        return out
    if kind == "season":
        _, a, b = SEASONS[i]
        return [(MONTH_NAMES[m - 1], date(y, m, 1), month_end(y, m), MONTH_NAMES[m - 1]) for m in range(a, b + 1)]
    return [(f"{n} {MONTH_NAMES[a - 1]}-{MONTH_NAMES[b - 1]}", date(y, a, 1), month_end(y, b), f"T{k + 1}")
            for k, (n, a, b) in enumerate(SEASONS)]


def star_period(kind, y, i):
    """The period a ☆ marks from this planner period: itself, but a day's is its week (there are no day priorities)."""
    if kind == "day":
        return planner_at("week", _day_of(y, i))
    return kind, y, i


def planner_star(kind, y, i):
    """The ^priority token for this period (a day: its week's), and whether it reads back as that period (a token
    has no year, so only periods within about a year can be marked; ^yr is always this year)."""
    kind, y, i = star_period(kind, y, i)
    ps, pe = planner_range(kind, y, i)
    token = {"week": f"wk{i}", "month": MONTH_NAMES[i - 1] if kind == "month" else "", "season": f"T{i + 1}", "year": "yr"}[kind]
    pr = priority_of(token)
    return token, bool(pr) and pr == (kind, ps, pe)


def habit_rows(projects, a, b, every=False):
    """[(project, task, specs, due, done)]: each open task with a repeating reminder (`every`: each open task, a
    Habits page lists those without one too), the days from `a` to `b` it is due and those it was done."""
    out = []
    for p in projects:
        for t in p.all_tasks():
            specs = [spec for spec, _ in t.reminders if repeats(spec)]
            if t.status == "done" or not (specs or every) or (t.held and not every):
                continue                          # a held habit is paused: only the Habits page lists it, never due
            due = [] if t.held else sorted({d for spec in specs for d in reminder_days(spec, a, b)})
            out.append((p, t, specs, due, [d for d in t.log() if a <= d <= b]))
    return out


def habit_count(due, done, a=None, b=None):
    """2.0.25: (days done, days it counts for) of a habit from `a` to `b` (default: all given): a day counts when it
    was due or ticked (an extra tick counts for both), so a missed Wednesday reads 11/12. Its effort counts per day."""
    inr = lambda d: (a is None or d >= a) and (b is None or d <= b)
    ticked = {d for d in done if inr(d)}
    return len(ticked), len(ticked | {d for d in due if inr(d)})


def planner_groups(projects, period):
    """-> (columns, planned, backlog, priorities) for a planner period.
    columns: [(heading, start, end, token, ok, [(project, task, via)])]: tasks planned for that column or a part of it,
      once per column however many of their plans are in it (via: the token of the first such plan; ok: the
      column's token reads back as that column, so it can be planned), then (2.0.21) tasks whose own date falls
      in it, with via None (a "due" card): a single date or a range in every column it overlaps, a loose date
      (~wk45, ~Nov, ~T1, ~Q1) in a column that holds all of it; not in a column the task is already planned in;
    planned: [(project, [tasks])], every task with a plan in this period (overlapping it and inside the columns)
      or a due card, done ones too, once each, by its earliest such plan (else its date);
    backlog: [(project, [(depth, task)])], every open task with neither, in outline order;
    priorities: [(project, task)], tasks marked as top priorities for exactly this period."""
    kind, y, i = period
    ps, pe = planner_range(*period)
    cols = []
    for head, a, b, token in planner_columns(*period):
        probe = Task("x >" + token)
        ok = probe.plan_kind == COLUMN_KIND[kind] and probe.plan == a and probe.plan_end in (a, b)
        cols.append((head, a, b, token, ok, []))
    lo, hi = cols[0][1], cols[-1][2]
    rank = PLAN_RANK[COLUMN_KIND[kind]]
    sp = star_period(*period)
    star = (sp[0],) + planner_range(*sp)                      # priorities: for this period (a day: its week)
    planned, backlog, prios, dues = [], [], [], []
    for p in projects:
        mine, rest = [], []

        def visit(t, depth):
            here = sorted((x for x in t.plans if x[2] <= pe and x[3] >= ps and lo <= x[2] and x[3] <= hi),
                          key=lambda x: (x[2], x[3]))
            taken = set()
            for k, tok, a, b in here:
                if PLAN_RANK[k] <= rank:
                    ci = next((j for j, c in enumerate(cols) if c[1] <= a and b <= c[2]), None)
                    if ci is not None and ci not in taken:
                        taken.add(ci)
                        cols[ci][5].append((p, t, tok))
            due = []
            if t.end:                                     # its own date: a due card in the columns it falls in
                for j, c in enumerate(cols):
                    if j not in taken and (c[1] <= t.start and t.end <= c[2] if t.loose else t.start <= c[2] and t.end >= c[1]):
                        due.append(j)
                        dues.append((j, p, t))
            if here:
                mine.append((here[0][2], here[0][3], len(mine), t))
            elif due:
                mine.append((max(t.start, lo), t.end, len(mine), t))
            elif t.status != "done":
                rest.append((depth, t))
            if any(pr[1:] == star for pr in t.priorities):
                prios.append((p, t))
            for c in t.children:
                visit(c, depth + 1)
        for t in p.tasks:
            visit(t, 0)
        if mine:
            planned.append((p, [t for *_, t in sorted(mine, key=lambda x: x[:3])]))
        if rest:
            backlog.append((p, rest))
    for j, p, t in dues:                                  # due cards after the planned ones
        cols[j][5].append((p, t, None))
    return cols, planned, backlog, prios


def upcoming_groups(projects):
    """-> (horizon, overdue, due, doing, reminders); dated lists are (date, project, task[, spec])."""
    horizon = TODAY + timedelta(days=UPCOMING_DAYS)
    overdue, due, doing, reminders = [], [], [], []
    for p in projects:
        for t in p.all_tasks():
            if t.status == "done" or t.held:          # on hold: paused, not upcoming
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


def upcoming_habits(habits):
    """2.0.25: [(next, project, task, specs, due today, done today)] for each habit due from TODAY to the horizon:
    its next day due that isn't ticked yet (today until it is ticked), by that day."""
    out = []
    for p, t, specs, due, done in habit_rows(habits or [], TODAY, TODAY + timedelta(days=UPCOMING_DAYS)):
        nxt = next((d for d in due if d not in done), None)
        if nxt:
            out.append((nxt, p, t, specs, TODAY in due, TODAY in done))
    return sorted(out, key=lambda r: r[0])


def view_upcoming(projects, habits=None):
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
    if habits:                                            # 2.0.25: each habit's next day due (a portfolio's habits.kf)
        section("Habits", [f"    {fd(d):<9} @{p.name}  {t.title}   ({', '.join(every_label(x) for x in specs)})"
                           + (f"  [{t.effort.upper()}]" if t.effort else "") for d, p, t, specs, _, _ in upcoming_habits(habits)])
    return out


def view_week(projects, monday=None, habits=None):
    monday = monday or week_monday()
    cols, planned, backlog, prios = planner_groups(projects, planner_at("week", monday))
    rows = habit_rows(habits or [], monday, monday + timedelta(days=6))
    out = ["WEEK", "====", f"Week of {week_label(monday)}  (plan a task for a day with >MonDD)"]
    if prios:
        out.append("\nTop priorities (^wk" + str(monday.isocalendar()[1]) + ")")
        out.extend(f"    {box(t)} @{p.name}  {t.label()}" for p, t in prios)
    for head, a, b, _, _, items in cols:
        out.append(f"\n{head}")
        out.extend(f"    {box(t)} @{p.name}  {t.label()}" + ("" if via else f"  (due {fspan(t.start, t.end, t.loose)})")
                   for p, t, via in items)
        hab = [(d, p, t, d in done) for p, t, _, due, done in rows for d in due if a <= d <= b]
        out.extend(f"    {'[x]' if ok else '[ ]'} @{p.name}  {t.title}  (habit" + (f", {('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[d.weekday()]})" if a != b else ")")
                   for d, p, t, ok in sorted(hab, key=lambda x: x[0]))
        if not items and not hab:
            out.append("    (nothing planned)")
    sun = monday + timedelta(days=6)

    def where(t):                                         # its plans, or (a due card only) its date
        return plan_labels(t) if any(a <= sun and b >= monday for _, _, a, b in t.plans) else "due " + fspan(t.start, t.end, t.loose)
    out.append("\nBy project")
    for p, tasks in planned:
        out.append(f"  @{p.name}   {pts(effort_points(tasks)[1])}")
        out.extend(f"    {box(t)} {where(t):<7} {t.label()}" for t in tasks)
    if not planned:
        out.append("    (nothing planned this week)")
    if rows:                                              # 2.0.25: each habit's days done of due, and its effort per day
        out.append("\nHabits (done of due)")
        for p, t, specs, due, done in rows:
            n, m = habit_count(due, done)
            if not m:
                continue                                  # not due this week (a monthly one)
            out.append(f"    {n}/{m}  @{p.name}  {t.title}  ({', '.join(every_label(x) for x in specs)})"
                       + (f"  {n * t.points}/{pts(m * t.points)}" if t.points else ""))
    out.append("\nBacklog (open tasks not planned or due this week)")
    for p, items in backlog:
        out.append(f"  @{p.name}")
        out.extend(f"    {'    ' * depth}{box(t)} {t.label()}"
                   + (f"   (planned {plan_labels(t)})" if t.plans else "")
                   for depth, t in items)
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
        "title": t.title, "text": t.text, "raw": getattr(t, "raw", None), "status": t.status, "notable": t.notable, "line": t.line, "path": t.project and t.project.path,
        "log": [iso(x) for x in t.log()],
        "date_text": t.date_text, "assignees": t.assignees, "notes": [n for n in t.notes if log_of(n) is None],
        "effort": t.effort, "points": t.points,
        "plan": iso(t.plan), "plan_end": iso(t.plan_end), "plan_kind": t.plan_kind, "plan_token": t.plan_token,
        "plan_label": plan_label(t.plan_kind, t.plan, t.plan_end) if t.plan else None,
        "plans": [{"kind": k, "token": tok, "start": iso(a), "end": iso(b), "label": plan_label(k, a, b)} for k, tok, a, b in t.plans],
        "plan_labels": plan_labels(t) or None,
        "priorities": [{"token": tok, "kind": k, "start": iso(a), "end": iso(b)} for tok, k, a, b in t.priorities],
        "when": fspan(t.start, t.end, t.loose) if t.end else None, "loose": t.loose,
        "span": {"start": iso(sp[0]), "end": iso(sp[1]), "how": sp[2],
                 "label": fspan(sp[0], sp[1], t.loose if sp[2] == "own" else None)} if sp else None,
        "overdue": t.overdue(), "held": t.held,
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
    d["folder"] = p.folder
    d["children"] = []
    return d


def to_data(projects, period=None, plan=None, habits=None, every=False):
    """Everything the five views show, as plain dicts and lists (JSON-ready).

    `plan` (from planner_from) picks the Planner's period; default this week. `habits` (projects from habits files)
    adds `planner.habits` for the Planner's columns (`every`: a Habits page, listing tasks without a frequency too).

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
            "name": p.name, "line": p.line, "path": p.path, "folder": p.folder, "notes": p.notes,
            "done": sum(t.status == "done" for t in tasks), "total": len(tasks),
            "points": dict(zip(("left", "total"), effort_points(tasks))),
            "tasks": shown})

    first, last = cols[0][1], cols[-1][2]
    rows, unscheduled = timeline_rows(projects, done=True)   # the page hides done ones unless "Show done tasks"
    planned_only = [(p, t) for p, t in unscheduled if t.plans]   # 2.0.22: undated but planned: a row of plan marks
    unscheduled = [(p, t) for p, t in unscheduled if not t.plans]

    def planned_in(t, a, b):
        return any(x[2] <= b and x[3] >= a for x in t.plans)
    rows = [(s, e, p, t, how) for s, e, p, t, how in rows if not period or (s <= last and e >= first) or planned_in(t, first, last)]
    rows += [(min(x[2] for x in t.plans), None, p, t, None) for p, t in planned_only if not period or planned_in(t, first, last)]
    rows.sort(key=lambda r: r[0])
    if period:
        unscheduled = []
    people = [(n, [(p, t) for p, t in items if not inside or inside(t)]) for n, items in people_groups(projects)]
    horizon, overdue, due, doing, reminders = upcoming_groups(projects)
    plan = plan or planner_at("week", TODAY)
    pcols, pplanned, pbacklog, pprios = planner_groups(projects, plan)
    pnow = planner_at(plan[0], TODAY)
    pstart, pend = planner_range(*plan)
    star, star_ok = planner_star(*plan)
    spk = star_period(*plan)
    spr = planner_range(*spk)

    def pref(x):
        return {"kind": x[0], "year": x[1], "index": x[2], "label": planner_label(*x)}
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
        "targets": [{"name": p.name, "line": p.line, "path": p.path, "folder": p.folder,
                     "section": p.section.title if p.section else None} for p in projects],
        "timeline": {
            "columns": [{"head": h, "start": iso(a), "end": iso(b)} for h, a, b in cols],
            "rows": [dict(flat(p, t), bar=[e is not None and s <= b and e >= a for _, a, b in cols],
                          planned=[planned_in(t, a, b) for _, a, b in cols],
                          before=e is not None and e < first, after=e is not None and e > last) for s, e, p, t, _ in rows],
            "unscheduled": [flat(p, t) for p, t in unscheduled]},
        "people": [{"name": n, "points": effort_points(t for _, t in items)[0], "tasks": [flat(p, t) for p, t in items]}
                   for n, items in people if items],
        "upcoming": {
            "horizon": fd(horizon), "days": UPCOMING_DAYS,
            "overdue": [flat(p, t) for _, p, t in sorted(overdue, key=lambda r: r[0])],
            "due": [flat(p, t) for _, p, t in sorted(due, key=lambda r: r[0])],
            "reminders": [dict(flat(p, t), spec=spec, date=fd(d)) for d, spec, p, t in sorted(reminders, key=lambda r: r[0])],
            "doing": [flat(p, t) for p, t in doing],
            "today": {"date": iso(TODAY), "head": f"{('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[TODAY.weekday()]} {TODAY.day}",
                      "token": f"{MONTH_NAMES[TODAY.month - 1]}{TODAY.day:02d}", "today": True, "future": False},
            "habits": [dict(flat(p, t), every=specs, every_label=", ".join(every_label(x) for x in specs) or None,
                            next=iso(d), next_label=fd(d), due=[iso(TODAY)] if due_today else [],
                            done=[iso(TODAY)] if done_today else [])
                       for d, p, t, specs, due_today, done_today in ([] if every else upcoming_habits(habits))]},
        "planner": {
            **pref(plan), "start": iso(pstart), "end": iso(pend), "current": plan == pnow,
            "prev": pref(planner_step(*plan, -1)), "next": pref(planner_step(*plan, 1)), "now": pref(pnow),
            "column_kind": COLUMN_KIND[plan[0]],
            "star": {"token": star, "ok": star_ok, "kind": spk[0], "start": iso(spr[0]), "end": iso(spr[1]), "label": planner_label(*spk)},
            "columns": [{"head": head, "start": iso(a), "end": iso(b), "token": token, "ok": ok, "today": a <= TODAY <= b,
                         "tasks": [dict(flat(p, t), via=via, due=via is None) for p, t, via in items]} for head, a, b, token, ok, items in pcols],
            "projects": [{"name": p.name, "line": p.line, "path": p.path, "folder": p.folder, "points": effort_points(tasks)[1],
                          "tasks": [flat(p, t) for t in tasks]} for p, tasks in pplanned],
            "backlog": [{"name": p.name, "line": p.line, "path": p.path, "folder": p.folder, "tasks": [dict(flat(p, t), depth=d) for d, t in items]}
                        for p, items in pbacklog],
            "priorities": [flat(p, t) for p, t in pprios],
            "habits": [dict(flat(p, t), every=specs, every_label=", ".join(every_label(x) for x in specs) or None,
                            due=[iso(x) for x in due], done=[iso(x) for x in done],
                            count=dict(zip(("done", "days"), habit_count(due, done, max(pstart, pcols[0][1]), min(pend, pcols[-1][2])))))
                       for p, t, specs, due, done in habit_rows(habits or [], pcols[0][1], pcols[-1][2], every)],
            "days": [{"date": iso(x), "head": f"{('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[x.weekday()]} {x.day}",
                      "token": f"{MONTH_NAMES[x.month - 1]}{x.day:02d}", "today": x == TODAY, "future": x > TODAY}
                     for x in (pstart + timedelta(days=k) for k in range((pend - pstart).days + 1))] if plan[0] in ("week", "day") else [],
            "log_years": sorted({x.year for p in (habits or []) for t in p.all_tasks() for x in t.log() if x.year < TODAY.year})},
    }


# ---------- editing (only on an explicit user action) ----------

STATUS_MARK = {"open": "", "doing": "~", "done": "!", "hold": "/"}


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
        raise EditError(f"unknown status {status!r} (use open, doing, done or hold)")
    lines, _ = _task_at(text, line, title)
    raw = lines[line - 1]
    ws = raw[:len(raw) - len(raw.lstrip())]
    body = raw[len(ws):]
    notable = "(!)" if body.startswith("(!)") else ""
    body = body[len(notable):]
    if body[0] in "!~/":
        body = body[1:]
    lines[line - 1] = ws + notable + STATUS_MARK[status] + body
    return "".join(lines)


def set_every(text, line, spec, title=None):
    """Set how often a habit repeats: `daily`, `weekdays`, `weekly Mon, Wed`, `monthly 1st` (with or without
    the `*`), or (empty) remove it. Its repeating reminder is replaced in place; a new one goes at the end."""
    lines, t = _task_at(text, line, title)
    spec = " ".join(spec.strip().lstrip("*").split())
    probe = Task("x *" + spec) if spec else None
    if probe and (len(probe.reminders) != 1 or probe.title != "x" or not repeats(spec) or next_reminder(spec) is None):
        raise EditError(f"{spec!r} is not a frequency (use daily, weekdays, weekly Mon, Wed or monthly 1st)")
    raw = lines[line - 1]
    i = next((k for k, (sp, _) in enumerate(t.reminders) if repeats(sp)), None)
    if i is not None:
        s, e = (t.col + x for x in t.at["reminders"][i])
        raw = raw[:s] + "*" + spec + raw[e:] if spec else _drop(raw, s, e, t.col)
    elif not spec:
        return text
    else:
        p = _content_end(raw)
        raw = raw[:p] + " *" + spec + raw[p:]
    lines[line - 1] = raw
    out = "".join(lines)
    n = _find(out, line)
    old = [sp for sp, _ in t.reminders if not repeats(sp)]
    want = ([spec] if spec else []) + [sp for k, (sp, _) in enumerate(t.reminders) if repeats(sp) and k != i]
    if (n is None or n.title != t.title or [sp for sp, _ in n.reminders if not repeats(sp)] != old
            or sorted(sp for sp, _ in n.reminders if repeats(sp)) != sorted(want)):
        raise EditError("the line wouldn't read back with that frequency, so edit it by hand")
    return out


def tick_habit(text, line, value, title=None):
    """Mark a habit done on a day (`Nov02`) or not (`-Nov02`), in its log note `-- done Nov02 Nov03`
    (directly under the task; made if new, removed when empty). Only that note line changes."""
    lines, t = _task_at(text, line, title)
    value = value.strip()
    off = value.startswith("-")
    m = re.fullmatch("(" + MON + r")(\d{1,2})", value.lstrip("-").strip())
    day = m and resolve_past(MONTHS[m.group(1)], int(m.group(2)))
    if not day or (LOG_END is None and day > TODAY):
        raise EditError(f"{value.lstrip('-')!r} is not a day so far (use Nov02)")
    token = f"{MONTH_NAMES[day.month - 1]}{day.day:02d}"
    end = _subtree_end(lines, line, t.level)
    log_at = None                                   # the task's own log note: before its first subtask
    for i in range(line, end):
        c = lines[i].strip()
        if c.startswith("--"):
            if log_of(c[2:].strip()) is not None:
                log_at = i
                break
        elif c and RE_TASK.match(c):
            break
    if off:
        if log_at is None:
            return text
        raw = lines[log_at]
        keep = []
        for x in re.finditer(MON + r"\d{1,2}", raw):
            if resolve_past(MONTHS[x.group()[:3]], int(x.group()[3:])) == day:
                keep.append(x)
        if not keep:
            return text
        for x in reversed(keep):
            raw = _drop(raw, x.start(), x.end(), 0)
        if log_of(raw.strip()[2:].strip()) is None:  # nothing left: the note goes
            del lines[log_at]
        else:
            lines[log_at] = raw
    elif log_at is not None:
        if day in (log_of(lines[log_at].strip()[2:].strip()) or []):
            return text
        raw = lines[log_at]
        p = _content_end(raw)
        lines[log_at] = raw[:p] + " " + token + raw[p:]
    else:
        raw = lines[line - 1]
        ws = raw[:len(raw) - len(raw.lstrip())]
        ending = raw[_content_end(raw):].lstrip(" \t") or "\n"
        if not raw.endswith(tuple("\r\n")):
            lines[line - 1] = raw + ending
        lines.insert(line, ws + ("    " if ws and "\t" not in ws else "\t") + "-- done " + token + ending)
    out = "".join(lines)
    n = _find(out, line)
    before = [(x.title, x.status) for p in parse(text) for x in p.all_tasks()]
    after = [(x.title, x.status) for p in parse(out) for x in p.all_tasks()]
    if n is None or (day in n.log()) == off or before != after:
        raise EditError("the habit's log wouldn't read back that way, so edit it by hand")
    return out


def take_habit_log(text, year):
    """For the archive: each habit's log days from `year` (taken out of its log note) -> (rest of the text,
    [("Habits", [the habit's line, its log note for that year])])."""
    lines = text.splitlines(keepends=True)
    moved, cuts = [], []
    for p in parse(text):
        for t in p.all_tasks():
            days = [d for d in t.log() if d.year == year]
            if not days:
                continue
            end = _subtree_end(lines, t.line, t.level)
            for i in range(t.line, end):
                c = lines[i].strip()
                if c.startswith("--") and log_of(c[2:].strip()) is not None:
                    cuts.append((i, year))
            raw = lines[t.line - 1]
            head = raw.lstrip(" \t")
            moved.append(("Habits", [head if head.endswith(("\n", "\r")) else head + "\n",
                                     "\t-- done " + " ".join(f"{MONTH_NAMES[d.month - 1]}{d.day:02d}" for d in days) + "\n"]))
    if not moved:
        raise EditError(f"no habit was ticked in {year}")
    for i, y in sorted(set(cuts), reverse=True):
        raw = lines[i]
        for x in reversed(list(re.finditer(MON + r"\d{1,2}", raw))):
            d = resolve_past(MONTHS[x.group()[:3]], int(x.group()[3:]))
            if d and d.year == y:
                raw = _drop(raw, x.start(), x.end(), 0)
        if log_of(raw.strip()[2:].strip()) is None:
            del lines[i]
        else:
            lines[i] = raw
    return "".join(lines), moved


def set_notable(text, line, value, title=None):
    """Circle the task in purple (`value` "on": `(!)` before its status mark) or not ("" or "off").
    Only those three characters change."""
    if value not in ("on", "off", ""):
        raise EditError(f"notable is on or off, not {value!r}")
    lines, t = _task_at(text, line, title)
    on = value == "on"
    if t.notable == on:
        return text
    raw = lines[line - 1]
    ws = raw[:len(raw) - len(raw.lstrip())]
    body = raw[len(ws):]
    lines[line - 1] = ws + ("(!)" + body if on else body[3:])
    out = "".join(lines)
    n = _find(out, line)
    if n is None or n.notable != on or n.title != t.title or n.status != t.status or n.level != t.level:
        raise EditError("the line wouldn't read back as that task, so edit it by hand")
    return out


def _subtree_end(lines, line, level):
    """The last non-blank line (1-based) of the task on `line` and its subtree: its subtasks and
    notes, up to the next task at its level or above, an @ line or a heading."""
    last = line
    for i in range(line, len(lines)):
        r = lines[i]
        c = r.strip()
        if not c:
            continue
        rws = r[:len(r) - len(r.lstrip())]
        lvl = rws.count("\t") + rws.count(" ") // 4
        if c.startswith("@") or (not c.startswith("--") and RE_TASK.match(c) and lvl <= level) \
                or (lvl == 0 and not c.startswith("--") and not RE_TASK.match(c)):
            break
        last = i + 1
    return last


def _cut(text, line, title=None):
    """-> (text without the task on `line` and its subtree, the removed lines, the task). Checked:
    exactly that task and its subtasks are gone, and every other task reads back the same."""
    lines, t = _task_at(text, line, title)
    last = _subtree_end(lines, line, t.level)
    block = lines[line - 1:last]
    out = "".join(lines[:line - 1] + lines[last:])
    gone = {x.line for x in t.walk()}
    before = [(x.title, x.status) for p in parse(text) for x in p.all_tasks() if x.line not in gone]
    after = [(x.title, x.status) for p in parse(out) for x in p.all_tasks()]
    if before != after or {x.line for x in t.walk()} != {line + i for i, r in enumerate(block) if RE_TASK.match(r.strip())
                                                         and not r.strip().startswith("--")}:
        raise EditError("that task's lines aren't where expected, so change it by hand")
    return out, block, t


def delete_task(text, line, value="", title=None):
    """Remove the task on `line` with its subtasks and notes (whole lines; nothing else changes)."""
    return _cut(text, line, title)[0]


def _dedent(block):
    """A task's lines with the task's own indentation taken off (so it sits at the top level)."""
    raw = block[0]
    ws = raw[:len(raw) - len(raw.lstrip())]
    out = [r[len(ws):] if r.startswith(ws) else (r.lstrip(" \t") if r.strip() else r) for r in block]
    while out and not out[-1].strip():
        out.pop()
    if out and not out[-1].endswith(("\n", "\r")):
        out[-1] += "\n"
    return out


def take_task(text, line, title=None):
    """For the archive: -> (text without the task and its subtree, its lines at the top level,
    its @ group's name or None for the file's own project)."""
    out, block, t = _cut(text, line, title)
    lines = text.splitlines(keepends=True)
    group = t.project.name if lines[t.project.line - 1].strip().startswith("@") else None
    return out, _dedent(block), group


def take_done(text, project_line=None):
    """For "Archive done": every finished top-level task (done, with all its subtasks done) in the project on
    `project_line` (or anywhere); a done subtask of an unfinished task stays with it.
    -> (the rest of the text, [(group, lines)] in order)."""
    picks = [t for p in parse(text) if project_line in (None, p.line) for t in p.tasks
             if all(x.status == "done" for x in t.walk())]
    if not picks:
        raise EditError("there are no finished tasks to archive")
    moved = []
    for t in sorted(picks, key=lambda x: -x.line):           # from the bottom up, so the lines above stay put
        text, block, group = take_task(text, t.line, t.title)
        moved.append((group, block))
    return text, moved[::-1]


def put_in_archive(text, group, block):
    """`text` (an archive file) with `block` added at the end of its `@group` (made at the end if new),
    or of its own tasks (before the first @) when `group` is None. Existing lines don't change, except
    that a last line with no line ending gets one."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"
    if group is None:
        at = next((i for i, r in enumerate(lines) if r.strip().startswith("@")), len(lines))
    else:
        head = next((i for i, r in enumerate(lines) if r.strip()[1:].strip() == group and r.strip().startswith("@")), None)
        if head is None:
            sep = ["\n"] if any(r.strip() for r in lines) else []
            return "".join(lines + sep + ["@" + group + "\n"] + block)
        at = next((i for i in range(head + 1, len(lines)) if lines[i].strip().startswith("@")
                   or (lines[i][:1] not in " \t" and lines[i].strip() and not lines[i].strip().startswith("--")
                       and not RE_TASK.match(lines[i].strip()))), len(lines))
    while at > 0 and not lines[at - 1].strip() and (group is None or at - 1 > head):
        at -= 1                                     # before the blank lines that end the group
    return "".join(lines[:at] + block + lines[at:])


def archive_today(year):
    """The TODAY an archive file of `year` is read with, so its dates (no years written) fall in that year."""
    return date(year, 1, 1) + timedelta(days=PAST_DAYS)


def set_date(text, line, when, title=None):
    """Set, replace or (with an empty `when`) clear the task's own date token.

    An existing date token is replaced in place. A new one goes before the
    first reminder, or at the end of the line. Nothing else on the line moves.
    """
    lines, t = _task_at(text, line, title)
    when = when.strip()
    probe = Task("x " + when) if when else None
    if probe and (probe.end is None or probe.title != "x"):
        raise EditError(f"{when!r} is not a date (use Oct24, Oct23--26, Oct23--Nov03, ~Q1, ~T1, ~Nov or ~wk43)")
    raw = lines[line - 1]
    if t.at["date"]:
        s, e = (t.col + i for i in t.at["date"])
        raw = raw[:s] + when + raw[e:] if when else _drop(raw, s, e, t.col)
    elif not when:
        raise EditError("that task has no date to clear")
    elif t.at["reminders"] or t.at["plans"] or t.at["priorities"]:   # before >plans, ^priorities and reminders: one order
        p = t.col + min(s for s, _ in t.at["reminders"] + t.at["priorities"] + t.at["plans"])
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


def _spans(t):
    """The task's plans as a set of (kind, start, end): what they mean, however they are written."""
    return frozenset((k, a, b) for k, _, a, b in t.plans)


def _one_plan(when):
    """`Oct14` / `>Oct14` / `wk45` / `Nov` / `T3` -> (token without the >, (kind, start, end)), or EditError."""
    tok = str(when).strip().lstrip(">").strip()
    probe = Task("x >" + tok) if tok else None
    if not probe or len(probe.plans) != 1 or probe.title != "x":
        raise EditError(f"{tok!r} is not a plan (use Oct14, wk45, Nov or T3)")
    k, _, a, b = probe.plans[0]
    return tok, (k, a, b)


def set_plan(text, line, value, title=None):
    """Plan the task for a day (`Oct14`), a week (`wk45`), a month (`Nov`) or a trimester (`T3`), with or
    without the `>`. A task can have several plans (`>Oct14 >Oct16`). The value says how:

      `Oct16`   plan it then, and drop its plans that ended before TODAY (planning from the backlog)
      `+Oct16`  plan it then as well, keeping every other plan
      `-Oct14`  take that plan off (matched by what it means, so `>Oct4` matches `-Oct04`)
      `""`      take every plan off
      {"from": "Oct14", "to": "Oct16"}  move that one plan, in place (if `to` is already there, `from` just goes)
      {"add": ["wk45", "wk47"], "remove": ["wk46"], "past": true}  several at once, as one edit (the Planner's
                list); each removed one must be there, and `past` also drops plans that ended before TODAY

    A plan it already has is not added twice (unchanged). A new token goes right after the task's last plan,
    else before the first ^priority or reminder, else at the end of the line; a removed one takes the spaces
    before it. Nothing else on the line moves.
    """
    lines, t = _task_at(text, line, title)
    have = _spans(t)
    spans = [(t.col + s, t.col + e) for s, e in t.at["plans"]]       # absolute, in the order of t.plans
    mean = [(k, a, b) for k, _, a, b in t.plans]
    drop, adds = [], []                                              # indexes to remove; tokens to add
    if isinstance(value, dict) and set(value) <= {"add", "remove", "past"}:
        lists = [value.get("add", []), value.get("remove", [])]
        if not all(isinstance(x, list) and all(isinstance(y, str) for y in x) for x in lists):
            raise EditError("add and remove are lists of plans, like [\"wk45\", \"wk47\"]")
        new = []
        for tok, m in map(_one_plan, lists[0]):
            if m not in have and m not in new:
                adds.append(tok)
                new.append(m)
        gone = set()
        for x in lists[1]:
            _, m = _one_plan(x)
            if m not in have:
                raise EditError(f"that task isn't planned for {x.strip().lstrip('>')}")
            gone.add(m)
        if gone & {_one_plan(x)[1] for x in lists[0]}:
            raise EditError("a plan can't be added and taken off at once")
        keep = {_one_plan(x)[1] for x in lists[0]}
        drop = [i for i, m in enumerate(mean) if m in gone or (value.get("past") and m[2] < TODAY and m not in keep)]
        if not drop and not adds:
            return text
        want = (have - {mean[i] for i in drop}) | set(new)
    elif isinstance(value, dict):
        if set(value) != {"from", "to"}:
            raise EditError("a move is {from, to}")
        _, old = _one_plan(value["from"])
        tok, new = _one_plan(value["to"])
        idx = [i for i, m in enumerate(mean) if m == old]
        if not idx:
            raise EditError(f"that task isn't planned for {str(value['from']).lstrip('>')}")
        if old == new:
            return text
        if new in have:
            drop, want = idx, have - {old}
        else:                                                        # replace the first in place, drop any copies
            drop, want = idx[1:], (have - {old}) | {new}
            s, e = spans[idx[0]]
    else:
        value = str(value).strip()
        if not value:
            if not t.plans:
                raise EditError("that task isn't planned")
            drop, want = list(range(len(mean))), frozenset()
        elif value.startswith("-"):
            _, old = _one_plan(value[1:])
            drop = [i for i, m in enumerate(mean) if m == old]
            if not drop:
                raise EditError(f"that task isn't planned for {value[1:].strip().lstrip('>')}")
            want = have - {old}
        else:
            keep = value.startswith("+")
            tok, new = _one_plan(value[1:] if keep else value)
            if not keep:
                drop = [i for i, m in enumerate(mean) if m[2] < TODAY and m != new]
            want = (have - {mean[i] for i in drop}) | {new}
            if new not in have:
                adds = [tok]
            elif not drop:
                return text
    raw = lines[line - 1]
    ops = []                                                         # (position, order, function on raw)
    if isinstance(value, dict) and "to" in value and new not in have:
        ops.append((s, 1, lambda r, s=s, e=e, tok=tok: r[:s] + ">" + tok + r[e:]))
    for i in drop:
        a, b = spans[i]
        ops.append((a, 1, lambda r, a=a, b=b: _drop(r, a, b, t.col)))
    if adds:
        add = " >".join(adds)                                        # several go side by side: >wk45 >wk47
        kept = [spans[i] for i in range(len(spans)) if i not in drop]
        tail = t.at["priorities"] + t.at["reminders"]
        if kept:
            p = max(e for _, e in kept)
            ops.append((p, 0, lambda r, p=p: r[:p] + " >" + add + r[p:]))
        elif tail:
            p = t.col + min(x for x, _ in tail)
            ops.append((p, 0, lambda r, p=p: r[:p] + ">" + add + " " + r[p:]))
        else:
            p = _content_end(raw)
            ops.append((p, 0, lambda r, p=p: r[:p] + " >" + add + r[p:]))
    for _, _, f in sorted(ops, key=lambda o: (-o[0], o[1])):        # right to left: earlier positions stay put
        raw = f(raw)
    lines[line - 1] = raw
    out = "".join(lines)
    n = _find(out, line)
    if n is None or (_spans(n), n.title, n.start, n.end) != (want, t.title, t.start, t.end):
        raise EditError("the line wouldn't read back as planned for that, so edit it by hand")
    return out


def set_priority(text, line, value, title=None):
    """Make the task a top priority for a period (`wk45`, `Nov`, `T3`, `yr`; with or without the `^`), or
    (`-wk45`) not any more. A new token goes before the first reminder (after any plan), or at the end;
    removing takes the token whose period matches and the spaces before it. Already so: unchanged."""
    lines, t = _task_at(text, line, title)
    value = value.strip()
    off = value.startswith("-")
    tok = value.lstrip("-").strip().lstrip("^")
    probe = Task("x ^" + tok)
    if len(probe.priorities) != 1 or probe.title != "x":
        raise EditError(f"{tok!r} is not a period (use wk45, Nov, T3 or yr)")
    span = probe.priorities[0][1:]
    have = [i for i, pr in enumerate(t.priorities) if pr[1:] == span]
    raw = lines[line - 1]
    if off:
        if not have:
            return text
        for i in sorted(have, reverse=True):
            s, e = (t.col + x for x in t.at["priorities"][i])
            raw = _drop(raw, s, e, t.col)
    else:
        if have:
            return text
        rem = t.at["reminders"]
        if rem:
            p = t.col + min(s for s, _ in rem)
            raw = raw[:p] + "^" + tok + " " + raw[p:]
        else:
            p = _content_end(raw)
            raw = raw[:p] + " ^" + tok + raw[p:]
    lines[line - 1] = raw
    out = "".join(lines)
    n = _find(out, line)
    if (n is None or (span in [pr[1:] for pr in n.priorities]) == off or n.title != t.title
            or (_spans(n), n.start, n.end) != (_spans(t), t.start, t.end)):
        raise EditError("the line wouldn't read back that way, so edit it by hand")
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
        tokens = t.at["reminders"] + t.at["priorities"] + t.at["plans"] + [t.at[k] for k in ("effort", "date") if t.at[k]]
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
        tokens = t.at["reminders"] + t.at["priorities"] + t.at["plans"] + [t.at[k] for k in ("date",) if t.at[k]]
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
    last = _subtree_end(lines, line, t.level)   # last non-blank line of the task's subtree
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


def _project_end(lines, line):
    """The last non-blank line (1-based) of the project on `line`: its tasks and notes, before blank lines,
    the next @ line or a heading."""
    last = line
    for i in range(line, len(lines)):
        r = lines[i]
        c = r.strip()
        if not c:
            continue
        rws = r[:len(r) - len(r.lstrip())]
        lvl = rws.count("\t") + rws.count(" ") // 4
        if c.startswith("@") or (lvl == 0 and not c.startswith("--") and not RE_TASK.match(c)):
            break
        last = i + 1
    return last


STATUS_ORDER = {"done": 0, "doing": 1, "open": 2, "hold": 3}
_ENDS = tuple("\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")


def _tree_sig(t):
    return tuple((x.title, x.status, x.level - t.level, tuple(x.notes)) for x in t.walk())


def sort_tasks(text, line, value="", title=None):
    """Order a project's top-level tasks done, in progress, then open, and within each A to Z by title (2.0.19;
    ignoring case and the tokens; stable for equal titles). `line` is the project's line and `title` its name (as for `add_task`; 0 = the file's own project);
    value "all" sorts every project in the file. Each task moves with its whole subtree (subtasks, notes) as
    whole lines, word for word; the blank lines between tasks stay where they were, and the project's notes
    before its first task stay first. Already in order: the text comes back unchanged."""
    lines = text.splitlines(keepends=True)
    projects = parse(text)
    if value == "all":
        picks = projects
    elif value == "":
        if line == 0:
            own = next((p for p in projects if not lines[p.line - 1].strip().startswith("@")), None)
            picks = [own] if own else []
        else:
            if type(line) is not int or not 1 <= line <= len(lines):
                raise EditError(f"line {line!r} is not in the text")
            p = next((p for p in projects if p.line == line), None)
            own = p is not None and not lines[line - 1].strip().startswith("@")
            if p is None or (title is not None and p.name != title and not own):
                raise EditError(f"line {line} is no longer that project (the text has changed)")
            picks = [p]
    else:
        raise EditError('sort takes "" (that project) or "all"')
    want = {}                                    # project line -> its tasks' trees in the new order
    for p in picks:
        if len(p.tasks) < 2:
            continue
        order = sorted(p.tasks, key=lambda t: (STATUS_ORDER[t.status], t.title.casefold()))
        if order == p.tasks:
            continue
        end = _project_end(lines, p.line)
        starts = [t.line for t in p.tasks] + [end + 1]
        blocks, gaps = [], []
        for a, b in zip(starts, starts[1:]):
            chunk = lines[a - 1:b - 1]
            k = len(chunk)
            while k > 1 and not chunk[k - 1].strip():
                k -= 1
            blocks.append(chunk[:k]); gaps.append(chunk[k:])
        at_eof = end == len(lines) and not lines[end - 1].endswith(_ENDS)
        if at_eof:                               # the file's last line has no line ending: it may move up
            blocks[-1] = blocks[-1][:-1] + [blocks[-1][-1] + next(
                (r[_content_end(r):].lstrip(" \t") for r in lines if r[_content_end(r):].lstrip(" \t")), "\n")]
        new = []
        for t, gap in zip(order, gaps):
            new += blocks[p.tasks.index(t)] + gap
        if at_eof:
            r = new[-1]
            new[-1] = r[:_content_end(r)] + r[_content_end(r):].rstrip("".join(_ENDS))
        lines[starts[0] - 1:end] = new
        want[p.line] = [_tree_sig(t) for t in order]
    out = "".join(lines)
    if out == text:
        return text
    after = parse(out)
    ok = len(after) == len(projects)
    for a, b in zip(projects, after) if ok else ():
        ok = ok and (a.name, a.line, a.notes) == (b.name, b.line, b.notes) \
            and [_tree_sig(t) for t in b.tasks] == want.get(a.line, [_tree_sig(t) for t in a.tasks])
    if not ok or sorted(r.rstrip("".join(_ENDS)) for r in out.splitlines(True)) != \
            sorted(r.rstrip("".join(_ENDS)) for r in text.splitlines(True)):
        raise EditError("that project's lines aren't where expected, so sort it by hand")
    return out


def add_task(text, line, task_text, title=None):
    """Add `- task_text` as the last top-level task of the project on `line` (its @ line).

    `title` is the project's name. The new line goes after the project's last line
    (its tasks and notes, before blank lines and the next @ or heading), indented
    like the project's first task. Existing lines are not changed, except that a
    final line with no line ending gets one.
    """
    lines = text.splitlines(keepends=True)
    task_text = task_text.strip() if isinstance(task_text, str) else ""
    if not task_text or any(c in task_text for c in "\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"):
        raise EditError("a task is one line of text")
    if line == 0:                               # the file's own project (a portfolio backlog's tasks before any @)
        own = next((p for p in parse(text) if not lines[p.line - 1].strip().startswith("@")), None)
        if own is None:                         # it has none yet: the new task goes first
            ending = next((r[_content_end(r):].lstrip(" \t") for r in lines if r[_content_end(r):].lstrip(" \t")), "\n")
            out = "- " + task_text + ending + text
            n = _find(out, 1)
            if n is None or n.parent is not None:
                raise EditError("the new task wouldn't land in that project, so add it by hand")
            return out
        line, title = own.line, None
    if type(line) is not int or not 1 <= line <= len(lines):
        raise EditError(f"line {line!r} is not in the text")
    p = next((p for p in parse(text) if p.line == line), None)
    own = p is not None and not lines[line - 1].strip().startswith("@")    # tasks before any @: named by the file, not the text
    if p is None or (title is not None and p.name != title and not own):
        raise EditError(f"line {line} is no longer that project (the text has changed)")
    raw = lines[line - 1]
    first = p.tasks[0] if p.tasks else None
    fr = lines[first.line - 1] if first else ""
    indent = fr[:len(fr) - len(fr.lstrip())]
    ending = raw[_content_end(raw):].lstrip(" \t") or "\n"
    last = _project_end(lines, line)
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


def add_with_fields(op, text, line, fields, title=None):
    """Op `task` or `subtask` with the new task's fields given separately:
    {"title": "draft report", "who": "KA", "effort": "m", "date": "Oct24", "plan": "Oct14"} (all but the title
    optional; `every` too, for a habit; `plan` plans it, as the Planner's column + Add task does).

    The line is added with the title alone, then who, effort and date are set on it by the
    same edits as the page's cells (set_assignees, set_effort, set_date), so each is checked
    and lands in the usual order. If any is refused, the whole edit is refused.
    """
    if not isinstance(fields, dict) or not isinstance(fields.get("title"), str):
        raise EditError("value must be text, or {title, who, effort, date}")
    out = EDITS[op](text, line, fields["title"], title)
    a, b = text.splitlines(), out.splitlines()
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), len(a)) + 1   # the new line
    for key, edit in (("who", set_assignees), ("effort", set_effort), ("date", set_date), ("every", set_every), ("plan", set_plan)):
        value = fields.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise EditError(f"{key} must be text")
        out = edit(out, n, value, _find(out, n).title)
    return out


EDITS = {"every": set_every, "tick": tick_habit, "priority": set_priority, "notable": set_notable, "delete": delete_task, "text": set_text, "plan": set_plan, "status": set_status, "date": set_date, "effort": set_effort, "assign": add_assignees, "who": set_assignees,
         "subtask": add_subtask, "task": add_task, "sort": sort_tasks}


# ---------- the notes file (--serve notes.txt) ----------

NOTE_SUFFIXES = (".kf", ".txt", ".md", ".markdown")   # files the page can open (.kf: the kafeen format)

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


def _hunks(base, other):
    """[(start, end, lines)]: where `other` replaces base[start:end] with `lines` (lists of lines)."""
    import difflib
    sm = difflib.SequenceMatcher(None, base, other, autojunk=False)
    return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def merge3(base, mine, theirs):
    """2.1.0: merge two texts that both started from `base`, line by line; -> (text, conflicts).

    Changes to different lines are both kept. Lines added at the same place on both sides are both kept
    (theirs first). Where both sides changed the same lines differently, theirs is kept and the clash is
    listed in `conflicts` as {line (1-based, in the result), base, mine, theirs} (each a list of lines). The
    result is made only of whole lines from the three texts, with their line endings, so nothing is reworded.
    """
    if mine == theirs or base == mine:
        return theirs, []
    if base == theirs:
        return mine, []
    # a missing line ending at the very end doesn't make the last line a change: compare as if every text had
    # one, and put back what the side that changed the end did (both sides agree, or one kept the base's)
    eol = "\r\n" if "\r\n" in base + mine + theirs else "\n"
    bare = [x != "" and not x.endswith(("\n", "\r")) for x in (base, mine, theirs)]
    end_bare = bare[1] if bare[1] == bare[2] else bare[1] if bare[2] == bare[0] else bare[2]
    b, m, t = ((x + eol if nb else x).splitlines(keepends=True) for x, nb in zip((base, mine, theirs), bare))
    hunks = sorted([(s0, e0, ls, 0) for s0, e0, ls in _hunks(b, m)] + [(s0, e0, ls, 1) for s0, e0, ls in _hunks(b, t)],
                   key=lambda h: (h[0], h[1]))
    out, conflicts, pos, i = [], [], 0, 0
    while i < len(hunks):
        lo, hi, group = hunks[i][0], hunks[i][1], [hunks[i]]
        i += 1
        while i < len(hunks):                         # hunks that overlap, or lines added at the same place, form one group
            s0, e0 = hunks[i][0], hunks[i][1]
            if s0 < hi or (s0 == e0 == lo == hi):
                group.append(hunks[i]); hi = max(hi, e0); i += 1
            else:
                break
        out += b[pos:lo]
        sides = [[h for h in group if h[3] == k] for k in (0, 1)]

        def apply(hs):                                # one side's text for base[lo:hi]
            res, at = [], lo
            for s0, e0, ls, _ in hs:
                res += b[at:s0] + ls; at = e0
            return res + b[at:hi]
        if not sides[0] or not sides[1]:
            out += apply(group)                       # only one side changed here
        else:
            mm, tt = apply(sides[0]), apply(sides[1])
            if mm == tt:
                out += tt
            elif lo == hi:                            # both only added lines at the same place: keep both
                out += tt + [x for x in mm if x not in tt]
            else:
                conflicts.append({"line": len(out) + 1, "base": b[lo:hi], "mine": mm, "theirs": tt})
                out += tt
        pos = hi
    out += b[pos:]
    text = "".join(out)
    if end_bare and text.endswith(eol):
        text = text[:-len(eol)]
    return text, conflicts


# ---------- the portfolio (--serve: the Projects folder next to planner.py) ----------
#
# A portfolio is a folder (PROJECTS); each sub-folder is a project:
#   HDC/backlog.kf  quicknote.kf  habits.kf  notes/[Section/]Page.kf|.txt|.md  archive/2026.kf
# Paths in the API are relative to the portfolio, with "/" between parts. Hidden
# names (starting with ".") are never listed or opened; .trash/ holds what was deleted.

PROJECTS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Projects")
PROJECT_FILES = {"backlog": "backlog.kf", "quicknote": "quicknote.kf", "habits": "habits.kf"}
NOTES_DIR, ARCHIVE_DIR, TRASH_DIR = "notes", "archive", ".trash"
RE_ARCHIVE = re.compile(r"\d{4}\.kf")


class PortfolioError(ValueError):
    """A portfolio request that can't be done (bad name or path, already exists, ...)."""


def _clean_name(name):
    """A project, section or page name as given, stripped; PortfolioError if it can't be a file name."""
    name = name.strip() if isinstance(name, str) else ""
    if (not name or name.startswith(".") or len(name) > 120 or any(c in name for c in '/\\:')
            or any(ord(c) < 32 for c in name)):
        raise PortfolioError("a name can't be empty, start with a dot, or contain / \\ or :")
    return name


def portfolio_kind(rel):
    """What the portfolio path `rel` names: project, backlog / quicknote / habits, section, page,
    archive; or None. Only by its shape; the file may not exist."""
    parts = rel.split("/") if isinstance(rel, str) else []
    if not parts or any(not x or x.startswith(".") for x in parts):
        return None
    n = len(parts)
    if n == 1:
        return "project"
    if n == 2:
        return next((k for k, f in PROJECT_FILES.items() if f == parts[1]), None)
    if n == 3 and parts[1] == ARCHIVE_DIR:
        return "archive" if RE_ARCHIVE.fullmatch(parts[2]) else None
    if parts[1] != NOTES_DIR or n > 4:
        return None
    if parts[-1].lower().endswith(NOTE_SUFFIXES):
        return "page"
    return "section" if n == 3 else None


def portfolio_path(root, rel):
    """The real path of `rel` inside the portfolio `root`; PortfolioError if it isn't one
    of the portfolio's kinds or would lead outside (.., symlinks)."""
    if isinstance(rel, str) and ("\\" in rel or "\0" in rel):
        rel = None
    if portfolio_kind(rel) is None:
        raise PortfolioError(f"{rel!r} isn't a project, page or notes file in this portfolio")
    root = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root, *rel.split("/")))
    if not full.startswith(root.rstrip(os.sep) + os.sep):
        raise PortfolioError(f"{rel!r} is outside the portfolio")
    return full


def _listing(folder):
    """Visible entries of `folder` (none if it doesn't exist), sorted by name, folders first."""
    try:
        found = [e for e in os.scandir(folder) if not e.name.startswith(".")]
    except OSError:
        return []
    return sorted(found, key=lambda e: (not e.is_dir(), e.name.casefold()))


def _page(rel, filename):
    stem, ext = os.path.splitext(filename)
    return {"kind": "page", "name": stem, "file": filename, "type": ext[1:].lower(), "path": rel}


def project_info(root, name):
    """One project: {name, path, files: {backlog, quicknote, habits} (paths; `made` says which
    exist), notes: [sections {kind, name, path, pages} and pages {kind, name, file, type, path}],
    archive: [{year, path}] newest first}."""
    d = os.path.join(root, name)
    notes = []
    for e in _listing(os.path.join(d, NOTES_DIR)):
        rel = f"{name}/{NOTES_DIR}/{e.name}"
        if e.is_dir():
            pages = [_page(f"{rel}/{f.name}", f.name) for f in _listing(e.path)
                     if f.is_file() and f.name.lower().endswith(NOTE_SUFFIXES)]
            notes.append({"kind": "section", "name": e.name, "path": rel, "pages": pages})
        elif e.is_file() and e.name.lower().endswith(NOTE_SUFFIXES):
            notes.append(_page(rel, e.name))
    archive = sorted(({"year": int(e.name[:4]), "path": f"{name}/{ARCHIVE_DIR}/{e.name}"}
                      for e in _listing(os.path.join(d, ARCHIVE_DIR))
                      if e.is_file() and RE_ARCHIVE.fullmatch(e.name) and e.stat().st_size),
                     key=lambda a: -a["year"])
    return {"name": name, "path": name,
            "files": {k: f"{name}/{f}" for k, f in PROJECT_FILES.items()},
            "made": [k for k, f in PROJECT_FILES.items() if os.path.isfile(os.path.join(d, f))],
            "notes": notes, "archive": archive}


def portfolio_tree(root):
    """{name, projects: [project_info]} for the portfolio folder `root`."""
    root = os.path.realpath(root)
    return {"name": os.path.basename(root),
            "projects": [project_info(root, e.name) for e in _listing(root) if e.is_dir()]}


def new_project(root, name):
    """Make a new project: its folder, its files (empty) and its notes/ and archive/ folders; -> its path."""
    name = _clean_name(name)
    full = portfolio_path(root, name)
    if os.path.lexists(full):
        raise PortfolioError(f"there is already a project called {name}")
    os.mkdir(full)
    for folder in (NOTES_DIR, ARCHIVE_DIR):
        os.mkdir(os.path.join(full, folder))
    for filename in PROJECT_FILES.values():
        write_notes(os.path.join(full, filename), "", None)
    return name


def _project_dir(root, project):
    full = portfolio_path(root, project if isinstance(project, str) else None)
    if not os.path.isdir(full):
        raise PortfolioError(f"there is no project called {project}")
    return full


def new_section(root, project, name):
    """Make a notes section (a folder in notes/); -> its path."""
    _project_dir(root, project)
    name = _clean_name(name)
    rel = f"{project}/{NOTES_DIR}/{name}"
    if name.lower().endswith(NOTE_SUFFIXES):
        raise PortfolioError("a section name can't end like a file (.kf, .txt, .md)")
    full = portfolio_path(root, rel)
    if os.path.lexists(full):
        raise PortfolioError(f"{name} already exists")
    os.makedirs(full)
    return rel


def new_page(root, project, name, section=None):
    """Make an empty notes page; `.kf` is added to a name without .kf, .txt or .md; -> its path."""
    _project_dir(root, project)
    name = _clean_name(name)
    if not name.lower().endswith(NOTE_SUFFIXES):
        name += ".kf"
    folder = f"{project}/{NOTES_DIR}" + (f"/{_clean_name(section)}" if section else "")
    rel = f"{folder}/{name}"
    full = portfolio_path(root, rel)
    if section and not os.path.isdir(os.path.dirname(full)):
        raise PortfolioError(f"there is no section called {section}")
    if os.path.lexists(full):
        raise PortfolioError(f"{name} already exists")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    write_notes(full, "", None)
    return rel


def rename_item(root, rel, name):
    """Rename a project, section or page (a page keeps its ending unless the new name has one);
    -> the new path."""
    kind = portfolio_kind(rel)
    if kind not in ("project", "section", "page"):
        raise PortfolioError("only projects, sections and pages can be renamed")
    full = portfolio_path(root, rel)
    if not os.path.lexists(full):
        raise PortfolioError(f"{rel} isn't there any more")
    name = _clean_name(name)
    if kind == "page" and not name.lower().endswith(NOTE_SUFFIXES):
        name += os.path.splitext(rel)[1]
    new = rel.rsplit("/", 1)[0] + "/" + name if "/" in rel else name
    if portfolio_kind(new) != kind:
        raise PortfolioError(f"{name} can't be the name of a {kind}")
    target = portfolio_path(root, new)
    if os.path.lexists(target) and not os.path.samefile(full, target):   # (same file: a change of case)
        raise PortfolioError(f"{name} already exists")
    os.rename(full, target)
    return new


def trash_item(root, rel):
    """Move a project, section or page into the portfolio's .trash/ (same path inside it,
    with " (2)" and so on if that is taken); -> the path in .trash."""
    if portfolio_kind(rel) not in ("project", "section", "page"):
        raise PortfolioError("only projects, sections and pages can be deleted")
    full = portfolio_path(root, rel)
    if not os.path.lexists(full):
        raise PortfolioError(f"{rel} isn't there any more")
    stem, ext = os.path.splitext(rel) if os.path.isfile(full) else (rel, "")
    dest, n = f"{TRASH_DIR}/{rel}", 1
    while os.path.lexists(os.path.join(os.path.realpath(root), *dest.split("/"))):
        n += 1
        dest = f"{TRASH_DIR}/{stem} ({n}){ext}"
    target = os.path.join(os.path.realpath(root), *dest.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.rename(full, target)
    return dest


def project_name(rel):
    """The project a portfolio path belongs to (its first part)."""
    return rel.split("/", 1)[0] if isinstance(rel, str) else None


def import_notes(text, root, name, split=False):
    """Make projects in the portfolio `root` from one notes file's `text`; -> {project: backlog text}.

    Without `split`: one project called `name`, its backlog the text unchanged (its @ lines become
    sub-groups). With `split`: each @ group becomes a project of that name (its lines unchanged,
    without the @ line), with the section heading above it copied first; tasks outside any @ go to
    `name`. Refused if a backlog it would write already has text.
    """
    if not split:
        out = {name: text}
    else:
        out, heading, target, put = {}, None, name, set()
        for raw in text.splitlines(keepends=True):
            c = raw.strip()
            ws = raw[:len(raw) - len(raw.lstrip())]
            if not c:
                if out.get(target):
                    out[target] += raw
                continue
            if c.startswith("@"):
                target = c[1:].strip().replace("/", "-").replace("\\", "-").replace(":", "-").lstrip(".") or name
                continue
            if not c.startswith("--") and not RE_TASK.match(c) and ws.count("\t") + ws.count(" ") // 4 == 0:
                heading, target, put = raw, name, set()
                continue
            if heading is not None and target not in put:
                body = out.get(target, "")
                if body and not body.endswith(("\n\n", "\r\n\r\n")):
                    body += "\n"
                out[target] = body + (heading if heading.endswith(("\n", "\r")) else heading + "\n")
                put.add(target)
            out[target] = out.get(target, "") + raw
        out = {k: v.rstrip("\r\n") + ("\r\n" if "\r\n" in v else "\n") for k, v in out.items() if v.strip()}
    for project in out:
        _clean_name(project)
        backlog = os.path.join(root, project, PROJECT_FILES["backlog"])
        if read_notes(backlog)[0].strip():
            raise PortfolioError(f"{project} already has a backlog with text in it")
    for project, body in out.items():
        os.makedirs(os.path.join(root, project), exist_ok=True)
        backlog = os.path.join(root, project, PROJECT_FILES["backlog"])
        write_notes(backlog, body, read_notes(backlog)[1])
    return out


def page_data(text, name=None, period=None, plan=None, habits=False, own=None):
    """to_data for one notes text; with `name` (a portfolio page: its project's name) the tasks before
    any @ belong to that project, and `targets` always offers it (line 0 when it has no tasks yet).
    `own` (2.0.25, a project's Backlog): (its habits.kf path, text, version), for Upcoming's and the Planner's
    habits; the habits carry that `path` and `versions` gets its version, so the page edits (ticks) them on disk."""
    projects = parse(text, name)
    hab = None
    if own and not habits:
        hab = parse(own[1], name)
        for hp in hab:
            hp.path, hp.folder = own[0], name
    d = to_data(projects, period, plan, projects if habits else hab, habits)
    if hab is not None:
        d["versions"] = {own[0]: own[2]}
    if name and not any(t["name"] == name and t["line"] for t in d["targets"]):
        d["targets"].insert(0, {"name": name, "line": 0, "path": None, "folder": None, "section": None})
    return d


def portfolio_projects(root, hide=()):
    """Every project's backlog and habits in the portfolio `root` (but the projects named in `hide`), parsed:
    -> (projects, habits, versions, own).
    Each Project gets `path` (its file) and `folder`; sections with the same title become one; `own` lists a
    line-0 target for each project whose backlog has no tasks of its own yet; `versions` maps each file's path
    to its version."""
    projects, versions, sections, own, habits = [], {}, {}, [], []
    for info in portfolio_tree(root)["projects"]:
        if info["name"] in hide:
            continue
        hrel = info["files"]["habits"]
        htext, versions[hrel] = read_notes(portfolio_path(root, hrel))
        for hp in parse(htext, info["name"]):
            hp.path, hp.folder = hrel, info["name"]
            habits.append(hp)
        rel = info["files"]["backlog"]
        text, versions[rel] = read_notes(portfolio_path(root, rel))
        ps = parse(text, info["name"])
        for pr in ps:
            pr.path, pr.folder = rel, info["name"]
            if pr.section is not None:
                pr.section = sections.setdefault(pr.section.title, pr.section)
        if not any(pr.name == info["name"] and pr.section is None and pr.line for pr in ps):
            own.append({"name": info["name"], "line": 0, "path": rel, "folder": info["name"], "section": None})
        projects += ps
    return projects, habits, versions, own


def portfolio_data(root, period=None, plan=None, hide=()):
    """to_data over every project's backlog (All projects; `portfolio_projects`; `hide`: project names to leave
    out), with the habits for the Planner, `targets` led by the line-0 ones, and `versions` for edits."""
    projects, habits, versions, own = portfolio_projects(root, hide)
    d = to_data(projects, period, plan, habits)
    d["targets"] = own + d["targets"]
    d["versions"] = versions
    return d


# ---------- web page ----------

def set_today(val):
    """--today value: Oct12 or 2026-10-12."""
    global TODAY
    m = re.fullmatch("(" + MON + r")(\d{1,2})", val)
    TODAY = date(date.today().year, MONTHS[m.group(1)], int(m.group(2))) if m else date.fromisoformat(val)


def apply_edit(text, req):
    """The text after the edit `req` asks for ({op, line, title, value}); EditError if refused."""
    op = EDITS.get(req["op"])
    if op is None:
        raise EditError(f"unknown edit {req['op']!r} ({', '.join(EDITS)})")
    if isinstance(req["value"], dict) and req["op"] in ("task", "subtask"):
        return add_with_fields(req["op"], text, req["line"], req["value"], req.get("title"))
    if req["op"] == "plan" and isinstance(req["value"], dict):     # {from, to} or {add, remove, past}: set_plan checks it
        pass
    elif not isinstance(req["value"], str):
        raise EditError("value must be text")
    return op(text, req["line"], req["value"], req.get("title"))


def own_habits(root, name, req):
    """2.0.25: (path, text, version) of the project `name`'s habits.kf for its Backlog page, or None (not a
    portfolio, a Habits or archive page, no such project)."""
    if not root or not name or req.get("habits") or req.get("year") is not None:
        return None
    rel = f"{name}/habits.kf"
    try:
        p = portfolio_path(root, rel)
    except PortfolioError:
        return None
    if not os.path.isdir(os.path.dirname(p)):
        return None
    return (rel,) + read_notes(p)


def _hide(req):
    """A request's `hide`: project names to leave out of All projects (the projects hidden in the page's drawer)."""
    hide = req.get("hide") or []
    if not isinstance(hide, list) or not all(isinstance(x, str) for x in hide):
        raise ValueError("hide must be a list of project names")
    return tuple(hide)


# ---------- sync (2.1.x): a hub on the user's home server keeps every device's Projects folder the same ----------
#
# The hub is an ordinary --serve with --hub: its Projects folder is the master copy. It logs every change to a file
# or folder (made through it, on its own page, or by hand) with a number, keeps every version of every file by its
# SHA-256 (blobs, the bases devices merge against), and answers /sync/* for devices that know the pairing code.
# Its state lives in Projects/.kafeen/ (hidden: never listed, served or synced).

SYNC_DIR = ".kafeen"


def _sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def sync_path(root, rel):
    """The real path of `rel` (a file or folder, "/" between parts) inside `root`; ValueError if it can't be synced:
    empty or hidden parts (so no .., .kafeen, .trash), backslashes, or a way out (a symlink)."""
    if not isinstance(rel, str) or not rel or "\\" in rel or "\0" in rel:
        raise ValueError(f"{rel!r} can't be synced")
    parts = rel.split("/")
    if any(not x or x.startswith(".") for x in parts):
        raise ValueError(f"{rel!r} can't be synced")
    root = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root, *parts))
    if not full.startswith(root.rstrip(os.sep) + os.sep):
        raise ValueError(f"{rel!r} is outside the folder")
    return full


def write_bytes(path, data):
    """Write `data` to `path` exactly (atomic: a temp file, then rename), making its folder if needed."""
    import tempfile
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".planner-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        mode = os.stat(path).st_mode & 0o7777 if os.path.exists(path) else 0o666 & ~_umask()
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _umask():
    m = os.umask(0)
    os.umask(m)
    return m


def to_trash(root, rel):
    """Move the file or folder `rel` to root/.trash/<rel> (" (2)" etc. if taken); -> where it went. Never deletes."""
    root = os.path.realpath(root)
    full = os.path.join(root, *rel.split("/"))
    stem, ext = os.path.splitext(rel) if os.path.isfile(full) else (rel, "")
    dest, n = f"{TRASH_DIR}/{rel}", 1
    while os.path.lexists(os.path.join(root, *dest.split("/"))):
        n += 1
        dest = f"{TRASH_DIR}/{stem} ({n}){ext}"
    target = os.path.join(root, *dest.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.rename(full, target)
    return dest


def scan_tree(root, cache, keep):
    """-> ({file: sha256}, {folder}, new cache) of everything under `root` but hidden names; `cache` {file: ((size,
    mtime_ns), sha256)} saves reading files that didn't change; `keep(data)` stores a new version, -> its hash."""
    files, dirs, stats = {}, set(), {}
    for here, ds, fs in os.walk(root):
        ds[:] = sorted(d for d in ds if not d.startswith("."))
        rel = os.path.relpath(here, root).replace(os.sep, "/")
        rel = "" if rel == "." else rel + "/"
        dirs.update(rel + d for d in ds)
        for name in fs:
            if name.startswith("."):
                continue
            p, key = os.path.join(here, name), rel + name
            try:
                st = os.stat(p)
            except OSError:
                continue
            sig = (st.st_size, st.st_mtime_ns)
            old = cache.get(key)
            if old and old[0] == sig:
                h = old[1]
            else:
                try:
                    with open(p, "rb") as f:
                        h = keep(f.read())
                except OSError:
                    continue
            files[key], stats[key] = h, (sig, h)
    return files, dirs, stats


def setup_hub(root, new=False):
    """Make this Projects folder a hub (2.1.1); -> the pairing code, shown once (only its hash is kept).
    ValueError if it is one already, unless `new` (a new code: every device must pair again)."""
    import json
    import secrets
    folder = os.path.join(root, SYNC_DIR)
    conf = os.path.join(folder, "hub.json")
    if os.path.exists(conf) and not new:
        raise ValueError("this folder is a hub already (--setup-hub --new-code makes a new pairing code)")
    os.makedirs(folder, exist_ok=True)
    code = "kfn-" + secrets.token_urlsafe(18)
    write_bytes(conf, json.dumps({"token": _sha(code.encode()), "made": datetime.now().isoformat(timespec="seconds")},
                                 indent=1).encode())
    return code


class Hub:
    """The hub's record of the folder (2.1.1): `files` {path: sha256}, `dirs` {path}, every change numbered in
    `entries` (and .kafeen/log.jsonl), every version in .kafeen/blobs/. `refresh` takes in what changed on disk."""

    def __init__(self, root):
        import json
        import threading
        self.root, self.dir = os.path.realpath(root), os.path.join(os.path.realpath(root), SYNC_DIR)
        try:
            with open(os.path.join(self.dir, "hub.json")) as f:
                self.token = json.load(f)["token"]
        except (OSError, ValueError, KeyError):
            raise ValueError("this folder isn't a hub yet: run planner.py --setup-hub first")
        self.cond = threading.Condition()
        self.files, self.dirs, self.entries, self.stats = {}, set(), [], {}
        self.blobs, self.log = os.path.join(self.dir, "blobs"), os.path.join(self.dir, "log.jsonl")
        os.makedirs(self.blobs, exist_ok=True)
        try:
            with open(self.log, encoding="utf-8") as f:
                for line in f:
                    try:
                        self._apply(json.loads(line))
                    except (ValueError, KeyError):
                        pass                            # a line cut short by a crash
        except FileNotFoundError:
            pass
        self.refresh("hub")                             # changes made while the hub wasn't running

    @property
    def seq(self):
        return self.entries[-1]["seq"] if self.entries else 0

    def allowed(self, header):
        import hmac
        code = header[7:].strip() if isinstance(header, str) and header.startswith("Bearer ") else ""
        return bool(code) and hmac.compare_digest(_sha(code.encode()), self.token)

    def _apply(self, e):
        self.entries.append(e)
        if e["kind"] == "put":
            self.files[e["path"]] = e["hash"]
        elif e["kind"] == "delete":
            self.files.pop(e["path"], None)
        elif e["kind"] == "mkdir":
            self.dirs.add(e["path"])
        elif e["kind"] == "rmdir":
            self.dirs.discard(e["path"])

    def _record(self, kind, path, h, device):
        import json
        e = {"seq": self.seq + 1, "kind": kind, "path": path, "hash": h, "device": device,
             "time": datetime.now().isoformat(timespec="seconds")}
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        self._apply(e)
        return e

    def blob(self, h):
        """A version's bytes by its hash, or None."""
        if not (isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)):
            return None
        try:
            with open(os.path.join(self.blobs, h), "rb") as f:
                return f.read()
        except OSError:
            return None

    def keep(self, data):
        h = _sha(data)
        p = os.path.join(self.blobs, h)
        if not os.path.exists(p):
            write_bytes(p, data)
        return h

    def refresh(self, device="hub"):
        """Log what differs between the record and the disk (files by content); -> the new entries."""
        with self.cond:
            files, dirs, self.stats = scan_tree(self.root, self.stats, self.keep)
            new = []
            for d in sorted(dirs - self.dirs):
                new.append(self._record("mkdir", d, None, device))
            for k in sorted(files):
                if self.files.get(k) != files[k]:
                    new.append(self._record("put", k, files[k], device))
            for k in sorted(set(self.files) - set(files)):
                new.append(self._record("delete", k, None, device))
            for d in sorted(self.dirs - dirs, reverse=True):
                new.append(self._record("rmdir", d, None, device))
            if new:
                self.cond.notify_all()
            return new

    def state(self):
        with self.cond:
            self.refresh("hub")                         # what's on disk now, edits on the hub included
            return {"seq": self.seq, "files": dict(self.files), "dirs": sorted(self.dirs)}

    def changes(self, since, wait):
        """{seq, changes: [entries after `since`]}, waiting up to `wait` s for one; {reset: true} if `since` is
        ahead of the hub (a hub set up again): the device then starts over from /sync/state."""
        with self.cond:
            if since > self.seq:
                return {"seq": self.seq, "reset": True, "changes": []}
            self.cond.wait_for(lambda: self.seq > since, wait)
            return {"seq": self.seq, "changes": [e for e in self.entries[since:] if e["seq"] > since]}

    def put(self, rel, base, data, device):
        """A device's version of a file, made from `base` (the hash it last had; None: new). -> {status: ok | merged
        | conflict, hash (the hub's now), data (merged: the merged bytes)}. Nothing is lost: a clash leaves the
        hub's file as it is, and the device keeps its version."""
        full = sync_path(self.root, rel)
        with self.cond:
            self.refresh("hub")                         # edits made on the hub itself come first
            cur = self.files.get(rel)
            if os.path.isdir(full):
                return {"status": "conflict", "hash": None, "error": f"{rel} is a folder here"}
            if cur == _sha(data):
                return {"status": "ok", "hash": cur}
            if cur is None or cur == base:              # new, unchanged here since, or deleted here (an edit wins)
                write_bytes(full, data)
                self.refresh(device)
                return {"status": "ok", "hash": self.files.get(rel)}
            if rel == SETTINGS_FILE:                    # 2.1.4: settings merge setting by setting
                merged = merge_settings(None if base is None else self.blob(base), data, self.blob(cur))
                if merged is not None:
                    write_bytes(full, merged)
                    self.refresh(device)
                    return {"status": "merged", "hash": self.files.get(rel), "data": merged}
            if base is None:                            # two different files that never had a common version
                return {"status": "conflict", "hash": cur}
            old, theirs = self.blob(base), self.blob(cur)
            try:
                if old is None or theirs is None:
                    raise ValueError
                merged, clashes = merge3(old.decode("utf-8"), data.decode("utf-8"), theirs.decode("utf-8"))
            except ValueError:                          # not text, or a base the hub never had
                return {"status": "conflict", "hash": cur}
            if clashes:
                return {"status": "conflict", "hash": cur, "clashes": clashes}
            out = merged.encode("utf-8")
            write_bytes(full, out)
            self.refresh(device)
            return {"status": "merged", "hash": self.files.get(rel), "data": out}

    def delete(self, rel, base, device):
        """A device deleted a file it had at `base`: it goes to .trash here too, unless it changed here since
        (then it stays: {status: changed}, and the device takes it back)."""
        full = sync_path(self.root, rel)
        with self.cond:
            self.refresh("hub")
            cur = self.files.get(rel)
            if cur is None:
                return {"status": "ok", "hash": None}
            if cur != base:
                return {"status": "changed", "hash": cur}
            to_trash(self.root, rel)
            self.refresh(device)
            return {"status": "ok", "hash": None}

    def mkdir(self, rel, device):
        full = sync_path(self.root, rel)
        with self.cond:
            if os.path.isfile(full):
                return {"status": "conflict", "error": f"{rel} is a file here"}
            os.makedirs(full, exist_ok=True)
            self.refresh(device)
            return {"status": "ok"}

    def rmdir(self, rel, device):
        """A device removed a folder: here it goes to .trash if nothing visible is left in it, else it stays."""
        full = sync_path(self.root, rel)
        with self.cond:
            self.refresh("hub")
            if not os.path.isdir(full):
                return {"status": "ok"}
            if any(not n.startswith(".") for _, ds, fs in os.walk(full) for n in fs):
                return {"status": "changed"}
            to_trash(self.root, rel)
            self.refresh(device)
            return {"status": "ok"}


def _sync_request(hub, code, name, method, path, payload=None, timeout=15):
    """One request to the hub; -> parsed JSON (or bytes for a blob). ValueError("unauthorized") for a wrong code;
    OSError when the hub can't be reached (offline)."""
    import json
    import urllib.error
    import urllib.request
    headers = {"Authorization": "Bearer " + code, "X-Kafeen-Device": name}
    data = None
    if payload is not None:
        data, headers["Content-Type"] = json.dumps(payload).encode(), "application/json"
    req = urllib.request.Request(hub + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return json.loads(body) if r.headers.get("Content-Type") == "application/json" else body
    except urllib.error.HTTPError as e:
        with e:
            if e.code == 401:
                raise ValueError("unauthorized: the pairing code is wrong (pair again with the hub's code)")
            raise OSError(f"the hub answered {e.code}")


def pair(root, hub, code, name=None):
    """Pair the Projects folder `root` with the hub at `hub` (2.1.2): checks the code, writes .kafeen/device.json
    (readable only by you: it holds the code); -> the hub's state. ValueError if refused or unreachable."""
    import json
    import socket
    from urllib.parse import urlsplit
    if os.path.exists(os.path.join(root, SYNC_DIR, "hub.json")):
        raise ValueError("this folder is the hub itself")
    hub = hub.strip().rstrip("/")
    if "://" not in hub:
        hub = "http://" + hub
    u = urlsplit(hub)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError(f"{hub!r} isn't a hub address (like http://kafeen-hub:8765)")
    if u.port is None and u.scheme == "http":
        hub += ":8765"
    name = (name or socket.gethostname().split(".")[0] or "a device")[:60]
    try:
        state = _sync_request(hub, code, name, "GET", "/sync/state")
    except OSError as e:
        raise ValueError(f"can't reach the hub at {hub} ({e}); is it running, and is Tailscale on?")
    os.makedirs(os.path.join(root, SYNC_DIR), exist_ok=True)
    path = os.path.join(root, SYNC_DIR, "device.json")
    write_bytes(path, json.dumps({"hub": hub, "code": code, "name": name, "seq": 0, "base": {}, "dirs": []}, indent=1).encode())
    os.chmod(path, 0o600)
    return state


class SyncClient:
    """A paired device's sync (2.1.2): keeps `root` equal to the hub's folder. Each round compares, per path, the
    file here (L), the version last agreed with the hub (B, the base) and the hub's (H): L = H agree; L = B: only the
    hub changed (pull, or a delete goes to .trash here); else this device changed it (put, which the hub merges, or
    delete). A clash keeps the hub's version here and saves this device's in .kafeen/conflicts/. Rounds run when
    the hub says something changed (a long-poll), when a file here changes (`kick`), and every minute."""

    BACKOFF = (1, 2, 5, 10, 30)

    def __init__(self, root, lock=None, on_change=None, on_status=None):
        import json
        import threading
        self.root = os.path.realpath(root)
        self.dir = os.path.join(self.root, SYNC_DIR)
        self.conf_path = os.path.join(self.dir, "device.json")
        with open(self.conf_path) as f:
            self.conf = json.load(f)
        self.hub, self.code, self.name = self.conf["hub"], self.conf["code"], self.conf["name"]
        self.base, self.bdirs = dict(self.conf.get("base", {})), set(self.conf.get("dirs", []))
        self.seq = self.conf.get("seq", 0)
        self.lock = lock or threading.RLock()
        self.on_change, self.on_status = on_change, on_status
        self.blobs = os.path.join(self.dir, "blobs")
        self.conflicts = os.path.join(self.dir, "conflicts")
        os.makedirs(self.blobs, exist_ok=True)
        self.cache, self.wake, self.stop = {}, threading.Event(), threading.Event()
        self.status = {"state": "syncing", "waiting": 0, "conflicts": self._conflict_count(), "hub": self.hub,
                       "name": self.name, "last": None, "error": None}

    @staticmethod
    def paired(root):
        return os.path.exists(os.path.join(root, SYNC_DIR, "device.json"))

    # ---- storage ----
    def keep(self, data):
        h = _sha(data)
        p = os.path.join(self.blobs, h)
        if not os.path.exists(p):
            write_bytes(p, data)
        return h

    def blob(self, h):
        try:
            with open(os.path.join(self.blobs, h), "rb") as f:
                return f.read()
        except OSError:
            return None

    def _save(self):
        import json
        self.conf.update(seq=self.seq, base=self.base, dirs=sorted(self.bdirs))
        write_bytes(self.conf_path, json.dumps(self.conf, indent=1).encode())

    def _conflict_count(self):
        try:
            return len([n for n in os.listdir(self.conflicts) if n.endswith(".json")])
        except OSError:
            return 0

    def recount(self):
        """The clashes kept aside changed (one was resolved): tell the pages."""
        self._set(conflicts=self._conflict_count())

    def _set(self, **kw):
        self.status.update(kw)
        if self.on_status:
            self.on_status(dict(self.status))

    # ---- the hub ----
    def _req(self, method, path, payload=None, timeout=15):
        return _sync_request(self.hub, self.code, self.name, method, path, payload, timeout)

    def _local(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def _hash_now(self, rel):
        try:
            with open(self._local(rel), "rb") as f:
                return _sha(f.read())
        except OSError:
            return None

    def _write(self, rel, data, expect):
        """Write the hub's version here, unless the file changed since this round looked (then the next round
        sees it); -> whether it was written."""
        with self.lock:
            if self._hash_now(rel) != expect:
                return False
            write_bytes(self._local(rel), data)
            return True

    def _pull(self, rel, h, expect):
        data = self.blob(h)
        if data is None:
            data = self._req("GET", "/sync/blob/" + h)
            self.keep(data)
        if self._write(rel, data, expect):
            self.base[rel] = h
            return True
        return False

    def _clash(self, rel, mine, base, theirs, clashes):
        import json
        os.makedirs(self.conflicts, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        n = len(os.listdir(self.conflicts)) + 1
        rec = {"path": rel, "device": self.name, "time": datetime.now().isoformat(timespec="seconds"),
               "base": base, "theirs": theirs, "mine": self.keep(mine), "clashes": clashes or []}
        write_bytes(os.path.join(self.conflicts, f"{stamp}-{n}.json"), json.dumps(rec, indent=1).encode())

    def round(self):
        """Bring this folder and the hub's into step once; -> {pulled, pushed, merged, conflicts}."""
        import base64
        st = self._req("GET", "/sync/state")
        with self.lock:
            files, dirs, self.cache = scan_tree(self.root, self.cache, self.keep)
        H, HD = st["files"], set(st["dirs"])
        n = {"pulled": 0, "pushed": 0, "merged": 0, "conflicts": 0}
        for d in sorted(HD | dirs):                    # folders first (a new section, an empty archive/)
            here, there, known = d in dirs, d in HD, d in self.bdirs
            if here and there:
                self.bdirs.add(d)
            elif there and not known:
                with self.lock:
                    os.makedirs(self._local(d), exist_ok=True)
                self.bdirs.add(d)
                n["pulled"] += 1
            elif here and not known:
                self._req("POST", "/sync/mkdir", {"path": d})
                self.bdirs.add(d)
                n["pushed"] += 1
        for rel in sorted(set(files) | set(H) | set(self.base)):
            L, B, Hh = files.get(rel), self.base.get(rel), H.get(rel)
            if L == Hh:
                if L is None:
                    self.base.pop(rel, None)
                else:
                    self.base[rel] = L
                continue
            if L == B:                                  # only the hub changed it
                if Hh is None:
                    with self.lock:
                        if self._hash_now(rel) == L:
                            to_trash(self.root, rel)
                            self.base.pop(rel, None)
                            n["pulled"] += 1
                elif self._pull(rel, Hh, L):
                    n["pulled"] += 1
                continue
            if L is None:                               # deleted here
                r = self._req("POST", "/sync/delete", {"path": rel, "base": B})
                if r["status"] == "ok":
                    self.base.pop(rel, None)
                    n["pushed"] += 1
                elif self._pull(rel, r["hash"], None):  # changed on another device meanwhile: it comes back
                    n["pulled"] += 1
                continue
            mine = self.blob(L)
            r = self._req("POST", "/sync/put", {"path": rel, "base": B, "data": base64.b64encode(mine).decode()})
            if r["status"] == "ok":
                self.base[rel] = r["hash"]
                n["pushed"] += 1
            elif r["status"] == "merged":
                merged = base64.b64decode(r["data"])
                self.keep(merged)
                if self._write(rel, merged, L):
                    self.base[rel] = r["hash"]
                n["merged"] += 1
            else:                                       # a clash: the hub's version here, this one kept aside
                self._clash(rel, mine, B, r["hash"], r.get("clashes"))
                if r["hash"] is None or self._pull(rel, r["hash"], L):
                    n["conflicts"] += 1
        for d in sorted(self.bdirs - (HD & dirs), reverse=True):   # folders gone on one side
            if d in dirs and d not in HD:               # removed on the hub: here too, if nothing visible is left
                with self.lock:
                    full = self._local(d)
                    if not any(not x.startswith(".") for _, _, fs in os.walk(full) for x in fs):
                        to_trash(self.root, d)
                        self.bdirs.discard(d)
            elif d in HD and d not in dirs:             # removed here
                if self._req("POST", "/sync/rmdir", {"path": d})["status"] == "ok":
                    self.bdirs.discard(d)
                else:
                    with self.lock:
                        os.makedirs(self._local(d), exist_ok=True)
            else:
                self.bdirs.discard(d)
        self.seq = max(self.seq, st["seq"])
        self._save()
        if any(n.values()) and self.on_change:
            self.on_change()
        self._set(state="synced", waiting=0, conflicts=self._conflict_count(), error=None,
                  last=datetime.now().isoformat(timespec="seconds"))
        return n

    def waiting(self):
        """How many files and folders here differ from the last version agreed with the hub (to send)."""
        with self.lock:
            files, dirs, self.cache = scan_tree(self.root, self.cache, self.keep)
        return (sum(files.get(k) != self.base.get(k) for k in set(files) | set(self.base))
                + len(dirs ^ self.bdirs))

    # ---- the threads ----
    def kick(self):
        self.wake.set()

    def start(self):
        import threading
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._poll, daemon=True).start()
        self.kick()

    def close(self):
        self.stop.set()
        self.wake.set()

    def _run(self):
        import time
        fails = 0
        while not self.stop.is_set():
            self.wake.wait(self.BACKOFF[min(fails, len(self.BACKOFF)) - 1] if fails else 60)
            if self.stop.is_set():
                break
            self.wake.clear()
            time.sleep(0.3)                             # a burst of edits goes in one round
            self._set(state="syncing")
            try:
                self.round()
                fails = 0
            except ValueError as e:                     # refused (a wrong code): wait for the user
                self._set(state="error", error=str(e))
                fails = len(self.BACKOFF)
            except (OSError, KeyError) as e:
                fails += 1
                try:
                    waiting = self.waiting()
                except OSError:
                    waiting = self.status.get("waiting", 0)
                self._set(state="offline", waiting=waiting, error=str(e))

    def _poll(self):
        seq = self.seq
        while not self.stop.is_set():
            try:
                d = self._req("GET", f"/sync/changes?since={seq}&wait=25", timeout=35)
                if d.get("reset"):
                    seq = 0
                    self.kick()
                    continue
                if any(e.get("device") != self.name for e in d["changes"]):
                    self.kick()                         # another device (or the hub) changed something
                seq = d["seq"]
            except (OSError, ValueError, KeyError):
                if self.status.get("state") not in ("offline", "error"):
                    self.kick()                         # let a round find out what's wrong and say so
                self.stop.wait(5)


# ---- clashes (2.1.3): a device's change that the hub couldn't merge, kept aside until the user chooses ----

RE_CLASH_ID = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9]+")


def _clash_dir(root):
    return os.path.join(root, SYNC_DIR, "conflicts")


def list_clashes(root):
    """[{id, path, device, time, whole, clashes: [{line, base, mine, theirs}]}] of the clashes kept aside on this
    device, oldest first. `whole`: the files couldn't be merged line by line (different from the start, or not text):
    the choice is between the two whole files."""
    import json
    folder, out = _clash_dir(root), []
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError:
        return []
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        out.append({"id": n[:-5], "path": rec["path"], "device": rec.get("device"), "time": rec.get("time"),
                    "whole": not rec.get("clashes"), "clashes": rec.get("clashes") or [],
                    "mine": None if rec.get("clashes") else _blob_text(root, rec.get("mine"))})
    return out


def _blob_text(root, h):
    try:
        with open(os.path.join(root, SYNC_DIR, "blobs", h), "rb") as f:
            return f.read().decode("utf-8")
    except (OSError, TypeError, UnicodeDecodeError):
        return None


def _blob_bytes(root, h):
    try:
        with open(os.path.join(root, SYNC_DIR, "blobs", h), "rb") as f:
            return f.read()
    except (OSError, TypeError):
        return None


def _find_block(lines, block, near):
    """Where the lines `block` stand in `lines` (ignoring line endings), the place nearest to `near`; None if not."""
    key = [x.rstrip("\r\n") for x in block]
    flat = [x.rstrip("\r\n") for x in lines]
    if not key:
        return min(max(near, 0), len(lines))
    spots = [i for i in range(len(flat) - len(key) + 1) if flat[i:i + len(key)] == key]
    return min(spots, key=lambda i: abs(i - near)) if spots else None


def resolve_clash(root, cid, choices):
    """Apply the user's choice for a clash kept aside (2.1.3) and file it under conflicts/resolved/.

    Line clashes: `choices` has one of "theirs" (keep what's there now), "mine" (this device's lines instead) or
    "both" (theirs, then this device's) per clash, applied to the file as it is now: the lines kept are found again
    by their text, so later edits elsewhere in the file don't matter. A whole-file clash takes one choice: "theirs",
    "mine" (this device's file instead) or "both" (this device's file saved beside it, as "NAME (from DEVICE)").
    -> {path, before, version, copy} (before/version: for Undo; copy: the new file's path for "both"), or
    ValueError if it can't be applied (the lines changed since: edit them by hand, then dismiss)."""
    import json
    if not isinstance(cid, str) or not RE_CLASH_ID.fullmatch(cid):
        raise ValueError("no such clash")
    rec_path = os.path.join(_clash_dir(root), cid + ".json")
    try:
        with open(rec_path, encoding="utf-8") as f:
            rec = json.load(f)
    except OSError:
        raise ValueError("no such clash (resolved already?)")
    rel, clashes = rec["path"], rec.get("clashes") or []
    full = sync_path(root, rel)
    text, version = read_notes(full) if os.path.isfile(full) else ("", None)
    out = {"path": rel, "before": text, "version": version, "copy": None}
    allowed = {"theirs", "mine", "both", "dismiss"}
    if not isinstance(choices, list) or not all(c in allowed for c in choices):
        raise ValueError("choose theirs, mine or both")
    if choices == ["dismiss"] or all(c in ("theirs", "dismiss") for c in choices):
        pass                                            # keep what's there: nothing to write
    elif not clashes:                                   # the whole file
        mine = _blob_bytes(root, rec.get("mine"))
        if mine is None:
            raise ValueError("this device's version is missing")
        if choices[0] == "mine":
            write_bytes(full, mine)
        else:
            stem, ext = os.path.splitext(rel)
            copy, n = f"{stem} (from {rec.get('device') or 'another device'}){ext}", 1
            while os.path.exists(sync_path(root, copy)):
                n += 1
                copy = f"{stem} (from {rec.get('device') or 'another device'} {n}){ext}"
            write_bytes(sync_path(root, copy), mine)
            out["copy"] = copy
    else:
        if len(choices) != len(clashes):
            raise ValueError("one choice per clash")
        lines = text.splitlines(keepends=True)
        eol = "\r\n" if "\r\n" in text else "\n"
        shift = 0
        for c, k in sorted(zip(choices, clashes), key=lambda x: x[1]["line"]):
            if c == "theirs":
                continue
            at = _find_block(lines, k["theirs"], k["line"] - 1 + shift)
            if at is None:
                raise ValueError(f"line {k['line']} of {rel} changed since; edit it by hand, then choose \"Keep what's there\"")
            mine = [x.rstrip("\r\n") + eol for x in k["mine"]]
            if at + len(k["theirs"]) == len(lines) and lines and not lines[-1].endswith(("\n", "\r")) and mine:
                mine[-1] = mine[-1].rstrip("\r\n")    # the file had no line ending at the end: still none
                if c == "both":
                    lines[-1] += eol
            new = (lines[at:at + len(k["theirs"])] if c == "both" else []) + mine
            lines[at:at + len(k["theirs"])] = new
            shift += len(new) - len(k["theirs"])
        try:
            out["version"] = write_notes(full, "".join(lines), version)
        except FileConflict:
            raise ValueError(f"{rel} changed just now; try again")
    done = os.path.join(_clash_dir(root), "resolved")
    os.makedirs(done, exist_ok=True)
    rec["resolved"] = {"choices": choices, "time": datetime.now().isoformat(timespec="seconds")}
    write_bytes(os.path.join(done, cid + ".json"), json.dumps(rec, indent=1).encode())
    os.remove(rec_path)
    return out


# ---- settings that follow you across devices (2.1.4): Projects/settings.json, an ordinary synced file ----

SETTINGS_FILE = "settings.json"
SETTINGS = {"hiddenProjects": [], "defWho": "", "defEffort": ""}


def _setting_ok(key, value):
    if key == "hiddenProjects":
        return isinstance(value, list) and len(value) <= 500 and all(isinstance(x, str) and 0 < len(x) <= 120 for x in value)
    if key == "defWho":
        return isinstance(value, str) and len(value) <= 14
    if key == "defEffort":
        return value in ("", *EFFORT)
    return False


def read_settings(root):
    """-> ({setting: value} for the settings in Projects/settings.json, its version); bad or unknown ones left out."""
    import json
    text, version = read_notes(os.path.join(root, SETTINGS_FILE))
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {k: v for k, v in data.items() if k in SETTINGS and _setting_ok(k, v)}, version


def write_settings(root, changes):
    """Set some settings (ValueError for an unknown setting or a bad value); -> the settings now. One setting per line
    (sorted), so two devices changing different settings merge line by line like any notes file."""
    import json
    if not isinstance(changes, dict) or not all(k in SETTINGS and _setting_ok(k, v) for k, v in changes.items()):
        raise ValueError("unknown setting or bad value")
    current, version = read_settings(root)
    new = dict(current, **changes)
    if new != current or version is None:
        write_notes(os.path.join(root, SETTINGS_FILE), settings_text(new), version)
    return new


def settings_text(settings):
    import json
    lines = [f"  {json.dumps(k)}: {json.dumps(settings[k], ensure_ascii=False)}" for k in sorted(settings)]
    return "{\n" + ",\n".join(lines) + "\n}\n"


def merge_settings(base, mine, theirs):
    """settings.json changed on two devices (bytes; base None: both made it): setting by setting, never a clash.
    A setting this device changed is its; otherwise the hub's. -> the merged bytes, or None if not settings."""
    import json
    try:
        b, m, t = (json.loads(x.decode("utf-8")) if x and x.strip() else {} for x in (base, mine, theirs))
    except ValueError:
        return None
    if not all(isinstance(x, dict) for x in (b, m, t)):
        return None
    out = dict(t)
    for k, v in m.items():
        if b.get(k) != v:
            out[k] = v
    for k in b:
        if k not in m and t.get(k) == b[k]:
            out.pop(k, None)
    return settings_text(out).encode("utf-8")


# ---- backups on the hub (2.1.4): a zip of the notes once a day, the newest BACKUPS_KEPT kept ----

BACKUPS_KEPT, BLOB_DAYS = 30, 90


def hub_backup(root, now=None):
    """Zip every visible file under `root` into .kafeen/backups/YYYY-MM-DD-HHMM.zip, keep the newest BACKUPS_KEPT;
    -> the zip's path."""
    import zipfile
    now = now or datetime.now()
    folder = os.path.join(root, SYNC_DIR, "backups")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, now.strftime("%Y-%m-%d-%H%M") + ".zip")
    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for here, ds, fs in os.walk(root):
            ds[:] = sorted(d for d in ds if not d.startswith("."))
            for name in sorted(fs):
                if not name.startswith("."):
                    full = os.path.join(here, name)
                    z.write(full, os.path.relpath(full, root).replace(os.sep, "/"))
    os.replace(tmp, path)
    for old in sorted(n for n in os.listdir(folder) if n.endswith(".zip"))[:-BACKUPS_KEPT]:
        os.remove(os.path.join(folder, old))
    return path


def backup_due(root, now=None, hours=20):
    """Whether the newest backup is older than `hours` (or there is none)."""
    folder = os.path.join(root, SYNC_DIR, "backups")
    try:
        newest = max((n for n in os.listdir(folder) if n.endswith(".zip")), default=None)
    except OSError:
        newest = None
    if newest is None:
        return True
    try:
        made = datetime.strptime(newest[:15], "%Y-%m-%d-%H%M")
    except ValueError:
        return True
    return ((now or datetime.now()) - made).total_seconds() > hours * 3600


def prune_blobs(hub, days=BLOB_DAYS):
    """Old versions on the hub: remove those older than `days` that no file is at now; -> how many went.
    (A device away longer than that merges a clash as a whole-file choice instead.)"""
    import time
    limit, keep, n = time.time() - days * 86400, set(hub.files.values()), 0
    for name in os.listdir(hub.blobs):
        p = os.path.join(hub.blobs, name)
        try:
            if name not in keep and os.stat(p).st_mtime < limit:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


# ---- start at login (2.1.4): --autostart on|off ----

def autostart_plan(system, hub=False, port=8765, python=None, script=None, home=None, uid=None):
    """-> (the file to write, its content, [commands to start it now], [commands to stop it]) for `system` ("Linux",
    "Darwin" or "Windows"); ValueError for another."""
    import shlex
    python = python or sys.executable
    script = script or os.path.abspath(__file__)
    home = home or os.path.expanduser("~")
    args = [python, script, "--serve", "--no-browser", "--port", str(port)] + (["--hub", "--host", "0.0.0.0"] if hub else [])
    name = "kafeen-hub" if hub else "kafeen"
    if system == "Linux":
        path = os.path.join(home, ".config", "systemd", "user", name + ".service")
        content = (f"[Unit]\nDescription=KAFEEN Planner{' sync hub' if hub else ''}\nAfter=network-online.target\n\n"
                   f"[Service]\nExecStart={shlex.join(args)}\nWorkingDirectory={os.path.dirname(script)}\n"
                   "Restart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n")
        return (path, content, [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", name + ".service"]],
                [["systemctl", "--user", "disable", "--now", name + ".service"]])
    if system == "Darwin":
        label = "com.kafeen." + name
        path = os.path.join(home, "Library", "LaunchAgents", label + ".plist")
        log = os.path.join(home, "Library", "Logs", name + ".log")
        x = lambda v: v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        content = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                   '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n'
                   f"\t<key>Label</key>\n\t<string>{x(label)}</string>\n\t<key>ProgramArguments</key>\n\t<array>\n"
                   + "".join(f"\t\t<string>{x(a)}</string>\n" for a in args)
                   + "\t</array>\n\t<key>RunAtLoad</key>\n\t<true/>\n\t<key>KeepAlive</key>\n\t<true/>\n"
                   f"\t<key>WorkingDirectory</key>\n\t<string>{x(os.path.dirname(script))}</string>\n"
                   f"\t<key>StandardOutPath</key>\n\t<string>{x(log)}</string>\n"
                   f"\t<key>StandardErrorPath</key>\n\t<string>{x(log)}</string>\n</dict>\n</plist>\n")
        target = f"gui/{os.getuid() if uid is None else uid}"
        return path, content, [["launchctl", "bootstrap", target, path]], [["launchctl", "bootout", target, path]]
    if system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        path = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
                            "KAFEEN Planner" + (" hub" if hub else "") + ".cmd")
        w = os.path.join(os.path.dirname(python), "pythonw.exe")
        runner = w if os.path.exists(w) else python
        quoted = " ".join([f'"{runner}"', f'"{script}"'] + args[2:])
        return path, f'@echo off\r\nstart "" {quoted}\r\n', [["cmd", "/c", path]], []
    raise ValueError(f"--autostart doesn't know {system} yet")


def autostart(on, hub=False, port=8765):
    """Turn starting at login on or off for this computer; -> lines to print."""
    import platform
    import subprocess
    path, content, start, stop = autostart_plan(platform.system(), hub, port)
    out = []
    run = lambda cmd: subprocess.run(cmd, capture_output=True, text=True)
    if on:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            for cmd in stop:
                run(cmd)                                # replace a running one
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        out.append(f"KAFEEN{' (the sync hub)' if hub else ''} now starts when you log in ({path}).")
        for cmd in start:
            try:
                r = run(cmd)
                if r.returncode:
                    out.append(f"Couldn't start it now ({' '.join(cmd)}: {(r.stderr or r.stdout).strip()}); it starts at the next login.")
                    break
            except OSError as e:
                out.append(f"Couldn't start it now ({e}); it starts at the next login.")
                break
        else:
            out.append(f"It's running: open http://localhost:{port}")
        if hub and platform.system() == "Linux":
            out.append("So the hub runs even before you log in (after a power cut), run once:  loginctl enable-linger $USER")
    else:
        if not os.path.exists(path):
            return ["KAFEEN wasn't set to start at login."]
        for cmd in stop:
            try:
                run(cmd)
            except OSError:
                pass
        os.remove(path)
        out.append("KAFEEN no longer starts at login (it stopped now too).")
    return out


class Changes:
    """2.1.0: what changed on disk, for the pages listening on /api/events: a counter and the last changes."""

    def __init__(self):
        import threading
        self.cond, self.seq, self.log, self.closed = threading.Condition(), 0, [], False
        self.status = None                              # 2.1.2: the sync status, for the pages ({state, waiting, ...})

    def publish(self, paths, tree=False):
        with self.cond:
            self.seq += 1
            self.log = self.log[-199:] + [(self.seq, sorted(paths), tree)]
            self.cond.notify_all()

    def publish_status(self, status):
        """2.1.2: a new sync status (an entry with no paths: the pages get the latest status)."""
        with self.cond:
            if status == self.status:
                return
            self.status, self.seq = status, self.seq + 1
            self.log = self.log[-199:] + [(self.seq, None, False)]
            self.cond.notify_all()

    def since(self, n, wait):
        """-> (the newest number, [(number, paths, tree)] after `n`), waiting up to `wait` seconds for one."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > n or self.closed, wait)
            return self.seq, [e for e in self.log if e[0] > n]

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify_all()


def scan_files(root=None, path=None):
    """{name: (size, mtime_ns)} of the notes the page can show: every file and folder under `root` (a portfolio;
    names relative to it, folders ending in "/", hidden ones skipped), or the one file `path`."""
    out = {}
    if path is not None:
        try:
            st = os.stat(path)
            out[path] = (st.st_size, st.st_mtime_ns)
        except OSError:
            pass
        return out
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel = os.path.relpath(here, root).replace(os.sep, "/")
        rel = "" if rel == "." else rel + "/"
        for d in dirs:
            out[rel + d + "/"] = (0, 0)
        for f in files:
            if f.startswith("."):
                continue
            try:
                st = os.stat(os.path.join(here, f))
            except OSError:
                continue
            out[rel + f] = (st.st_size, st.st_mtime_ns)
    return out


def changed_files(old, new):
    """-> (names added, removed or changed, whether files or folders came or went)."""
    paths = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
    return {k.rstrip("/") for k in paths}, old.keys() != new.keys()


def make_server(port, notes_path=None, portfolio=None, host="127.0.0.1", hub=False, sync=True):
    """The server: 127.0.0.1 only unless `host` says otherwise (`--host 0.0.0.0`: every network interface, for a
    trusted LAN; no Host/Origin check or login then). Port 0 picks a free port.

    With `portfolio` (a folder; `--serve` passes PROJECTS), GET /api/portfolio lists its projects, POST /api/portfolio
    makes, renames and deletes (moves to .trash) projects, sections and pages, and
    /api/file reads and saves any file in it by its path relative to the folder.

    With `notes_path`, GET/POST /api/file read and save that one file. Nothing else is ever written.

    With `hub` (2.1.1, a portfolio that `setup_hub` made a hub; ValueError otherwise), /sync/* lets paired devices
    read and change the folder (a Bearer pairing code; no Host/Origin check, devices aren't browsers).
    """
    import base64
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    from urllib.parse import parse_qs, urlsplit

    # A pinned day (--today, or a TODAY set by the tests) stays; otherwise each request reads the clock, so a
    # server left running moves on at midnight.
    default_today = TODAY if TODAY_PINNED or TODAY != date.today() else None
    web = Path(__file__).resolve().parent / "web"
    statics = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
               "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
    folio = os.path.realpath(portfolio) if portfolio else None
    # Requests run on their own threads, so a stalled browser connection can't block the others. TODAY and
    # LOG_END are module globals set per request, and files are read-modify-written, so API work takes turns.
    lock = threading.RLock()
    if hub and folio is None:
        raise ValueError("a hub serves a Projects folder, not one notes file")
    hub = Hub(folio) if hub else None
    # 2.1.2: a paired folder keeps itself in step with the hub (sync=False: built but not started, for the tests)
    client = SyncClient(folio, lock) if folio is not None and hub is None and SyncClient.paired(folio) else None
    # 2.1.0: watch the notes on disk (every SCAN_SECONDS, and right after each POST) and tell the open pages
    changes, stop, watched = Changes(), threading.Event(), (folio is not None or notes_path is not None)
    seen = {"files": scan_files(folio) if folio is not None else scan_files(path=notes_path) if notes_path else {}}
    scan_lock = threading.Lock()

    def rescan():
        if not watched:
            return
        if hub is not None:
            try:
                hub.refresh("hub")                     # edits made on the hub (its page, by hand) go in its log
            except OSError:
                pass
        with scan_lock:
            try:
                now = scan_files(folio) if folio is not None else scan_files(path=notes_path)
            except OSError:                            # a folder that vanished mid-scan: try again next time
                return
            paths, tree = changed_files(seen["files"], now)
            seen["files"] = now
        if paths:
            changes.publish(paths, tree)
            if client is not None:
                client.kick()                          # 2.1.2: send it to the hub

    def watch():
        while not stop.wait(SCAN_SECONDS):
            try:
                rescan()
            except Exception:                          # a folder that vanished mid-scan: try again next time
                pass

    class Handler(BaseHTTPRequestHandler):
        timeout = 10                                   # seconds a connection may sit silent before it is dropped
        MAX_BODY = 32 * 1024 * 1024

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache")      # a new version of the page is picked up at once
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _trusted(self):
            """Only this page may use the API: blocks other sites (Origin) and DNS rebinding (Host).
            Not checked when `--host` opens the server to the network: any address may then reach it."""
            if host != "127.0.0.1":
                return True
            hosts = {f"localhost:{self.server.server_address[1]}", f"127.0.0.1:{self.server.server_address[1]}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") in hosts and (origin is None or origin in {"http://" + h for h in hosts}):
                return True
            self._json(403, {"error": "forbidden"})
            return False

        def do_GET(self):
            path = self.path.split("?")[0]
            if path.startswith("/sync/"):
                return self._sync_get(path)
            if path in statics:
                name, ctype = statics[path]
                self._send(200, (web / name).read_bytes(), ctype)
            elif path == "/api/portfolio":
                if not self._trusted():
                    return
                with lock:
                    self._json(200, {"name": None} if folio is None else portfolio_tree(folio))
            elif path == "/api/file":
                if not self._trusted():
                    return
                with lock:
                    self._file(parse_qs(urlsplit(self.path).query).get("path", [None])[0])
            elif path == "/api/events":
                if self._trusted():
                    self._events()
            elif path == "/api/settings":              # 2.1.4: settings that follow you across devices
                if self._trusted():
                    if folio is None:
                        return self._json(200, {"settings": None})
                    with lock:
                        self._json(200, {"settings": read_settings(folio)[0]})
            elif path == "/api/clashes":               # 2.1.3: the clashes kept aside on this device
                if self._trusted():
                    self._json(200, {"clashes": list_clashes(folio) if client is not None else []})
            elif path == "/api/sync":                  # 2.1.2: where sync stands ({state: "unpaired"} if not paired)
                if self._trusted():
                    self._json(200, changes.status or {"state": "hub" if hub is not None else "unpaired"})
            else:
                self._send(404, b"not found", "text/plain")

        def _sync_ok(self):
            """A /sync/ request: only on a hub, only with the pairing code."""
            if hub is None:
                self._send(404, b"not found", "text/plain")
                return False
            if not hub.allowed(self.headers.get("Authorization")):
                self._json(401, {"error": "wrong or missing pairing code"})
                return False
            return True

        def _sync_get(self, path):
            if not self._sync_ok():
                return
            q = parse_qs(urlsplit(self.path).query)
            try:
                if path == "/sync/state":
                    return self._json(200, hub.state())
                if path == "/sync/changes":
                    since = int(q.get("since", ["0"])[0])
                    wait = min(max(float(q.get("wait", ["0"])[0]), 0), 30)
                    return self._json(200, hub.changes(since, wait))
                if path.startswith("/sync/blob/"):
                    data = hub.blob(path[len("/sync/blob/"):])
                    if data is None:
                        return self._json(404, {"error": "no such version"})
                    return self._send(200, data, "application/octet-stream")
            except ValueError:
                return self._json(400, {"error": "bad request"})
            except OSError:
                return
            self._send(404, b"not found", "text/plain")

        def _sync_post(self):
            if not self._sync_ok():
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 <= length <= self.MAX_BODY:
                    raise ValueError
                req = json.loads(self.rfile.read(length))
                device = str(self.headers.get("X-Kafeen-Device") or "a device")[:60]
                op, rel = self.path[len("/sync/"):], req.get("path")
                with lock:
                    if op == "put":
                        out = hub.put(rel, req.get("base"), base64.b64decode(req.get("data", ""), validate=True), device)
                        if "data" in out:
                            out["data"] = base64.b64encode(out["data"]).decode()
                    elif op == "delete":
                        out = hub.delete(rel, req.get("base"), device)
                    elif op == "mkdir":
                        out = hub.mkdir(rel, device)
                    elif op == "rmdir":
                        out = hub.rmdir(rel, device)
                    else:
                        return self._send(404, b"not found", "text/plain")
                out["seq"] = hub.seq
                self._json(200, out)
            except (ValueError, TypeError) as e:
                self._json(400, {"error": f"bad request: {e}"})
            except OSError:
                pass
            finally:
                rescan()                                # the hub's own pages see a device's change at once

        def do_POST(self):
            if self.path.startswith("/sync/"):
                return self._sync_post()
            if self.path not in ("/api/parse", "/api/edit", "/api/file", "/api/portfolio", "/api/archive", "/api/clashes", "/api/settings"):
                return self._send(404, b"not found", "text/plain")
            if not self._trusted():
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "send JSON"})
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 <= length <= self.MAX_BODY:
                    raise ValueError
            except ValueError:
                return self._json(400, {"error": "bad request: a valid Content-Length is needed"})
            try:
                raw = self.rfile.read(length)           # read before taking the lock: a slow client holds up only itself
            except OSError:
                return                                  # the connection timed out or went away
            if len(raw) < length:
                return self._json(400, {"error": "bad request: the body ended early"})
            try:
                with lock:
                    self._post(raw)
            except OSError:
                pass                                    # the browser left before the answer was sent
            except Exception as e:                      # one bad request must never take the server down
                self._json(500, {"error": f"server error: {type(e).__name__}: {e}"})
            finally:
                rescan()                                # tell the other open pages at once, not at the next scan

        def _post(self, raw):
            global TODAY, LOG_END
            LOG_END = None
            try:
                req = json.loads(raw)
                if self.path == "/api/file":
                    return self._save(req)
                if self.path == "/api/portfolio":
                    return self._portfolio(req)
                if self.path == "/api/settings":           # 2.1.4: {set: {setting: value}}
                    if folio is None:
                        return self._json(409, {"error": "settings are kept in a Projects folder"})
                    try:
                        return self._json(200, {"settings": write_settings(folio, req.get("set"))})
                    except (ValueError, FileConflict) as e:
                        return self._json(409, {"error": str(e)})
                if self.path == "/api/clashes":            # 2.1.3: {id, choices}
                    if client is None:
                        return self._json(409, {"error": "this folder isn't paired with a hub"})
                    try:
                        out = resolve_clash(folio, req.get("id"), req.get("choices"))
                    except ValueError as e:
                        return self._json(409, {"error": str(e)})
                    client.recount()
                    return self._json(200, out)
                TODAY = default_today or date.today()
                if req.get("today"):
                    set_today(req["today"])
                if req.get("year") is not None:              # an archive page: its dates fall in its year
                    if type(req["year"]) is not int or not 1900 <= req["year"] <= 2999:
                        raise ValueError("year must be a year, like 2026")
                    TODAY = archive_today(req["year"])
                    LOG_END = date(req["year"], 12, 31)
                if self.path == "/api/archive":
                    return self._archive(req, period_from(req.get("period")), planner_from(req.get("planner")))
                text = req.get("text", "")
                period = period_from(req.get("period"))
                monday = planner_from(req.get("planner"))
                name = req.get("name") if isinstance(req.get("name"), str) else None
                if self.path == "/api/parse":
                    if req.get("all"):
                        if folio is None:
                            return self._json(409, {"error": "no projects folder is being served (planner.py --serve)"})
                        return self._json(200, portfolio_data(folio, period, monday, _hide(req)))
                    return self._json(200, page_data(text, name, period, monday, bool(req.get("habits")), own_habits(folio, name, req)))
                if "path" in req:
                    return self._edit_file(req, period, monday)
                text = apply_edit(text, req)
                self._json(200, {"text": text, "data": page_data(text, name, period, monday, bool(req.get("habits")), own_habits(folio, name, req))})
            except EditError as e:
                self._json(409, {"error": str(e)})
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                self._json(400, {"error": f"bad request: {e}"})

        def _edit_file(self, req, period, monday):
            """/api/edit with `path` and `version`: the edit is made on the file itself. Refused (409
            conflict) if the file isn't at `version` any more. -> {text, version, data}."""
            p = self._target(req["path"])
            if p is None:
                return self._not_open(req["path"])
            text, current = read_notes(p)
            if current != req.get("version"):
                return self._json(409, {"error": "the file changed on disk since it was loaded", "conflict": True, "version": current})
            name = project_name(req["path"]) if folio else None
            hab = folio and portfolio_kind(req["path"]) == "habits"
            before, text = text, apply_edit(text, req)
            try:
                version = write_notes(p, text, current)
            except FileConflict:
                return self._json(409, {"error": "the file changed on disk since it was loaded", "conflict": True,
                                        "version": read_notes(p)[1]})
            data = (portfolio_data(folio, period, monday, _hide(req)) if folio and req.get("all")
                    else page_data(text, name, period, monday, hab, None if hab else own_habits(folio, name, req)))
            self._json(200, {"text": text, "before": before, "version": version, "data": data})

        def _archive(self, req, period, monday):
            """POST /api/archive {path, version, year, line + title | done (+ project_line), all}: move a task and its
            subtasks (or every finished task) from a project's .kf file into its archive/YEAR.kf. The archive is
            written first, so a crash leaves a copy rather than losing anything. -> {text, version, data, archive,
            moved, tree, undo: [{path, before, version}] (the source, then the archive)}."""
            if folio is None:
                return self._json(409, {"error": "the archive needs the projects folder (planner.py --serve)"})
            path, year = req.get("path"), req.get("archive_year")
            if portfolio_kind(path) in (None, "project", "section", "archive") or not path.endswith(".kf"):
                return self._json(409, {"error": "tasks can be archived from a project's .kf pages"})
            if type(year) is not int or not 1900 <= year <= 2999:
                return self._json(400, {"error": "bad request: archive_year must be a year, like 2026"})
            src = self._target(path)
            if src is None:
                return self._not_open(path)
            text, current = read_notes(src)
            if current != req.get("version"):
                return self._json(409, {"error": "the file changed on disk since it was loaded", "conflict": True, "version": current})
            if req.get("habit_log"):
                if portfolio_kind(path) != "habits":
                    return self._json(409, {"error": "habit logs are archived from a project's Habits"})
                rest, moved = take_habit_log(text, year)
            elif req.get("done"):
                rest, moved = take_done(text, req.get("project_line"))
            else:
                rest, block, group = take_task(text, req["line"], req.get("title"))
                moved = [(group, block)]
            arel = f"{project_name(path)}/{ARCHIVE_DIR}/{year}.kf"
            apath = portfolio_path(folio, arel)
            atext, aver = read_notes(apath)
            new = atext
            for group, block in moved:
                new = put_in_archive(new, group, block)
            os.makedirs(os.path.dirname(apath), exist_ok=True)
            aver2 = write_notes(apath, new, aver)          # the archive first: a crash leaves a copy, never a loss
            try:
                version = write_notes(src, rest, current)
            except FileConflict:
                write_notes(apath, atext, aver2)           # the source changed meanwhile: take the copy back out
                return self._json(409, {"error": "the file changed on disk since it was loaded", "conflict": True,
                                        "version": read_notes(src)[1]})
            name = project_name(path)
            data = (portfolio_data(folio, period, monday, _hide(req)) if req.get("all")
                    else page_data(rest, name, period, monday, portfolio_kind(path) == "habits",
                                   None if portfolio_kind(path) == "habits" else own_habits(folio, name, req)))
            self._json(200, {"text": rest, "version": version, "data": data, "archive": arel,
                             "moved": sum(1 for _, b in moved for r in b if RE_TASK.match(r.strip()) and not r.strip().startswith("--")),
                             "tree": portfolio_tree(folio),
                             "undo": [{"path": path, "before": text, "version": version},
                                      {"path": arel, "before": atext, "version": aver2}]})

        def _portfolio(self, req):
            """POST /api/portfolio {op, ...}: project {name}; section {project, name}; page {project, name,
            section?}; rename {path, name}; trash {path}. -> {path, tree}."""
            op = req.get("op")
            if folio is None:
                return self._json(409, {"error": "no projects folder is being served (planner.py --serve)"})
            try:
                if op == "project":
                    path = new_project(folio, req.get("name"))
                elif op == "section":
                    path = new_section(folio, req.get("project"), req.get("name"))
                elif op == "page":
                    path = new_page(folio, req.get("project"), req.get("name"), req.get("section"))
                elif op == "rename":
                    path = rename_item(folio, req.get("path"), req.get("name"))
                elif op == "trash":
                    path = trash_item(folio, req.get("path"))
                else:
                    return self._json(400, {"error": f"bad request: unknown op {op!r} (project, section, page, rename, trash)"})
            except PortfolioError as e:
                return self._json(409, {"error": str(e)})
            except OSError as e:
                return self._json(500, {"error": f"can't do that: {e.strerror or e}"})
            self._json(200, {"path": path, "tree": portfolio_tree(folio)})

        def _target(self, path):
            """The file a request means: the command-line file, or in a portfolio the file at `path`
            (relative to it) if its folder exists; else None."""
            if folio is not None:
                if portfolio_kind(path) in (None, "project", "section"):
                    return None
                try:
                    p = portfolio_path(folio, path)
                except PortfolioError:
                    return None
                folder = os.path.dirname(p)
                if portfolio_kind(path) == "archive":     # archive/ is made on the first save
                    folder = os.path.dirname(folder)
                return p if os.path.isdir(folder) else None
            return notes_path if notes_path is not None and path in (None, notes_path) else None

        def _not_open(self, path):
            """409 notOpen: `path` isn't a file this server can read or write."""
            self._json(409, {"error": f"{os.path.basename(str(path))} isn't open", "notOpen": True})

        def _file(self, path=None):
            """{name, path, text, version} for the command-line file or a
            portfolio file (text "" and version null if not made yet); {name: null} without a path
            and without a command-line file."""
            if path is None and notes_path is None:
                return self._json(200, {"name": None})
            p = self._target(path)
            if p is None:
                return self._not_open(path)
            try:
                text, version = read_notes(p)
            except (OSError, UnicodeDecodeError) as e:
                return self._json(500, {"error": f"can't read {p}: {e}"})
            self._json(200, {"name": os.path.basename(p), "path": path if folio else p, "text": text, "version": version})

        def _events(self):
            """2.1.0: a stream of Server-Sent Events: `changed` {paths, tree} whenever notes change on disk (paths as
            the page names them: portfolio paths, or the command-line file's path), and a comment every
            15 s so the connection stays open. The page's EventSource reconnects by itself."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            n = changes.seq
            try:
                self.wfile.write(b"retry: 2000\n\n")
                if changes.status:                      # 2.1.2: where sync stands, at once
                    self.wfile.write(f"event: sync\ndata: {json.dumps(changes.status)}\n\n".encode())
                self.wfile.flush()
                while not stop.is_set():
                    n2, entries = changes.since(n, 15)
                    if stop.is_set():
                        break
                    if entries:
                        paths = sorted({p for e in entries if e[1] is not None for p in e[1]})
                        if paths:
                            msg = json.dumps({"paths": paths, "tree": any(e[2] for e in entries)})
                            self.wfile.write(f"event: changed\ndata: {msg}\n\n".encode())
                        if any(e[1] is None for e in entries):   # 2.1.2: the sync status changed
                            self.wfile.write(f"event: sync\ndata: {json.dumps(changes.status)}\n\n".encode())
                    else:
                        self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
                    n = n2
            except OSError:
                pass                                    # the page went away

        def _save(self, req):
            p = self._target(req.get("path"))
            if p is None:
                return self._not_open(req.get("path"))
            if not isinstance(req.get("text"), str):
                return self._json(400, {"error": "bad request: text must be a string"})
            try:
                if folio is not None:
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                version = write_notes(p, req["text"], req.get("version"), bool(req.get("force")))
            except FileConflict as e:
                disk, current = read_notes(p)
                base = req.get("base")
                if isinstance(base, str) and current is not None:   # 2.1.0: changed on disk meanwhile: merge if the
                    crlf = "\r\n" in disk and disk.count("\r\n") == disk.count("\n")   # changes don't clash
                    merged, clashes = merge3(base, req["text"], disk.replace("\r\n", "\n") if crlf else disk)
                    if not clashes:
                        try:
                            version = write_notes(p, merged, current)
                        except (FileConflict, OSError) as e2:
                            return self._json(409, {"error": str(e2), "conflict": True, "version": read_notes(p)[1]})
                        return self._json(200, {"version": version, "text": merged, "merged": True})
                return self._json(409, {"error": str(e), "conflict": True, "version": current})
            except OSError as e:
                return self._json(500, {"error": f"can't save {p}: {e}"})
            self._json(200, {"version": version})

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = True                          # a stuck request never keeps the program from exiting
        request_queue_size = 128                       # the default 5 resets connections when a browser opens a burst

        def server_close(self):
            stop.set()
            if client is not None:
                client.close()
            changes.close()                            # wakes the event streams, which then end
            super().server_close()

    server = Server((host, port), Handler)
    if client is not None:
        client.on_change, client.on_status = rescan, changes.publish_status
        changes.status = dict(client.status)
    elif hub is not None:
        changes.status = {"state": "hub"}
    server.changes, server.rescan, server.hub, server.sync = changes, rescan, hub, client
    if watched:
        threading.Thread(target=watch, daemon=True).start()
    if hub is not None and sync:                       # 2.1.4: a backup a day, old versions pruned
        def backups():
            while True:
                try:
                    if backup_due(folio):
                        with lock:
                            hub_backup(folio)
                            prune_blobs(hub)
                except OSError:
                    pass
                if stop.wait(3600):
                    break
        threading.Thread(target=backups, daemon=True).start()
    if client is not None and sync:
        client.start()
    return server


def serve(port, notes_path=None, portfolio=None, host="127.0.0.1", hub=False, browser=True):
    import threading
    import webbrowser

    try:
        server = make_server(port, notes_path, portfolio=portfolio, host=host, hub=hub)
    except ValueError as e:
        sys.exit(f"planner.py: {e}")
    if hub:
        print(f"Sync hub: paired devices keep {portfolio} in step (log and versions in {os.path.join(portfolio, SYNC_DIR)})")
    local = host == "127.0.0.1"
    url = f"http://localhost:{port}"
    print(f"Planner running at {url if local else f'http://{host}:{port}  (anyone on the network can use it and change the files)'}  (Ctrl-C to stop)")
    if portfolio:
        print(f"Projects in {portfolio}")
    if notes_path:
        print(f"Editing {notes_path}" + ("" if os.path.exists(notes_path) else " (new file, created on first Save)"))
    if local and browser:                              # a server on the network is usually headless
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


VIEWS = {"projects": view_projects, "timeline": view_timeline,
         "people": view_people, "upcoming": view_upcoming, "week": view_week}


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
    global TODAY_PINNED
    args, path, chosen = list(argv[1:]), None, []
    today = take_option(args, "--today")
    if today is not None:
        try:
            set_today(today)
            TODAY_PINNED = True
        except ValueError:
            sys.exit(f"planner.py: bad --today value {today!r} (use Oct12 or 2026-10-12)")
    if "--import" in args:
        split = "--split" in args
        if split:
            args.remove("--split")
        args.remove("--import")
        if len(args) not in (1, 2) or not os.path.isfile(args[0]):
            sys.exit("planner.py: use --import notes.txt [FOLDER] [--split]")
        folder = args[1] if len(args) == 2 else PROJECTS
        if not os.path.isdir(folder) and not os.path.isdir(os.path.dirname(os.path.abspath(folder))):
            sys.exit(f"planner.py: can't make the portfolio {folder!r}: its parent folder doesn't exist")
        try:
            with open(args[0], encoding="utf-8", newline="") as f:
                text = f.read()
            os.makedirs(folder, exist_ok=True)
            made = import_notes(text, folder, os.path.splitext(os.path.basename(args[0]))[0], split)
        except (OSError, UnicodeDecodeError, PortfolioError) as e:
            sys.exit(f"planner.py: can't import {args[0]!r}: {e}")
        print(f"Imported into {folder}: " + ", ".join(made))
        return
    if "--setup-hub" in args:                                  # 2.1.1: this machine's Projects folder becomes the hub
        args.remove("--setup-hub")
        new = "--new-code" in args
        if new:
            args.remove("--new-code")
        folder = args[0] if len(args) == 1 else PROJECTS if not args else None
        if folder is None:
            sys.exit("planner.py: use --setup-hub [FOLDER] [--new-code]")
        try:
            os.makedirs(folder, exist_ok=True)
            code = setup_hub(folder, new)
        except (OSError, ValueError) as e:
            sys.exit(f"planner.py: {e}")
        print(f"""This computer's projects ({os.path.realpath(folder)}) are now the sync hub.

Pairing code (keep it secret; you type it once on each of your devices):

    {code}

Start the hub (and keep it running):
    python3 planner.py --serve --hub --host 0.0.0.0

Then, on each computer:
    python3 planner.py --pair http://THIS-COMPUTER:8765 {code}
(THIS-COMPUTER: its Tailscale name, like kafeen-hub.)""")
        return
    if "--pair" in args:                                       # 2.1.2: this computer's Projects folder follows the hub
        args.remove("--pair")
        name = take_option(args, "--name")
        if len(args) not in (2, 3):
            sys.exit("planner.py: use --pair HUB-ADDRESS PAIRING-CODE [FOLDER] [--name NAME]")
        folder = args[2] if len(args) == 3 else PROJECTS
        try:
            os.makedirs(folder, exist_ok=True)
            state = pair(folder, args[0], args[1], name)
            client = SyncClient(folder)
            print(f"Paired with the hub at {client.hub} as {client.name!r} (the hub has {len(state['files'])} files).")
            n = client.round()
        except (OSError, ValueError) as e:
            sys.exit(f"planner.py: {e}")
        print(f"First sync: {n['pulled']} from the hub, {n['pushed']} sent, {n['merged']} merged"
              + (f", {n['conflicts']} clashes (kept in {os.path.join(folder, SYNC_DIR, 'conflicts')})" if n["conflicts"] else "")
              + ".\nFrom now on, python3 planner.py --serve keeps this folder in step with the hub, live.")
        return
    if "--unpair" in args:
        args.remove("--unpair")
        folder = args[0] if len(args) == 1 else PROJECTS
        conf = os.path.join(folder, SYNC_DIR, "device.json")
        if not os.path.exists(conf):
            sys.exit("planner.py: this folder isn't paired with a hub")
        os.remove(conf)
        print("Unpaired: the files stay as they are and no longer sync. Pair again with --pair.")
        return
    if "--autostart" in args:                                  # 2.1.4: start KAFEEN (or the hub) at login
        args.remove("--autostart")
        hub = "--hub" in args
        if hub:
            args.remove("--hub")
        port = take_option(args, "--port") or "8765"
        if len(args) != 1 or args[0] not in ("on", "off") or not port.isdigit():
            sys.exit("planner.py: use --autostart on|off [--hub] [--port N]")
        if hub and args[0] == "on" and not os.path.exists(os.path.join(PROJECTS, SYNC_DIR, "hub.json")):
            sys.exit("planner.py: make this computer the hub first: python3 planner.py --setup-hub")
        try:
            print("\n".join(autostart(args[0] == "on", hub, int(port))))
        except (OSError, ValueError) as e:
            sys.exit(f"planner.py: {e}")
        return
    if "--serve" in args:
        args.remove("--serve")
        hub = "--hub" in args
        if hub:
            args.remove("--hub")
        browser = "--no-browser" not in args
        if not browser:
            args.remove("--no-browser")
        port = take_option(args, "--port") or "8765"
        host = take_option(args, "--host") or "127.0.0.1"
        if not port.isdigit() or not 0 < int(port) < 65536:
            sys.exit(f"planner.py: bad --port value {port!r}")
        if len(args) > 1 or any(a.lower() in VIEWS for a in args):
            sys.exit("planner.py: --serve takes at most one notes file (and no view names)")
        if not args:                                           # the Projects folder next to planner.py
            try:
                os.makedirs(PROJECTS, exist_ok=True)
            except OSError as e:
                sys.exit(f"planner.py: can't make the folder {PROJECTS!r}: {e.strerror or e}")
            return serve(int(port), portfolio=PROJECTS, host=host, hub=hub, browser=browser)
        if hub:
            sys.exit("planner.py: --hub serves the Projects folder, not one notes file")
        notes = os.path.realpath(args[0])                      # follow a symlink to the real file
        if os.path.isdir(notes):
            sys.exit(f"planner.py: --serve takes no folder: your projects live in {PROJECTS}")
        if not os.path.isdir(os.path.dirname(notes)):
            sys.exit(f"planner.py: can't edit {args[0]!r}: not a file in an existing folder")
        try:
            read_notes(notes)
        except (OSError, UnicodeDecodeError) as e:
            sys.exit(f"planner.py: can't read {args[0]!r}: {e}")
        return serve(int(port), notes, host=host, browser=browser)
    for a in args:
        if a.lower() in VIEWS:
            chosen.append(a.lower())
        elif not os.path.isfile(a) and not os.path.isdir(a):
            sys.exit(f"planner.py: {a!r} is not a file, a portfolio folder or a view ({' | '.join(VIEWS)})")
        elif path is not None:
            sys.exit(f"planner.py: only one notes file at a time (got {path!r} and {a!r})")
        else:
            path = a

    habits = None
    if path and os.path.isdir(path):                           # a portfolio: every project's backlog (and habits)
        try:
            projects, habits, _, _ = portfolio_projects(path)
        except (OSError, UnicodeDecodeError) as e:
            sys.exit(f"planner.py: can't read the portfolio {path!r}: {e}")
        for p in projects + habits:                            # a sub-group reads "HDC · Stream"
            if p.name != p.folder:
                p.name = f"{p.folder} · {p.name}"
        text = None
    elif path:
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

    if text is not None:
        projects = parse(text)
    if not projects:
        print("No projects or tasks found.")
        return
    for name in chosen or list(VIEWS):
        print("\n".join(view_week(projects, None, habits) if name == "week" else view_upcoming(projects, habits)
                         if name == "upcoming" else VIEWS[name](projects)))
        print()


if __name__ == "__main__":
    main(sys.argv)
