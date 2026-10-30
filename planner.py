#!/usr/bin/env python3
"""
planner.py - turn plain-text planning notes into four views:
projects, timeline, people, and what's coming up.
Standard library only (Python 3.8+).

USAGE
  python planner.py                    paste your notes, then press
                                       Ctrl-D (Mac/Linux) or Ctrl-Z then Enter (Windows)
  python planner.py notes.txt          read notes from a file instead
  python planner.py notes.txt people   show one view only:
                                       projects | timeline | people | upcoming
  --today Oct10                        pretend today is another date (for testing)
  --serve [--port 8765]                open the web page (paste/open/edit notes, dark mode;
                                       click a task's box to change its status)

NOTE FORMAT (quick reference)
  Fall Planning  Sep01--Dec19   heading: left edge, no marker, optional dates
  @HDC                          project: runs until the next @ or heading
  - task  ~- task  !- task      open / in progress / done
  <Tab>                         one level deeper = subtask
  -- text                       note on the task above (never a task)
  (KA)  (KA, RT)                assignees
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
        self.assignees, self.reminders, self.notes, self.children = [], [], [], []
        self.start = self.end = self.loose = None
        self.parent = self.project = None
        self.title = self._parse(text)

    def _parse(self, text):
        for m in RE_ASSIGN.finditer(text):
            self.assignees += [a.strip() for a in m.group(1).split(",")]
        text = RE_ASSIGN.sub("", text)
        for m in RE_REMIND.finditer(text):
            self.reminders.append((m.group(1), next_reminder(m.group(1))))
        text = RE_REMIND.sub("", text)

        m = RE_RANGE.search(text)
        if m:
            s = resolve(MONTHS[m.group(1)], int(m.group(2)))
            em = MONTHS[m.group(3) or m.group(1)]
            e = s and resolve_after(em, int(m.group(4)), s)
            if e:
                self.start, self.end = s, e
                text = text[:m.start()] + text[m.end():]
        if self.end is None:
            m = RE_LOOSE.search(text)
            span = m and loose_span(m.group(1))
            if span:
                self.start, self.end = span
                self.loose = m.group(1)
                text = text[:m.start()] + text[m.end():]
        if self.end is None:
            m = RE_DATE.search(text)
            d = m and resolve(MONTHS[m.group(1)], int(m.group(2)))
            if d:
                self.start = self.end = d
                text = text[:m.start()] + text[m.end():]
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


class Project:
    def __init__(self, name, section):
        self.name, self.section = name, section
        self.tasks, self.notes = [], []

    def all_tasks(self):
        for t in self.tasks:
            yield from t.walk()


def parse(text):
    projects, section, project, stack = [], None, None, []

    def ensure_project():
        nonlocal project
        if project is None:
            project = Project("(no project)", section)
            projects.append(project)
        return project

    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        ws = raw[:len(raw) - len(raw.lstrip())]
        level = ws.count("\t") + ws.count(" ") // 4
        line = raw.strip()

        if line.startswith("@"):
            project = Project(line[1:].strip(), section)
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
        out.append(f"\n@{p.name}   {done}/{len(tasks)} done")
        for n in p.notes:
            out.append(f"    -- {n}")

        def render(t, depth):
            line = "    " * depth + f"{BOX[t.status]} {t.label()}"
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


def timeline_rows(projects):
    """Open tasks -> (rows sorted by date, unscheduled). Row = (start, end, project, task, how)."""
    rows, unscheduled = [], []
    for p in projects:
        for t in p.all_tasks():
            if t.status == "done":
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
        out.append(f"\n{name}   {len(items)} task(s)")
        for p, t in items:
            sp = t.span()
            when = f"   {fspan(sp[0], sp[1])}" if sp else ""
            flag = "   OVERDUE" if t.overdue() else ""
            out.append(f"    {BOX[t.status]} @{p.name}  {t.title}{when}{flag}")
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
    section("Due soon", [f"    {fd(d):<9} @{p.name}  {t.label()}" for d, p, t in sorted(due, key=lambda r: r[0])])
    section("Reminders", [f"    {fd(d):<9} @{p.name}  {t.label()}   (*{spec})"
                          for d, spec, p, t in sorted(reminders, key=lambda r: r[0])])
    section("In progress", [f"    [~] @{p.name}  {t.label()}" for p, t in doing])
    return out


# ---------- structured data (for the web page) ----------

def iso(d):
    return d.isoformat() if d else None


def task_data(t):
    sp = t.span()
    return {
        "title": t.title, "status": t.status, "line": t.line, "assignees": t.assignees, "notes": t.notes,
        "when": fspan(t.start, t.end, t.loose) if t.end else None,
        "span": {"start": iso(sp[0]), "end": iso(sp[1]), "how": sp[2],
                 "label": fspan(sp[0], sp[1], t.loose if sp[2] == "own" else None)} if sp else None,
        "overdue": t.overdue(),
        "reminders": [{"spec": spec, "next": iso(d)} for spec, d in t.reminders],
        "children": [task_data(c) for c in t.children],
    }


def flat(p, t):
    """A task with its project, for the flat lists (timeline, people, upcoming)."""
    d = task_data(t)
    d["project"] = p.name
    d["children"] = []
    return d


def to_data(projects):
    """Everything the four views show, as plain dicts and lists (JSON-ready)."""
    sections, seen = [], {}
    for p in projects:
        key = id(p.section)
        if key not in seen:
            sec = p.section
            seen[key] = {"title": sec.title if sec else None,
                         "when": fspan(sec.start, sec.end, sec.loose) if sec and sec.end else None,
                         "projects": []}
            sections.append(seen[key])
        tasks = list(p.all_tasks())
        seen[key]["projects"].append({
            "name": p.name, "notes": p.notes,
            "done": sum(t.status == "done" for t in tasks), "total": len(tasks),
            "tasks": [task_data(t) for t in p.tasks]})

    months = timeline_months()
    first, last = date(*months[0], 1), month_end(*months[-1])
    rows, unscheduled = timeline_rows(projects)
    horizon, overdue, due, doing, reminders = upcoming_groups(projects)
    return {
        "today": iso(TODAY), "today_label": fd(TODAY),
        "projects": sections,
        "timeline": {
            "months": [{"label": MONTH_NAMES[m - 1], "year": y} for y, m in months],
            "rows": [dict(flat(p, t), bar=[s <= month_end(y, m) and e >= date(y, m, 1) for y, m in months],
                          before=e < first, after=e > last) for s, e, p, t, _ in rows],
            "unscheduled": [flat(p, t) for p, t in unscheduled]},
        "people": [{"name": n, "tasks": [flat(p, t) for p, t in items]} for n, items in people_groups(projects)],
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


def set_status(text, line, status, title=None):
    """Return `text` with the task on `line` (1-based) set to `status`.

    Only the status mark before the task's dash changes. Every other character
    of the text, including that line's indentation, wording and line ending,
    stays exactly as it was. If `title` is given it must match the task's parsed
    title, so an edit made from an out-of-date view is refused, not misapplied.
    """
    if status not in STATUS_MARK:
        raise EditError(f"unknown status {status!r} (use open, doing or done)")
    lines = text.splitlines(keepends=True)      # same split points as parse()
    if type(line) is not int or not 1 <= line <= len(lines):
        raise EditError(f"line {line!r} is not in the text")
    task = next((t for p in parse(text) for t in p.all_tasks() if t.line == line), None)
    if task is None or (title is not None and task.title != title):
        raise EditError(f"line {line} is no longer that task (the text has changed)")
    raw = lines[line - 1]
    ws = raw[:len(raw) - len(raw.lstrip())]
    body = raw[len(ws):]
    if body[0] in "!~":
        body = body[1:]
    lines[line - 1] = ws + STATUS_MARK[status] + body
    return "".join(lines)


# ---------- web page ----------

def set_today(val):
    """--today value: Oct12 or 2026-10-12."""
    global TODAY
    m = re.fullmatch("(" + MON + r")(\d{1,2})", val)
    TODAY = date(date.today().year, MONTHS[m.group(1)], int(m.group(2))) if m else date.fromisoformat(val)


def make_server(port):
    """The local server (127.0.0.1 only). Port 0 picks a free port."""
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pathlib import Path

    default_today = TODAY
    page = Path(__file__).resolve().parent / "web" / "index.html"

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/index.html"):
                self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path not in ("/api/parse", "/api/edit"):
                return self._send(404, b"not found", "text/plain")
            global TODAY
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                TODAY = default_today
                if req.get("today"):
                    set_today(req["today"])
                text = req.get("text", "")
                if self.path == "/api/parse":
                    return self._json(200, to_data(parse(text)))
                text = set_status(text, req["line"], req["status"], req.get("title"))
                self._json(200, {"text": text, "data": to_data(parse(text))})
            except EditError as e:
                self._json(409, {"error": str(e)})
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                self._json(400, {"error": f"bad request: {e}"})

        def log_message(self, *args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def serve(port):
    import threading
    import webbrowser

    server = make_server(port)
    url = f"http://localhost:{port}"
    print(f"Planner running at {url}  (Ctrl-C to stop)")
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
        return serve(int(port))
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
