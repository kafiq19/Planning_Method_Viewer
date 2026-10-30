"""
Tests for planner.py. Standard library only:  python -m unittest -v

Every test pins TODAY (default Oct 12 2026) because dates are written without years.
"""
import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date

import planner

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "example.txt")


def read_example():
    with open(EXAMPLE, encoding="utf-8") as f:
        return f.read()


class Base(unittest.TestCase):
    today = "2026-10-12"

    def setUp(self):
        self._saved = planner.TODAY
        planner.set_today(self.today)

    def tearDown(self):
        planner.TODAY = self._saved

    def task(self, text, status="open"):
        return planner.Task(text, status)

    def find(self, projects, title):
        for p in projects:
            for t in p.all_tasks():
                if t.title == title:
                    return t
        self.fail(f"no task titled {title!r}")


# ---------- line classification ----------

class TestParse(Base):
    def test_project_section_and_tasks(self):
        ps = planner.parse("Fall  Sep01--Dec19\n@A\n- one\n@B\n- two\n")
        self.assertEqual([p.name for p in ps], ["A", "B"])
        self.assertEqual(ps[0].section.title, "Fall")
        self.assertEqual(ps[0].section.start, date(2026, 9, 1))
        self.assertIs(ps[0].section, ps[1].section)

    def test_status_markers(self):
        ps = planner.parse("@A\n- open\n~- doing\n!- done\n")
        self.assertEqual([t.status for t in ps[0].tasks], ["open", "doing", "done"])

    def test_no_project(self):
        ps = planner.parse("- loose task\n")
        self.assertEqual(ps[0].name, "(no project)")

    def test_nesting_by_tabs_and_spaces(self):
        ps = planner.parse("@A\n- a\n\t- b\n        - c\n\t- d\n- e\n")
        a, e = ps[0].tasks
        self.assertEqual([c.title for c in a.children], ["b", "d"])
        self.assertEqual(a.children[0].children[0].title, "c")
        self.assertIs(a.children[0].children[0].parent, a.children[0])
        self.assertEqual(e.children, [])

    def test_notes(self):
        ps = planner.parse("@A\n-- project note\n- a\n\t-- dash note\n\tplain note\n")
        self.assertEqual(ps[0].notes, ["project note"])
        self.assertEqual(ps[0].tasks[0].notes, ["dash note", "plain note"])

    def test_note_is_not_a_task(self):
        ps = planner.parse("@A\n- a\n-- - not a task\n")
        self.assertEqual(len(list(ps[0].all_tasks())), 1)

    def test_left_edge_text_is_heading(self):
        ps = planner.parse("@A\n- a\nforgot the dash\n- b\n")
        self.assertEqual(len(ps), 2)
        self.assertEqual(ps[1].name, "(no project)")
        self.assertEqual(ps[1].section.title, "forgot the dash")

    def test_blank_lines_ignored(self):
        ps = planner.parse("\n@A\n   \n- a\n\n\t- b\n")
        self.assertEqual(ps[0].tasks[0].children[0].title, "b")

    def test_line_numbers(self):
        text = "Fall\n\n@A\n- a\n\t-- note\n\t- b\r\n~- c\n"
        ps = planner.parse(text)
        a, c = ps[0].tasks
        self.assertEqual((ps[0].section.line, a.line, a.children[0].line, c.line), (1, 4, 6, 7))

    def test_line_numbers_point_at_task_lines(self):
        lines = read_example().splitlines()
        for p in planner.parse(read_example()):
            for t in p.all_tasks():
                self.assertRegex(lines[t.line - 1].strip(), r"^[!~]?-(?!-)")
                self.assertIn(t.title.split()[0], lines[t.line - 1])

    def test_parse_does_not_modify_input(self):
        text = read_example()
        copy = str(text)
        planner.parse(text)
        self.assertEqual(text, copy)


# ---------- inline tokens ----------

class TestTokens(Base):
    def test_assignees(self):
        t = self.task("meet (KA) and (RT, JS) later")
        self.assertEqual(t.assignees, ["KA", "RT", "JS"])
        self.assertEqual(t.title, "meet and later")

    def test_lowercase_parens_stay_in_title(self):
        t = self.task("call (maybe)")
        self.assertEqual(t.assignees, [])
        self.assertEqual(t.title, "call (maybe)")

    def test_single_date(self):
        t = self.task("ship Oct24")
        self.assertEqual((t.start, t.end), (date(2026, 10, 24),) * 2)
        self.assertEqual(t.title, "ship")

    def test_range_same_month(self):
        t = self.task("x Oct23--26")
        self.assertEqual((t.start, t.end), (date(2026, 10, 23), date(2026, 10, 26)))

    def test_range_cross_month(self):
        t = self.task("x Oct23--Nov03")
        self.assertEqual((t.start, t.end), (date(2026, 10, 23), date(2026, 11, 3)))

    def test_range_cross_year(self):
        t = self.task("x Dec15--Jan10")
        self.assertEqual((t.start, t.end), (date(2026, 12, 15), date(2027, 1, 10)))

    def test_loose_quarter_month_week(self):
        q, m, w = self.task("x ~Q1"), self.task("x ~Nov"), self.task("x ~wk43")
        self.assertEqual((q.start, q.end, q.loose), (date(2027, 1, 1), date(2027, 3, 31), "Q1"))
        self.assertEqual((m.start, m.end), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual((w.start, w.end), (date(2026, 10, 19), date(2026, 10, 25)))
        self.assertEqual(q.title, "x")

    def test_only_first_date_counts(self):
        t = self.task("call Oct20 Oct22")
        self.assertEqual(t.end, date(2026, 10, 20))
        self.assertEqual(t.title, "call Oct22")

    def test_range_beats_loose_beats_date(self):
        t = self.task("x Oct30 ~Q1 Oct23--26")
        self.assertEqual((t.start, t.end), (date(2026, 10, 23), date(2026, 10, 26)))
        self.assertEqual(t.title, "x Oct30 ~Q1")
        t = self.task("x Oct30 ~Q1")
        self.assertEqual(t.loose, "Q1")
        self.assertEqual(t.title, "x Oct30")

    def test_invalid_date_stays_in_title(self):
        t = self.task("x Feb30")
        self.assertIsNone(t.end)
        self.assertEqual(t.title, "x Feb30")

    def test_months_are_case_sensitive(self):
        t = self.task("x oct24")
        self.assertIsNone(t.end)

    def test_date_inside_word_ignored(self):
        t = self.task("xOct24")
        self.assertIsNone(t.end)

    def test_reminders(self):
        t = self.task("x *Oct19 *daily *weekly Fri *monthly 1st")
        specs = [s for s, _ in t.reminders]
        self.assertEqual(specs, ["Oct19", "daily", "weekly Fri", "monthly 1st"])
        self.assertEqual(t.title, "x")
        self.assertIsNone(t.end, "a reminder date is not a due date")


# ---------- date resolution ----------

class TestDates(Base):
    def test_window(self):
        # Oct 12 2026: window is Jul 14 2026 .. Jul 13 2027
        self.assertEqual(planner.resolve(7, 14), date(2026, 7, 14))
        self.assertEqual(planner.resolve(7, 13), date(2027, 7, 13))
        self.assertEqual(planner.resolve(9, 30), date(2026, 9, 30))
        self.assertEqual(planner.resolve(1, 15), date(2027, 1, 15))

    def test_feb29(self):
        self.assertIsNone(planner.resolve(2, 29))   # Feb 2027 has no 29th
        planner.set_today("2027-10-12")
        self.assertEqual(planner.resolve(2, 29), date(2028, 2, 29))

    def test_resolve_after(self):
        self.assertEqual(planner.resolve_after(1, 10, date(2026, 12, 15)), date(2027, 1, 10))
        self.assertEqual(planner.resolve_after(12, 15, date(2026, 12, 15)), date(2026, 12, 15))

    def test_loose_recent_past_period(self):
        # ~Sep ended within the last 90 days, so it is this year's (overdue), not next year's
        self.assertEqual(planner.loose_span("Sep"), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(planner.loose_span("Q3"), (date(2026, 7, 1), date(2026, 9, 30)))

    def test_reminder_one_off(self):
        self.assertEqual(planner.next_reminder("Oct19"), date(2026, 10, 19))
        self.assertIsNone(planner.next_reminder("Oct01"))   # already passed

    def test_reminder_repeating(self):
        # Oct 12 2026 is a Monday
        self.assertEqual(planner.next_reminder("daily"), date(2026, 10, 12))
        self.assertEqual(planner.next_reminder("weekly Mon"), date(2026, 10, 12))
        self.assertEqual(planner.next_reminder("weekly Fri"), date(2026, 10, 16))
        self.assertEqual(planner.next_reminder("weekly friday"), date(2026, 10, 16))
        self.assertEqual(planner.next_reminder("monthly 1st"), date(2026, 11, 1))
        self.assertEqual(planner.next_reminder("monthly 12"), date(2026, 10, 12))

    def test_monthly_skips_short_months(self):
        planner.set_today("2027-01-31")
        self.assertEqual(planner.next_reminder("monthly 31st"), date(2027, 1, 31))
        planner.set_today("2027-02-01")
        self.assertEqual(planner.next_reminder("monthly 31st"), date(2027, 3, 31))

    def test_set_today_forms(self):
        planner.set_today("2026-10-12")
        self.assertEqual(planner.TODAY, date(2026, 10, 12))
        planner.set_today("Oct12")
        self.assertEqual(planner.TODAY, date(date.today().year, 10, 12))

    def test_formatting(self):
        self.assertEqual(planner.fd(date(2026, 10, 24)), "Oct 24")
        self.assertEqual(planner.fd(date(2027, 1, 5)), "Jan 5 2027")
        self.assertEqual(planner.fspan(date(2026, 10, 20), date(2026, 10, 23)), "Oct 20-23")
        self.assertEqual(planner.fspan(date(2026, 10, 26), date(2026, 11, 6)), "Oct 26 - Nov 6")


# ---------- derived semantics ----------

class TestSemantics(Base):
    def test_span_own_stretches_over_children(self):
        ps = planner.parse("@A\n- parent Oct24\n\t- child Oct20\n")
        self.assertEqual(ps[0].tasks[0].span(), (date(2026, 10, 20), date(2026, 10, 24), "own"))

    def test_span_rollup(self):
        ps = planner.parse("@A\n- parent\n\t- a Oct20\n\t- b Nov03\n")
        self.assertEqual(ps[0].tasks[0].span(), (date(2026, 10, 20), date(2026, 11, 3), "rollup"))

    def test_span_inherited_from_nearest_dated_ancestor(self):
        ps = planner.parse("@A\n- top Feb16--18\n\t- mid\n\t\t- leaf\n")
        leaf = ps[0].tasks[0].children[0].children[0]
        self.assertEqual(leaf.span(), (date(2027, 2, 16), date(2027, 2, 18), "parent"))

    def test_unscheduled(self):
        ps = planner.parse("@A\n- nothing\n")
        self.assertIsNone(ps[0].tasks[0].span())
        self.assertFalse(ps[0].tasks[0].overdue())

    def test_overdue(self):
        ps = planner.parse("@A\n- late Sep30\n!- done late Sep30\n- today Oct12\n")
        late, done, today = ps[0].tasks
        self.assertTrue(late.overdue())
        self.assertFalse(done.overdue())
        self.assertFalse(today.overdue())

    def test_assignees_not_inherited(self):
        ps = planner.parse("@A\n- parent (KA)\n\t- child\n")
        self.assertEqual(ps[0].tasks[0].children[0].assignees, [])

    def test_section_dates_not_inherited(self):
        ps = planner.parse("Fall  Sep01--Dec19\n@A\n- task\n")
        self.assertIsNone(ps[0].tasks[0].span())


# ---------- example.txt checklist (AGENTS.md > Testing) ----------

class TestExample(Base):
    def setUp(self):
        super().setUp()
        self.ps = planner.parse(read_example())

    def test_site_visit_prep_overdue(self):
        self.assertTrue(self.find(self.ps, "site visit prep").overdue())

    def test_note_under_complete_powerpoint(self):
        self.assertIn("use Q3 numbers from Lisa's deck", self.find(self.ps, "complete powerpoint").notes)

    def test_plan_agenda_via_parent(self):
        self.assertEqual(self.find(self.ps, "plan agenda").span(),
                         (date(2027, 2, 16), date(2027, 2, 18), "parent"))
        self.assertIn("Feb 16-18 2027 (via parent)", "\n".join(planner.view_timeline(self.ps)))

    def test_update_handbook_unscheduled(self):
        _, unscheduled = planner.timeline_rows(self.ps)
        self.assertIn("update handbook", [t.title for _, t in unscheduled])

    def test_annual_report_spans_q1(self):
        s, e, _ = self.find(self.ps, "annual report").span()
        self.assertEqual((s, e), (date(2027, 1, 1), date(2027, 3, 31)))

    def test_counts(self):
        counts = {p.name: (sum(t.status == "done" for t in p.all_tasks()), len(list(p.all_tasks())))
                  for p in self.ps}
        self.assertEqual(counts, {"HDC": (2, 11), "MDM": (1, 6), "OPS": (0, 5)})

    def test_people(self):
        groups = dict(planner.people_groups(self.ps))
        self.assertEqual(list(groups), ["JS", "KA", "RT", "(unassigned)"])
        self.assertEqual(len(groups["KA"]), 5)
        self.assertNotIn("meet w. clients", [t.title for _, t in groups["KA"]])   # done is hidden

    def test_upcoming(self):
        _, overdue, due, doing, reminders = planner.upcoming_groups(self.ps)
        self.assertEqual([t.title for _, _, t in overdue], ["site visit prep"])
        self.assertEqual(sorted(t.title for _, _, t in due),
                         ["complete powerpoint", "finish proposal", "review with KA",
                          "send to board", "set up accounts"])
        self.assertEqual({t.title for _, t in doing}, {"complete powerpoint", "annual report"})
        self.assertEqual(sorted((d, s) for d, s, _, _ in reminders),
                         [(date(2026, 10, 16), "weekly Fri"), (date(2026, 10, 19), "Oct19"),
                          (date(2026, 10, 23), "Oct23")])

    def test_views_render(self):
        for name, view in planner.VIEWS.items():
            out = view(self.ps)
            self.assertEqual(out[0], name.upper())
            self.assertTrue(all(isinstance(line, str) for line in out))

    def test_to_data_matches_views(self):
        d = json.loads(json.dumps(planner.to_data(self.ps)))
        self.assertEqual(d["today"], "2026-10-12")
        self.assertEqual([s["title"] for s in d["projects"]], ["Fall Planning", "Winter Planning"])
        self.assertEqual(len(d["timeline"]["months"]), 12)
        self.assertEqual([t["title"] for t in d["timeline"]["unscheduled"]], ["update handbook"])
        self.assertEqual([p["name"] for p in d["people"]], ["JS", "KA", "RT", "(unassigned)"])
        self.assertEqual([t["title"] for t in d["upcoming"]["overdue"]], ["site visit prep"])
        agenda = next(r for r in d["timeline"]["rows"] if r["title"] == "plan agenda")
        self.assertEqual(agenda["span"]["how"], "parent")
        self.assertEqual(agenda["line"], 34)


# ---------- editing ----------

class TestSetStatus(Base):
    def changed_lines(self, before, after):
        a, b = before.splitlines(keepends=True), after.splitlines(keepends=True)
        self.assertEqual(len(a), len(b))
        return [(i + 1, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]

    def test_only_the_status_mark_changes(self):
        text = read_example()
        t = self.find(planner.parse(text), "send to board")
        new = planner.set_status(text, t.line, "done", t.title)
        self.assertEqual(self.changed_lines(text, new),
                         [(t.line, "\t- send to board Oct24 *Oct23\n", "\t!- send to board Oct24 *Oct23\n")])

    def test_all_transitions(self):
        for old, new, want in [("- a", "doing", "~- a"), ("~- a", "done", "!- a"), ("!- a", "open", "- a"),
                               ("- a", "open", "- a"), ("!-a", "doing", "~-a")]:
            with self.subTest(old=old, new=new):
                self.assertEqual(planner.set_status("@P\n" + old + "\n", 2, new), "@P\n" + want + "\n")

    def test_every_task_round_trips(self):
        text = read_example()
        for p in planner.parse(text):
            for t in p.all_tasks():
                out = text
                for st in ("open", "doing", "done", t.status):
                    out = planner.set_status(out, t.line, st, t.title)
                    self.assertEqual(len(self.changed_lines(text, out)), 0 if st == t.status else 1)
                self.assertEqual(out, text)

    def test_preserves_whitespace_and_line_endings(self):
        text = "@P\r\n    \t- a  (KA)  Oct24   \r\n\n- b"
        out = planner.set_status(text, 2, "done")
        self.assertEqual(out, "@P\r\n    \t!- a  (KA)  Oct24   \r\n\n- b")
        self.assertEqual(planner.set_status(text, 4, "doing"), "@P\r\n    \t- a  (KA)  Oct24   \r\n\n~- b")

    def test_result_parses_with_new_status(self):
        text = read_example()
        t = self.find(planner.parse(text), "site visit prep")
        new = planner.set_status(text, t.line, "done", t.title)
        self.assertFalse(self.find(planner.parse(new), "site visit prep").overdue())

    def test_refuses_non_tasks(self):
        text = "Fall\n@P\n-- a note\n- task\n\tplain note\n\n"
        for line in (1, 2, 3, 5, 6):
            with self.subTest(line=line), self.assertRaises(planner.EditError):
                planner.set_status(text, line, "done")

    def test_refuses_stale_or_bad_requests(self):
        text = "@P\n- a\n- b\n"
        for line, status, title in [(2, "done", "b"), (0, "done", None), (4, "done", None),
                                    ("2", "done", None), (True, "done", None), (2, "finished", None)]:
            with self.subTest(line=line, status=status, title=title), self.assertRaises(planner.EditError):
                planner.set_status(text, line, status, title)


class TestServer(Base):
    def setUp(self):
        super().setUp()
        self.server = planner.make_server(0)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def post(self, path, payload):
        req = urllib.request.Request(self.url + path, json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_page(self):
        with urllib.request.urlopen(self.url + "/") as r:
            self.assertIn(b"/api/edit", r.read())

    def test_parse(self):
        code, d = self.post("/api/parse", {"text": read_example(), "today": "2026-10-12"})
        self.assertEqual(code, 200)
        self.assertEqual([t["title"] for t in d["upcoming"]["overdue"]], ["site visit prep"])

    def test_edit(self):
        text = read_example()
        code, d = self.post("/api/edit", {"text": text, "line": 17, "status": "done",
                                          "title": "site visit prep", "today": "2026-10-12"})
        self.assertEqual(code, 200)
        self.assertEqual(d["text"], text.replace("- site visit prep", "!- site visit prep"))
        self.assertEqual(d["data"]["upcoming"]["overdue"], [])

    def test_edit_stale_is_409(self):
        code, d = self.post("/api/edit", {"text": read_example(), "line": 17, "status": "done", "title": "other"})
        self.assertEqual(code, 409)
        self.assertIn("no longer that task", d["error"])

    def test_edit_missing_fields_is_400(self):
        code, d = self.post("/api/edit", {"text": "- a"})
        self.assertEqual(code, 400)


# ---------- CLI ----------

class TestCLI(unittest.TestCase):
    def run_cli(self, *args, stdin=None, code=0):
        r = subprocess.run([sys.executable, os.path.join(HERE, "planner.py"), *args],
                           input=stdin or "", capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, code, r.stderr)
        return r.stdout if code == 0 else r.stderr

    def test_bad_arguments_give_one_line_errors(self):
        cases = [
            ((EXAMPLE, "timline"), "is not a file or a view"),
            (("no-such-file.txt",), "is not a file or a view"),
            ((EXAMPLE, EXAMPLE), "only one notes file"),
            ((EXAMPLE, "--today"), "--today needs a value"),
            ((EXAMPLE, "--today", "Feb30"), "bad --today value"),
            ((EXAMPLE, "--today", "soon"), "bad --today value"),
            (("--serve", "--port"), "--port needs a value"),
            (("--serve", "--port", "abc"), "bad --port value"),
            (("--serve", "--port", "70000"), "bad --port value"),
        ]
        for args, msg in cases:
            with self.subTest(args=args):
                err = self.run_cli(*args, code=1)
                self.assertIn(msg, err)
                self.assertNotIn("Traceback", err)

    def test_view_names_ignore_case(self):
        self.assertTrue(self.run_cli(EXAMPLE, "PEOPLE", "--today", "2026-10-12").startswith("PEOPLE"))

    def test_all_views(self):
        out = self.run_cli(EXAMPLE, "--today", "2026-10-12")
        for heading in ("PROJECTS", "TIMELINE", "PEOPLE", "UPCOMING"):
            self.assertIn(heading, out)
        self.assertIn("site visit prep   Sep 30   OVERDUE", out)

    def test_one_view(self):
        out = self.run_cli(EXAMPLE, "timeline", "--today", "2026-10-12")
        self.assertTrue(out.startswith("TIMELINE"))
        self.assertNotIn("PROJECTS", out)

    def test_stdin_matches_file(self):
        self.assertEqual(self.run_cli("--today", "2026-10-12", stdin=read_example()),
                         self.run_cli(EXAMPLE, "--today", "2026-10-12"))

    def test_empty_input(self):
        self.assertIn("No projects or tasks found.", self.run_cli(stdin="\n"))


if __name__ == "__main__":
    unittest.main()
