"""
Tests for planner.py. Standard library only:  python -m unittest -v

Every test pins TODAY (default Oct 12 2026) because dates are written without years.
"""
import json
import os
import stat
import subprocess
import tempfile
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

    def test_effort(self):
        for size, points in (("s", 1), ("m", 3), ("l", 5), ("xl", 8)):
            with self.subTest(size=size):
                t = self.task(f"write report (KA) ({size}) Oct24")
                self.assertEqual((t.effort, t.points, t.title, t.assignees), (size, points, "write report", ["KA"]))
        t = self.task("a ( xl ) b")
        self.assertEqual((t.effort, t.title), ("xl", "a b"))

    def test_no_effort(self):
        t = self.task("a")
        self.assertEqual((t.effort, t.points), (None, 0))

    def test_uppercase_effort_is_initials(self):
        t = self.task("a (S) (XL)")
        self.assertEqual((t.effort, t.assignees), (None, ["S", "XL"]))

    def test_effort_attached_to_word_or_unknown_stays_in_title(self):
        for text in ("review file(s)", "a (xs)", "a (xxl)", "a (med)"):
            with self.subTest(text=text):
                t = self.task(text)
                self.assertEqual((t.effort, t.title), (None, text))

    def test_only_first_effort_counts(self):
        t = self.task("a (s) b (l)")
        self.assertEqual((t.effort, t.title), ("s", "a b (l)"))

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

    def test_effort_not_inherited_or_rolled_up(self):
        ps = planner.parse("@P\n- parent (l)\n\t- child\n\t!- done child (m)\n- other (s)\n")
        self.assertEqual(self.find(ps, "child").points, 0)
        self.assertEqual(self.find(ps, "parent").points, 5)
        self.assertEqual(planner.effort_points(ps[0].all_tasks()), (6, 9))

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

    def test_effort_totals(self):
        self.assertEqual({p.name: planner.effort_points(p.all_tasks()) for p in self.ps},
                         {"HDC": (9, 10), "MDM": (3, 3), "OPS": (8, 8)})
        groups = dict(planner.people_groups(self.ps))
        self.assertEqual(planner.effort_points(t for _, t in groups["KA"])[0], 13)   # (l) + (xl)
        projects = "\n".join(planner.view_projects(self.ps))
        self.assertIn("@HDC   2/11 done   9 of 10 pts left", projects)
        self.assertIn("[ ] finish proposal (KA) [L]   Oct 24", projects)
        self.assertIn("\n@OPS   0/5 done   8 of 8 pts left", projects)
        people = "\n".join(planner.view_people(self.ps))
        self.assertIn("KA   5 task(s), 13 pts", people)
        self.assertIn("RT   2 task(s), 8 pts", people)
        self.assertIn("[~] @HDC  complete powerpoint [M]   Oct 20-23", people)

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
        self.assertEqual([c["head"] for c in d["timeline"]["columns"]],
                         ["O 26", "N", "D", "J 27", "F", "M", "A", "M", "J", "J", "A", "S"])
        self.assertIsNone(d["period"])
        self.assertEqual([t["title"] for t in d["timeline"]["unscheduled"]], ["meet w. clients", "interviews", "update handbook"])
        gather = next(r for r in d["timeline"]["rows"] if r["title"] == "gather requirements")   # done tasks are sent; the page hides them on request
        self.assertEqual(gather["status"], "done")
        self.assertNotIn("gather requirements", "\n".join(planner.view_timeline(self.ps)))
        self.assertEqual([p["name"] for p in d["people"]], ["JS", "KA", "RT", "(unassigned)"])
        self.assertEqual([t["title"] for t in d["upcoming"]["overdue"]], ["site visit prep"])
        agenda = next(r for r in d["timeline"]["rows"] if r["title"] == "plan agenda")
        self.assertEqual(agenda["span"]["how"], "parent")
        self.assertEqual(agenda["line"], 34)
        hdc = d["projects"][0]["projects"][0]
        self.assertEqual(hdc["points"], {"left": 9, "total": 10})
        proposal = hdc["tasks"][1]
        self.assertEqual((proposal["title"], proposal["effort"], proposal["points"]), ("finish proposal", "l", 5))
        annual = hdc["tasks"][2]
        self.assertEqual((annual["title"], annual["loose"], proposal["loose"]), ("annual report", "Q1", None))
        self.assertEqual({g["name"]: g["points"] for g in d["people"]}, {"JS": 11, "KA": 13, "RT": 8, "(unassigned)": 4})


# ---------- periods (Month / Season picker) ----------

class TestPeriods(Base):
    def setUp(self):
        super().setUp()
        self.ps = planner.parse(read_example())

    def data(self, kind, year, index):
        return planner.to_data(self.ps, planner.period_from({"kind": kind, "year": year, "index": index}))

    def titles(self, d):
        def walk(t):
            yield ("(" + t["title"] + ")") if t.get("dim") else t["title"]
            for c in t["children"]:
                yield from walk(c)
        return [x for sec in d["projects"] for p in sec["projects"] for t in p["tasks"] for x in walk(t)]

    def test_seasons_are_jan_apr_may_aug_sep_dec(self):
        self.assertEqual([planner.period_range("season", 2027, i) for i in range(3)],
                         [(date(2027, 1, 1), date(2027, 4, 30)), (date(2027, 5, 1), date(2027, 8, 31)),
                          (date(2027, 9, 1), date(2027, 12, 31))])
        self.assertEqual([planner.period_at("season", date(2026, m, 15))[2] for m in range(1, 13)],
                         [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2])

    def test_stepping_crosses_years(self):
        self.assertEqual(planner.period_step("month", 2026, 12, 1), ("month", 2027, 1))
        self.assertEqual(planner.period_step("month", 2026, 1, -1), ("month", 2025, 12))
        self.assertEqual(planner.period_step("season", 2026, 2, 1), ("season", 2027, 0))
        self.assertEqual(planner.period_step("season", 2027, 0, -1), ("season", 2026, 2))
        self.assertEqual(planner.period_step("month", 2026, 10, 15), ("month", 2028, 1))

    def test_labels(self):
        self.assertEqual(planner.period_label("month", 2026, 10), "Oct 2026")
        self.assertEqual(planner.period_label("season", 2027, 0), "Winter 2027 (Jan-Apr)")

    def test_month_columns_are_weeks(self):
        cols = planner.period_columns("month", 2026, 10)      # Oct 1 2026 is a Thursday
        self.assertEqual([h for h, _, _ in cols], ["1-4", "5-11", "12-18", "19-25", "26-31"])
        self.assertEqual((cols[0][1], cols[-1][2]), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual([h for h, _, _ in planner.period_columns("month", 2027, 2)][-1], "22-28")

    def test_fall_2026(self):
        d = self.data("season", 2026, 2)
        self.assertEqual([c["head"] for c in d["timeline"]["columns"]], ["Sep", "Oct", "Nov", "Dec"])
        self.assertEqual(d["period"]["label"], "Fall 2026 (Sep-Dec)")
        self.assertEqual(d["period"]["short"], "Fall 2026")
        self.assertEqual((d["period"]["prev"], d["period"]["next"], d["period"]["now"], d["period"]["current"]),
                         ({"kind": "season", "year": 2026, "index": 1, "label": "Summer 2026"},
                          {"kind": "season", "year": 2027, "index": 0, "label": "Winter 2027"},
                          {"kind": "season", "year": 2026, "index": 2, "label": "Fall 2026"}, True))
        self.assertFalse(self.data("season", 2027, 0)["period"]["current"])
        nov = self.data("month", 2026, 11)["period"]
        self.assertEqual((nov["prev"]["label"], nov["label"], nov["next"]["label"]), ("Oct 2026", "Nov 2026", "Dec 2026"))
        self.assertEqual(planner.period_from(nov["next"]), ("month", 2026, 12))     # labels are ignored on the way back
        titles = self.titles(d)
        self.assertIn("site visit prep", titles)              # Sep 30: overdue, still in Fall
        self.assertIn("quarterly review", titles)
        self.assertNotIn("annual report", titles)             # ~Q1
        self.assertNotIn("update handbook", titles)           # undated
        self.assertNotIn("meet w. clients", titles)           # done and undated
        self.assertEqual(d["timeline"]["unscheduled"], [])
        self.assertEqual([p["name"] for sec in d["projects"] for p in sec["projects"]], ["HDC", "MDM"])

    def test_winter_2027_includes_inherited_and_rolled_up_dates(self):
        d = self.data("season", 2027, 0)
        titles = self.titles(d)
        for t in ("annual report", "final layout", "plan agenda", "team offsite", "renew software licenses"):
            self.assertIn(t, titles)
        self.assertIn("budget planning", titles)              # ~Q2 is Apr-Jun, so it overlaps Winter's April
        self.assertNotIn("quarterly review", titles)          # Dec 8-12
        rows = {r["title"]: r["bar"] for r in d["timeline"]["rows"]}
        self.assertEqual(rows["annual report"], [True, True, True, False])
        self.assertEqual(rows["final layout"], [False, False, True, False])

    def test_month_view_people_and_upcoming(self):
        d = self.data("month", 2026, 11)
        self.assertEqual(sorted(t["title"] for g in d["people"] for t in g["tasks"]),
                         ["first-week check-in", "onboard new hire"])
        self.assertEqual([t["title"] for t in d["upcoming"]["overdue"]], ["site visit prep"])   # unchanged
        rows = {r["title"]: r["bar"] for r in d["timeline"]["rows"]}
        self.assertEqual([c["head"] for c in d["timeline"]["columns"]], ["1", "2-8", "9-15", "16-22", "23-29", "30"])
        self.assertEqual(rows["first-week check-in"], [False, True, False, False, False, False])  # Nov 6

    def test_empty_period(self):
        d = self.data("month", 2028, 6)
        self.assertEqual((d["projects"], d["people"], d["timeline"]["rows"]), ([], [], []))

    def test_bad_periods(self):
        for bad in ({"kind": "year", "year": 2026, "index": 1}, {"kind": "month", "year": 2026, "index": 13},
                    {"kind": "season", "year": 2026, "index": 3}, {"kind": "month", "year": "2026", "index": 1},
                    {"kind": "month", "year": 99999, "index": 1}, "Fall"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                planner.period_from(bad)
        self.assertIsNone(planner.period_from(None))
        self.assertEqual(planner.period_from({"kind": "season"}), ("season", 2026, 2))   # today is Oct 12 2026
        self.assertEqual(planner.period_from({"kind": "month"}), ("month", 2026, 10))


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
                         [(t.line, "\t- send to board (s) Oct24 *Oct23\n", "\t!- send to board (s) Oct24 *Oct23\n")])

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


class EditBase(Base):
    def assert_one_line_changed(self, before, after, line, want):
        a, b = before.splitlines(keepends=True), after.splitlines(keepends=True)
        self.assertEqual(len(a), len(b))
        self.assertEqual([i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y], [line])
        self.assertEqual(b[line - 1], want)


class TestSetDate(EditBase):
    def test_add_at_end(self):
        out = planner.set_date("@P\n\t- a  (KA)   \r\n", 2, "Oct24")
        self.assertEqual(out, "@P\n\t- a  (KA) Oct24   \r\n")

    def test_add_before_reminder(self):
        self.assertEqual(planner.set_date("- a *weekly Fri\n", 1, "Oct24"), "- a Oct24 *weekly Fri\n")

    def test_replace_in_place(self):
        text = read_example()
        t = self.find(planner.parse(text), "complete powerpoint")
        out = planner.set_date(text, t.line, "~wk44", t.title)
        self.assert_one_line_changed(text, out, t.line, "\t~- complete powerpoint (JS) (m) ~wk44 *Oct19\n")
        self.assertEqual(self.find(planner.parse(out), "complete powerpoint").loose, "wk44")

    def test_replace_each_kind(self):
        for old in ("Oct20", "Oct20--23", "Oct20--Nov02", "~Q1", "~Nov", "~wk43"):
            with self.subTest(old=old):
                self.assertEqual(planner.set_date(f"- call {old} (KA)\n", 1, "Dec01"), "- call Dec01 (KA)\n")

    def test_clear(self):
        self.assertEqual(planner.set_date("- a  Oct24 *Oct20\n", 1, ""), "- a *Oct20\n")
        self.assertEqual(planner.set_date("- Oct24 a\n", 1, ""), "-  a\n")     # spaces after are left alone
        with self.assertRaises(planner.EditError):
            planner.set_date("- a\n", 1, "")

    def test_rejects_non_dates(self):
        for bad in ("Oct 24", "oct24", "Feb30", "tomorrow", "Oct24 Oct25", "(KA)"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_date("- a\n", 1, bad)

    def test_refuses_when_earlier_token_wins(self):
        with self.assertRaises(planner.EditError):          # Feb30 is found first and fails, so Oct24 would be ignored
            planner.set_date("- a Feb30\n", 1, "Oct24")

    def test_resetting_own_date_is_a_no_op(self):
        text = read_example()
        for p in planner.parse(text):
            for t in p.all_tasks():
                if t.date_text:
                    self.assertEqual(planner.set_date(text, t.line, t.date_text, t.title), text)

    def test_date_text(self):
        t = self.find(planner.parse(read_example()), "onboard new hire")
        self.assertEqual(t.date_text, "Oct26--Nov06")


class TestSetEffort(EditBase):
    def test_add_before_date_or_reminder_or_at_end(self):
        text = read_example()
        t = self.find(planner.parse(text), "review with KA")
        out = planner.set_effort(text, t.line, "m", t.title)
        self.assert_one_line_changed(text, out, t.line, "\t\t- review with KA (m) Oct22\n")
        self.assertEqual(planner.set_effort("- a (KA) *daily\n", 1, "s"), "- a (KA) (s) *daily\n")
        self.assertEqual(planner.set_effort("- a*daily\n", 1, "s"), "- a (s) *daily\n")
        self.assertEqual(planner.set_effort("\t- a  (KA)   \r\n", 1, "xl"), "\t- a  (KA) (xl)   \r\n")

    def test_replace_in_place(self):
        text = read_example()
        t = self.find(planner.parse(text), "complete powerpoint")
        out = planner.set_effort(text, t.line, "xl", t.title)
        self.assert_one_line_changed(text, out, t.line, "\t~- complete powerpoint (JS) (xl) Oct20--23 *Oct19\n")
        self.assertEqual(planner.set_effort("- a ( m ) b\n", 1, "l"), "- a (l) b\n")

    def test_input_forms(self):
        for value in ("M", " m ", "(m)", "( M )"):
            with self.subTest(value=value):
                self.assertEqual(planner.set_effort("- a\n", 1, value), "- a (m)\n")

    def test_clear(self):
        self.assertEqual(planner.set_effort("- a  (m)  Oct24\n", 1, ""), "- a  Oct24\n")
        with self.assertRaises(planner.EditError):
            planner.set_effort("- a\n", 1, "")

    def test_rejects_bad_sizes(self):
        for bad in ("xs", "xxl", "medium", "3", "S M"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_effort("- a\n", 1, bad)

    def test_refuses_stale_title(self):
        with self.assertRaises(planner.EditError):
            planner.set_effort("- a\n", 1, "m", "b")

    def test_resetting_own_effort_is_a_no_op(self):
        text = read_example()
        for p in planner.parse(text):
            for t in p.all_tasks():
                if t.effort:
                    self.assertEqual(planner.set_effort(text, t.line, t.effort, t.title), text)


class TestAddAssignees(EditBase):
    def test_new_group_before_date(self):
        text = read_example()
        t = self.find(planner.parse(text), "send to board")
        out = planner.add_assignees(text, t.line, "RT", t.title)
        self.assert_one_line_changed(text, out, t.line, "\t- send to board (RT) (s) Oct24 *Oct23\n")

    def test_new_group_before_reminder_or_at_end(self):
        self.assertEqual(planner.add_assignees("- a *daily\n", 1, "KA"), "- a (KA) *daily\n")
        self.assertEqual(planner.add_assignees("- a  \n", 1, "KA, RT"), "- a (KA, RT)  \n")
        self.assertEqual(planner.add_assignees("- a (m) Oct24\n", 1, "KA"), "- a (KA) (m) Oct24\n")

    def test_join_existing_group(self):
        self.assertEqual(planner.add_assignees("- a (KA) Oct24\n", 1, "RT JS"), "- a (KA, RT, JS) Oct24\n")
        self.assertEqual(planner.add_assignees("- a ( KA ) x\n", 1, "RT"), "- a ( KA, RT ) x\n")
        self.assertEqual(planner.add_assignees("- a (KA) (RT)\n", 1, "JS"), "- a (KA) (RT, JS)\n")

    def test_skips_existing_and_rejects_bad(self):
        self.assertEqual(planner.add_assignees("- a (KA)\n", 1, "KA, RT, RT"), "- a (KA, RT)\n")
        for bad in ("KA", "ka", "ABCDE", "", "K1"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.add_assignees("- a (KA)\n", 1, bad)


class TestSetAssignees(EditBase):
    def test_replace_in_place(self):
        text = read_example()
        t = self.find(planner.parse(text), "team offsite")
        out = planner.set_assignees(text, t.line, "KA, JS", t.title)
        self.assert_one_line_changed(text, out, t.line, "- team offsite (KA, JS) (xl) Feb16--18\n")

    def test_remove(self):
        text = read_example()
        t = self.find(planner.parse(text), "finish proposal")
        out = planner.set_assignees(text, t.line, "  ", t.title)
        self.assert_one_line_changed(text, out, t.line, "- finish proposal (l) Oct24\n")
        self.assertEqual(planner.set_assignees("- a (KA)\n", 1, ""), "- a\n")
        with self.assertRaises(planner.EditError):
            planner.set_assignees("- a\n", 1, "")

    def test_several_groups_become_one(self):
        self.assertEqual(planner.set_assignees("- a (KA) b (RT) Oct24\n", 1, "JS"), "- a (JS) b Oct24\n")
        self.assertEqual(planner.set_assignees("- a (KA) b (RT)\n", 1, ""), "- a b\n")

    def test_add_when_none_and_no_change(self):
        self.assertEqual(planner.set_assignees("- a (m) Oct24\n", 1, "rt".upper()), "- a (RT) (m) Oct24\n")
        self.assertEqual(planner.set_assignees("- a (KA, RT)\n", 1, "KA RT KA"), "- a (KA, RT)\n")

    def test_rejects_bad_and_stale(self):
        for bad in ("ka", "ABCDE", "K1"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_assignees("- a (KA)\n", 1, bad)
        with self.assertRaises(planner.EditError):
            planner.set_assignees("- a (KA)\n", 1, "RT", "b")


class TestAddSubtask(EditBase):
    def test_goes_after_last_subtask_and_its_notes(self):
        text = read_example()
        t = self.find(planner.parse(text), "onboard new hire")
        out = planner.add_subtask(text, t.line, "order laptop (RT) Oct27", t.title)
        a, b = text.splitlines(keepends=True), out.splitlines(keepends=True)
        self.assertEqual(b[t.line + 3], "\t- order laptop (RT) Oct27\n")
        self.assertEqual(a, b[:t.line + 3] + b[t.line + 4:])
        new = self.find(planner.parse(out), "order laptop")
        self.assertEqual((new.parent.title, new.assignees), ("onboard new hire", ["RT"]))

    def test_nested_parent_and_notes(self):
        text = "@P\n- a\n\t- b\n\t\t- c\n\t\t-- note on c\n\n- d\n"
        self.assertEqual(planner.add_subtask(text, 3, "new"),
                         "@P\n- a\n\t- b\n\t\t- c\n\t\t-- note on c\n\t\t- new\n\n- d\n")
        self.assertEqual(planner.add_subtask(text, 2, "new"),
                         "@P\n- a\n\t- b\n\t\t- c\n\t\t-- note on c\n\t- new\n\n- d\n")

    def test_stops_at_project_and_heading(self):
        self.assertEqual(planner.add_subtask("@P\n- a\n@Q\n- b\n", 2, "x"), "@P\n- a\n\t- x\n@Q\n- b\n")
        self.assertEqual(planner.add_subtask("@P\n- a\nWinter\n", 2, "x"), "@P\n- a\n\t- x\nWinter\n")

    def test_last_line_and_line_endings(self):
        self.assertEqual(planner.add_subtask("@P\r\n- a", 2, "x"), "@P\r\n- a\n\t- x")
        self.assertEqual(planner.add_subtask("@P\r\n- a\r\n", 2, "x"), "@P\r\n- a\r\n\t- x\r\n")

    def test_space_indented_parent(self):
        self.assertEqual(planner.add_subtask("- a\n    - b\n", 2, "x"), "- a\n    - b\n        - x\n")

    def test_rejects_multiline_and_empty(self):
        for bad in ("", "   ", "a\nb", "a\u2028b"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.add_subtask("- a\n", 1, bad)

    def test_stale_title_refused(self):
        with self.assertRaises(planner.EditError):
            planner.add_subtask("- a\n", 1, "x", "not a")


class TestNotesFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "notes.txt")

    def tearDown(self):
        self.dir.cleanup()

    def put(self, data):
        with open(self.path, "wb") as f:
            f.write(data)

    def get(self):
        with open(self.path, "rb") as f:
            return f.read()

    def test_read_is_exact(self):
        self.put(b"@P\r\n\t- a\r\n")
        text, version = planner.read_notes(self.path)
        self.assertEqual(text, "@P\r\n\t- a\r\n")
        self.assertEqual(version, planner.file_version(b"@P\r\n\t- a\r\n"))

    def test_missing_file_then_created(self):
        self.assertEqual(planner.read_notes(self.path), ("", None))
        v = planner.write_notes(self.path, "- a\n", None)
        self.assertEqual((self.get(), v), (b"- a\n", planner.file_version(b"- a\n")))

    def test_save_and_conflict(self):
        self.put(b"- a\n")
        _, v = planner.read_notes(self.path)
        v2 = planner.write_notes(self.path, "!- a\n", v)
        self.assertEqual(self.get(), b"!- a\n")
        with self.assertRaises(planner.FileConflict):           # v is stale now
            planner.write_notes(self.path, "~- a\n", v)
        self.put(b"- changed elsewhere\n")
        with self.assertRaises(planner.FileConflict):
            planner.write_notes(self.path, "~- a\n", v2)
        self.assertEqual(self.get(), b"- changed elsewhere\n")
        planner.write_notes(self.path, "~- a\n", v2, force=True)
        self.assertEqual(self.get(), b"~- a\n")

    def test_crlf_kept(self):
        self.put(b"@P\r\n- a\r\n")
        _, v = planner.read_notes(self.path)
        planner.write_notes(self.path, "@P\n!- a\n- b\n", v)        # what a browser text box sends back
        self.assertEqual(self.get(), b"@P\r\n!- a\r\n- b\r\n")

    def test_lf_and_mixed_left_alone(self):
        self.put(b"@P\r\n- a\n")
        _, v = planner.read_notes(self.path)
        planner.write_notes(self.path, "@P\n- a\n", v)
        self.assertEqual(self.get(), b"@P\n- a\n")

    def test_unicode_and_permissions(self):
        self.put("- café ✓\n".encode())
        os.chmod(self.path, 0o640)
        text, v = planner.read_notes(self.path)
        planner.write_notes(self.path, "!" + text, v)
        self.assertEqual(self.get().decode(), "!- café ✓\n")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)
        self.assertEqual(os.listdir(self.dir.name), ["notes.txt"])      # no temp files left


class TestServer(Base):
    notes = None

    def setUp(self):
        super().setUp()
        self.server = planner.make_server(0, self.notes)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def post(self, path, payload, headers=None):
        req = urllib.request.Request(self.url + path, json.dumps(payload).encode(),
                                     dict({"Content-Type": "application/json"}, **(headers or {})))
        return self.send(req)

    def send(self, req):
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_other_sites_are_refused(self):
        for headers, code in [({"Origin": "https://evil.example"}, 403), ({"Host": "evil.example:80"}, 403),
                              ({"Content-Type": "text/plain"}, 415),
                              ({"Origin": self.url.replace("127.0.0.1", "localhost")}, 200)]:
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/api/parse", {"text": "- a"}, headers)[0], code)
        req = urllib.request.Request(self.url + "/api/file", headers={"Origin": "https://evil.example"})
        self.assertEqual(self.send(req)[0], 403)

    def test_no_notes_file(self):
        with urllib.request.urlopen(self.url + "/api/file") as r:
            self.assertEqual(json.loads(r.read()), {"name": None})
        self.assertEqual(self.post("/api/file", {"text": "x", "version": None})[0], 409)

    def test_page(self):
        with urllib.request.urlopen(self.url + "/") as r:
            self.assertIn(b"/api/edit", r.read())

    def test_example(self):
        with urllib.request.urlopen(self.url + "/api/example") as r:
            self.assertEqual(json.loads(r.read()), {"text": read_example()})
        req = urllib.request.Request(self.url + "/api/example", headers={"Origin": "https://evil.example"})
        self.assertEqual(self.send(req)[0], 403)

    def test_parse(self):
        code, d = self.post("/api/parse", {"text": read_example(), "today": "2026-10-12"})
        self.assertEqual(code, 200)
        self.assertEqual([t["title"] for t in d["upcoming"]["overdue"]], ["site visit prep"])

    def test_edit(self):
        text = read_example()
        code, d = self.post("/api/edit", {"text": text, "line": 17, "op": "status", "value": "done",
                                          "title": "site visit prep", "today": "2026-10-12"})
        self.assertEqual(code, 200)
        self.assertEqual(d["text"], text.replace("- site visit prep", "!- site visit prep"))
        self.assertEqual(d["data"]["upcoming"]["overdue"], [])

    def test_edit_stale_is_409(self):
        code, d = self.post("/api/edit", {"text": read_example(), "line": 17, "op": "status", "value": "done",
                                          "title": "other"})
        self.assertEqual(code, 409)
        self.assertIn("no longer that task", d["error"])

    def test_edit_missing_fields_is_400(self):
        code, d = self.post("/api/edit", {"text": "- a"})
        self.assertEqual(code, 400)

    def test_parse_and_edit_with_period(self):
        period = {"kind": "season", "year": 2026, "index": 2}
        code, d = self.post("/api/parse", {"text": read_example(), "today": "2026-10-12", "period": period})
        self.assertEqual((code, d["period"]["label"]), (200, "Fall 2026 (Sep-Dec)"))
        code, d = self.post("/api/edit", {"text": "@P\n- a Oct24\n- b Feb02\n", "line": 2, "op": "status",
                                          "value": "done", "today": "2026-10-12", "period": period})
        self.assertEqual([t["title"] for t in d["data"]["projects"][0]["projects"][0]["tasks"]], ["a"])
        self.assertEqual(self.post("/api/parse", {"text": "", "period": {"kind": "week"}})[0], 400)

    def test_edit_bad_op_or_value_is_409(self):
        for extra in ({"op": "delete", "value": ""}, {"op": "date", "value": 5}):
            code, _ = self.post("/api/edit", dict({"text": "- a", "line": 1}, **extra))
            self.assertEqual(code, 409)

    def test_edit_ops(self):
        text = "@P\n- a\n"
        for op, value, want in [("date", "Oct24", "@P\n- a Oct24\n"), ("assign", "KA", "@P\n- a (KA)\n"),
                                ("effort", "m", "@P\n- a (m)\n"),
                                ("who", "KA, RT", "@P\n- a (KA, RT)\n"),
                                ("subtask", "b", "@P\n- a\n\t- b\n")]:
            code, d = self.post("/api/edit", {"text": text, "line": 2, "op": op, "value": value, "title": "a"})
            self.assertEqual((code, d["text"]), (200, want))


class TestServerWithFile(TestServer):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.notes = os.path.join(self.dir.name, "plan.txt")
        with open(self.notes, "wb") as f:
            f.write(b"@P\r\n- a\r\n")
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.dir.cleanup()

    def test_no_notes_file(self):
        pass

    def test_load_save_conflict(self):
        with urllib.request.urlopen(self.url + "/api/file") as r:
            d = json.loads(r.read())
        self.assertEqual((d["name"], d["text"]), ("plan.txt", "@P\r\n- a\r\n"))
        code, s = self.post("/api/file", {"text": "@P\n!- a\n", "version": d["version"]})
        self.assertEqual(code, 200)
        with open(self.notes, "rb") as f:
            self.assertEqual(f.read(), b"@P\r\n!- a\r\n")
        code, c = self.post("/api/file", {"text": "@P\n~- a\n", "version": d["version"]})   # stale
        self.assertEqual((code, c["conflict"], c["version"]), (409, True, s["version"]))
        self.assertEqual(self.post("/api/file", {"text": "@P\n~- a\n", "version": None, "force": True})[0], 200)
        self.assertEqual(self.post("/api/file", {"text": 5, "version": None})[0], 400)


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
            (("--serve", EXAMPLE, "timeline"), "at most one notes file"),
            (("--serve", HERE), "not a file in an existing folder"),
            (("--serve", os.path.join(HERE, "no-such-dir", "x.txt")), "not a file in an existing folder"),
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
