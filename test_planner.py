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
import urllib.parse
import urllib.request
from datetime import date

import planner

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "example.kf")         # the reference notes (example.txt is free for your own)
PORTFOLIO = os.path.join(HERE, "example")           # the reference portfolio (--import example.kf example --split)


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
                self.assertRegex(lines[t.line - 1].strip(), r"^(\(!\))?[!~]?-(?!-)")
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
        for size, points in (("xs", 1), ("s", 1), ("m", 3), ("l", 5), ("xl", 8)):
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
        for text in ("review file(s)", "a (xxs)", "a (xxl)", "a (med)"):
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

    def test_loose_trimester(self):                           # same months as the seasons; calendar order
        t1, t2, t3 = self.task("x ~T1"), self.task("x ~T2 y"), self.task("x ~T3")
        self.assertEqual((t1.start, t1.end, t1.loose, t1.title), (date(2027, 1, 1), date(2027, 4, 30), "T1", "x"))
        self.assertEqual((t2.start, t2.end, t2.title), (date(2026, 5, 1), date(2026, 8, 31), "x y"))   # within 90 days back
        self.assertEqual((t3.start, t3.end), (date(2026, 9, 1), date(2026, 12, 31)))
        for name, (_, a, b) in zip(("T1", "T2", "T3"), planner.SEASONS):
            span = self.task("x ~" + name)
            self.assertEqual((span.start.month, span.end.month), (a, b))
        for bad in ("x ~T4", "x ~T0", "x ~t1", "x ~T12"):
            with self.subTest(bad=bad):
                self.assertEqual((self.task(bad).end, self.task(bad).title), (None, bad))
        self.assertEqual(planner.fspan(t3.start, t3.end, t3.loose), "~T3 (Sep 1 - Dec 31)")
        self.assertEqual(planner.set_date("- a\n", 1, "~T2"), "- a ~T2\n")

    def test_loose_periods_fill_whole_months_on_the_timeline(self):
        ps = planner.parse("@P\n- t1 ~T1\n- t2 ~T2\n- t3 ~T3\n" + "".join(f"- q{i} ~Q{i}\n" for i in range(1, 5)))
        bars = lambda d: {r["title"]: "".join("#" if b else "." for b in r["bar"]) for r in d["timeline"]["rows"]}
        months = [c["head"] for c in planner.to_data(ps)["timeline"]["columns"]]
        self.assertEqual(months, ["O 26", "N", "D", "J 27", "F", "M", "A", "M", "J", "J", "A", "S"])
        self.assertEqual(bars(planner.to_data(ps)), {                        # 12 months from Oct 2026
            "t1": "...####.....", "t3": "###.........",     # T3 Sep-Dec: the chart starts in Oct
            "q1": "...###......", "q2": "......###...", "q4": "###.........",
            "t2": "............", "q3": "............"})    # May-Aug / Jul-Sep 2026: just ended, before the chart
        self.assertTrue(all(r["before"] for r in planner.to_data(ps)["timeline"]["rows"] if r["title"] in ("t2", "q3")))
        self.assertEqual(bars(planner.to_data(ps, ("season", 2027, 0))), {   # Winter 2027: Jan Feb Mar Apr
            "t1": "####", "q1": "###.", "q2": "...#"})
        timeline = "\n".join(planner.view_timeline(ps))
        self.assertRegex(timeline, r"@P  t1 +\. \. \. # # # # \. \. \. \. \.  ~T1 \(Jan 1 2027 - Apr 30 2027\)")

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
        self.assertEqual(counts, {"HDC": (2, 11), "MDM": (1, 6), "OPS": (0, 6)})

    def test_effort_totals(self):
        self.assertEqual({p.name: planner.effort_points(p.all_tasks()) for p in self.ps},
                         {"HDC": (9, 10), "MDM": (4, 4), "OPS": (8, 8)})
        groups = dict(planner.people_groups(self.ps))
        self.assertEqual(planner.effort_points(t for _, t in groups["KA"])[0], 13)   # (l) + (xl)
        projects = "\n".join(planner.view_projects(self.ps))
        self.assertIn("@HDC   2/11 done   9 of 10 pts left", projects)
        self.assertIn("[ ] finish proposal (KA) [L]   Oct 24", projects)
        self.assertIn("\n@OPS   0/6 done   8 of 8 pts left", projects)
        people = "\n".join(planner.view_people(self.ps))
        self.assertIn("KA   5 task(s), 13 pts", people)
        self.assertIn("RT   2 task(s), 9 pts", people)
        self.assertIn("[~] @HDC  complete powerpoint [M]   Oct 20-23", people)

    def test_people(self):
        groups = dict(planner.people_groups(self.ps))
        self.assertEqual(list(groups), ["JS", "KA", "RT", "(unassigned)"])
        self.assertEqual(len(groups["KA"]), 5)
        self.assertNotIn("meet w. clients", [t.title for _, t in groups["KA"]])   # done is hidden

    def test_upcoming_order(self):
        out = planner.view_upcoming(self.ps)
        heads = [l.strip() for l in out if l.strip() in ("Overdue", "In progress", "Due soon", "Reminders")]
        self.assertEqual(heads, ["Overdue", "In progress", "Due soon", "Reminders"])

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
        self.assertEqual({g["name"]: g["points"] for g in d["people"]}, {"JS": 11, "KA": 13, "RT": 9, "(unassigned)": 4})


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
                         [(t.line, "\t(!)- send to board (s) Oct24 >Oct14 *Oct23\n", "\t(!)!- send to board (s) Oct24 >Oct14 *Oct23\n")])

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
        for bad in ("xxs", "xxl", "medium", "3", "S M"):
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
        self.assert_one_line_changed(text, out, t.line, "\t(!)- send to board (RT) (s) Oct24 >Oct14 *Oct23\n")

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


class TestPlanToken(Base):
    def test_plan_is_not_the_date(self):
        t = self.task("draft report (KA) (m) Oct24 >Oct14 *Oct13")
        self.assertEqual((t.title, t.plan, t.start, t.end), ("draft report", planner.date(2026, 10, 14),
                                                            planner.date(2026, 10, 24), planner.date(2026, 10, 24)))
        self.assertEqual(t.reminders[0][0], "Oct13")

    def test_plan_alone_leaves_the_task_undated(self):
        t = self.task("call RT >Oct13")
        self.assertEqual((t.title, t.plan, t.end), ("call RT", planner.date(2026, 10, 13), None))

    def test_first_valid_only_and_bad_ones_stay_in_title(self):
        t = self.task("a >Oct13 >Oct14")
        self.assertEqual((t.plan, t.title, t.end), (planner.date(2026, 10, 13), "a >Oct14", None))   # never read as a date
        t = self.task("a >Feb30 b")
        self.assertEqual((t.plan, t.title), (None, "a >Feb30 b"))
        t = self.task("x->Oct13 y>Oct13")                       # needs a space (or the start) before >
        self.assertEqual((t.plan, t.end), (None, None))

    def test_resolves_like_a_date(self):
        self.assertEqual(self.task("a >Jan05").plan, planner.date(2027, 1, 5))
        self.assertEqual(self.task("a >Aug01").plan, planner.date(2026, 8, 1))


class TestSetPlan(EditBase):
    def test_add_move_clear(self):
        text = "@P\r\n\t- a (KA) Oct24 *Oct13  \r\n- b\n"
        out = planner.set_plan(text, 2, "Oct14", "a")
        self.assert_one_line_changed(text, out, 2, "\t- a (KA) Oct24 >Oct14 *Oct13  \r\n")
        out2 = planner.set_plan(out, 2, ">Oct16", "a")
        self.assert_one_line_changed(out, out2, 2, "\t- a (KA) Oct24 >Oct16 *Oct13  \r\n")
        self.assertEqual(planner.set_plan(out2, 2, "", "a"), text)
        self.assertEqual(planner.set_plan(text, 3, "Oct17", "b"), "@P\r\n\t- a (KA) Oct24 *Oct13  \r\n- b >Oct17\n")

    def test_other_edits_keep_the_order(self):                # initials, effort, date, plan, reminder
        text = "- a >Oct14 *Oct13\n"
        self.assertEqual(planner.set_date(text, 1, "Oct24"), "- a Oct24 >Oct14 *Oct13\n")
        self.assertEqual(planner.set_effort(text, 1, "m"), "- a (m) >Oct14 *Oct13\n")
        self.assertEqual(planner.add_assignees(text, 1, "KA"), "- a (KA) >Oct14 *Oct13\n")

    def test_example_line(self):
        text = read_example()
        t = self.find(planner.parse(text), "final layout")
        out = planner.set_plan(text, t.line, "Oct15", t.title)
        self.assert_one_line_changed(text, out, t.line, "\t- final layout (JS) Mar02--20 >Oct15\n")

    def test_refused(self):
        for value, title, text in [("Oct32", "a", "- a\n"), ("tomorrow", "a", "- a\n"), ("", "a", "- a\n"),
                                   ("Oct14", "stale", "- a\n"), ("Oct14", None, "@P\n")]:
            with self.subTest(value=value, title=title), self.assertRaises(planner.EditError):
                planner.set_plan(text, 1, value, title)


class TestPlanner(Base):
    def setUp(self):
        super().setUp()
        self.ps = planner.parse(read_example())

    def groups(self, ps, period):
        cols, planned, backlog, prios = planner.planner_groups(ps, period)
        return {c[0]: [t.title for _, t in c[5]] for c in cols if c[5]}, planned, backlog, prios

    def test_week_columns_planned_and_backlog(self):
        cols, planned, backlog, _ = planner.planner_groups(self.ps, ("week", 2026, 42))
        self.assertEqual([c[0] for c in cols], ["Mon 12", "Tue 13", "Wed 14", "Thu 15", "Fri 16", "Sat/Sun 17-18"])
        self.assertEqual([c[3] for c in cols], ["Oct12", "Oct13", "Oct14", "Oct15", "Oct16", "Oct17"])
        self.assertEqual(self.groups(self.ps, ("week", 2026, 42))[0], {"Mon 12": ["gather requirements"], "Wed 14": ["send to board"]})
        self.assertEqual([(p.name, [t.title for t in ts]) for p, ts in planned], [("HDC", ["gather requirements", "send to board"])])
        self.assertEqual(planner.effort_points(planned[0][1])[1], 2)      # (s) + (s), done ones count
        hdc = dict((p.name, items) for p, items in backlog)["HDC"]
        titles = [t.title for _, t in hdc]
        self.assertNotIn("send to board", titles)                         # planned this week
        self.assertNotIn("meet w. clients", titles)                       # done
        self.assertEqual(hdc[1], (1, self.find(self.ps, "complete powerpoint")))   # outline depth kept

    def test_weekend_and_other_weeks(self):
        ps = planner.parse("@P\n- sat >Oct17\n- sun >Oct18\n- next >Oct19\n")
        cols, _, backlog, _ = planner.planner_groups(ps, ("week", 2026, 42))
        self.assertEqual([t.title for _, t in cols[5][5]], ["sat", "sun"])
        self.assertEqual([t.title for _, t in backlog[0][1]], ["next"])   # planned for another week: still in the backlog
        self.assertEqual(self.groups(ps, ("week", 2026, 43))[0], {"Mon 19": ["next"]})

    def test_levels_roll_up(self):
        ps = planner.parse("@P\n- day >Oct14\n- week >wk43\n- month >Nov\n- season >T3\n- edge >wk44\n- open\n")
        self.assertEqual(self.groups(ps, ("month", 2026, 10))[0],
                         {"Oct 12-18": ["day"], "Oct 19-25": ["week"], "Oct 26-31": ["edge"]})
        self.assertEqual(self.groups(ps, ("month", 2026, 11))[0], {"Nov 1": ["edge"]})   # a week across two months: in both
        cols, planned, backlog, _ = planner.planner_groups(ps, ("month", 2026, 11))
        self.assertEqual([t.title for _, ts in planned for t in ts], ["edge", "month"])   # by start; >Nov: planned this month, no column
        self.assertEqual([t.title for _, items in backlog for _, t in items], ["day", "week", "season", "open"])
        self.assertEqual(self.groups(ps, ("season", 2026, 2))[0], {"Oct": ["day", "week"], "Nov": ["month"]})
        self.assertEqual(self.groups(ps, ("year", 2026, 0))[0], {"Fall Sep-Dec": ["day", "week", "month", "season", "edge"]})
        cols, *_ = planner.planner_groups(ps, ("year", 2026, 0))
        self.assertEqual([c[4] for c in cols], [False, True, True])      # Winter 2026 is past: >T1 means Winter 2027

    def test_month_columns_are_mon_sun_weeks(self):
        cols = planner.planner_columns("month", 2026, 11)
        self.assertEqual([(h, t) for h, _, _, t in cols][:2], [("Nov 1", "wk44"), ("Nov 2-8", "wk45")])
        self.assertEqual((cols[0][1], cols[0][2]), (planner.date(2026, 10, 26), planner.date(2026, 11, 1)))

    def test_priorities(self):
        ps = planner.parse("@P\n- a ^wk42\n!- b ^wk42 ^Oct\n- c ^wk43\n- d ^yr ^T3\n")
        for period, want in [(("week", 2026, 42), ["a", "b"]), (("month", 2026, 10), ["b"]),
                             (("season", 2026, 2), ["d"]), (("year", 2026, 0), ["d"])]:
            with self.subTest(period=period):
                self.assertEqual([t.title for _, t in planner.planner_groups(ps, period)[3]], want)
        self.assertEqual(planner.planner_star("week", 2026, 42), ("wk42", True))
        self.assertEqual(planner.planner_star("year", 2027, 0), ("yr", False))  # ^yr is always this year
        self.assertEqual(planner.planner_star("month", 2028, 1), ("Jan", False))

    def test_planner_from(self):
        self.assertEqual(planner.planner_from(None), ("week", 2026, 42))
        self.assertEqual(planner.planner_from({"kind": "season"}), ("season", 2026, 2))
        self.assertEqual(planner.planner_from({"kind": "year"}), ("year", 2026, 0))
        self.assertEqual(planner.planner_from({"kind": "week", "year": 2027, "index": 1}), ("week", 2027, 1))
        for bad in ({"kind": "day"}, {"kind": "week", "year": 2026, "index": 60}, {"kind": "month", "year": 2026, "index": 13},
                    {"kind": "year", "year": 2026, "index": 2}, {"kind": "week", "year": "2026", "index": 3}, 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                planner.planner_from(bad)
        self.assertEqual(planner.planner_step("week", 2026, 53, 1), ("week", 2027, 1))
        self.assertEqual(planner.planner_step("year", 2026, 0, -1), ("year", 2025, 0))

    def test_week_monday(self):
        self.assertEqual(planner.week_monday(), planner.date(2026, 10, 12))
        self.assertEqual(planner.week_monday({"year": 2027, "index": 1}), planner.date(2027, 1, 4))

    def test_to_data(self):
        w = planner.to_data(self.ps)["planner"]
        self.assertEqual((w["kind"], w["label"], w["current"], w["prev"]["label"], w["next"]["label"], w["column_kind"]),
                         ("week", "Oct 12-18", True, "Oct 5-11", "Oct 19-25", "day"))
        self.assertEqual([(c["head"], c["token"], c["today"], c["ok"]) for c in w["columns"]][:2],
                         [("Mon 12", "Oct12", True, True), ("Tue 13", "Oct13", False, True)])
        self.assertEqual((w["columns"][5]["start"], w["columns"][5]["end"]), ("2026-10-17", "2026-10-18"))
        t = w["columns"][2]["tasks"][0]
        self.assertEqual((t["plan_label"], t["plan_kind"], t["plan_token"], t["plan_end"]), ("Oct 14", "day", "Oct14", "2026-10-14"))
        self.assertEqual(w["star"], {"token": "wk42", "ok": True, "kind": "week", "start": "2026-10-12", "end": "2026-10-18"})
        self.assertEqual([(g["name"], g["points"]) for g in w["projects"]], [("HDC", 2)])
        self.assertEqual(w["backlog"][0]["tasks"][1]["depth"], 1)
        w = planner.to_data(self.ps, None, ("season", 2026, 2))["planner"]
        self.assertEqual((w["label"], w["now"]["label"], [c["head"] for c in w["columns"]]), ("Fall 2026", "Fall 2026", ["Sep", "Oct", "Nov", "Dec"]))

    def test_cli_view(self):
        out = "\n".join(planner.view_week(self.ps))
        self.assertIn("Week of Oct 12-18", out)
        self.assertIn("Wed 14\n    [ ] @HDC  send to board", out)
        self.assertIn("  @HDC   2 pts", out)


class TestPlanLevels(EditBase):
    def test_tokens(self):
        for text, want in [("a >wk45", ("week", "wk45", planner.date(2026, 11, 2), planner.date(2026, 11, 8))),
                           ("a >Nov", ("month", "Nov", planner.date(2026, 11, 1), planner.date(2026, 11, 30))),
                           ("a >T1", ("season", "T1", planner.date(2027, 1, 1), planner.date(2027, 4, 30))),
                           ("a >wk54 >Nov", ("month", "Nov", planner.date(2026, 11, 1), planner.date(2026, 11, 30)))]:
            with self.subTest(text=text):
                t = self.task(text)
                self.assertEqual((t.plan_kind, t.plan_token, t.plan, t.plan_end), want)
        self.assertEqual(self.task("a >wk54 >Nov").title, "a >wk54")
        self.assertEqual(self.task("a >Nov Oct24").end, planner.date(2026, 10, 24))    # >Nov is never the date
        self.assertEqual(planner.plan_label("season", planner.date(2027, 1, 1), planner.date(2027, 4, 30)), "Winter 2027")

    def test_priority_tokens(self):
        t = self.task("a ^wk42 ^Nov ^yr ^T4 b")
        self.assertEqual([(x[0], x[1]) for x in t.priorities], [("wk42", "week"), ("Nov", "month"), ("yr", "year")])
        self.assertEqual(t.title, "a ^T4 b")
        self.assertEqual(self.task("x^Nov").priorities, [])

    def test_set_plan_any_level(self):
        self.assertEqual(planner.set_plan("- a (KA) Oct24 ^wk42 *daily\n", 1, "Nov"), "- a (KA) Oct24 >Nov ^wk42 *daily\n")
        self.assertEqual(planner.set_plan("- a >Nov\n", 1, ">wk45"), "- a >wk45\n")
        self.assertEqual(planner.set_plan("- a >T3\n", 1, ""), "- a\n")
        for bad in ("wk54", "Q1", "Fall"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_plan("- a\n", 1, bad)

    def test_set_priority(self):
        self.assertEqual(planner.set_priority("- a >Nov *daily\n", 1, "wk42"), "- a >Nov ^wk42 *daily\n")
        self.assertEqual(planner.set_priority("- a ^wk42\n", 1, "^wk42"), "- a ^wk42\n")       # already
        self.assertEqual(planner.set_priority("- a ^wk42 ^Nov\r\n", 1, "-wk42"), "- a ^Nov\r\n")
        self.assertEqual(planner.set_priority("- a\n", 1, "-wk42"), "- a\n")
        self.assertEqual(planner.set_priority("- a\n", 1, "yr"), "- a ^yr\n")
        for bad in ("wk54", "Q1", "-x"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_priority("- a\n", 1, bad)

    def test_other_edits_go_before_plan_and_priorities(self):
        self.assertEqual(planner.set_date("- a ^wk42\n", 1, "Oct24"), "- a Oct24 ^wk42\n")
        self.assertEqual(planner.add_assignees("- a >Nov ^wk42\n", 1, "KA"), "- a (KA) >Nov ^wk42\n")
        self.assertEqual(planner.set_effort("- a ^yr\n", 1, "m"), "- a (m) ^yr\n")


class TestSetText(EditBase):
    def test_replaces_only_the_text_after_the_dash(self):
        text = read_example()
        t = self.find(planner.parse(text), "complete powerpoint")
        self.assertEqual(t.text, "complete powerpoint (JS) (m) Oct20--23 *Oct19")
        out = planner.set_text(text, t.line, "  finish slides (JS, KA) (l) Oct21--23 *Oct19 ", t.title)
        self.assert_one_line_changed(text, out, t.line, "\t~- finish slides (JS, KA) (l) Oct21--23 *Oct19\n")
        n = self.find(planner.parse(out), "finish slides")
        self.assertEqual((n.assignees, n.effort, n.parent.title, [c.title for c in n.children]),
                         (["JS", "KA"], "l", "finish proposal", ["review with KA"]))

    def test_keeps_indent_mark_trailing_space_and_crlf(self):
        text = "@P\r\n- a\r\n    !-   b (KA)  \t\r\n- c"
        self.assertEqual(planner.set_text(text, 3, "new b", "b"), "@P\r\n- a\r\n    !-   new b  \t\r\n- c")
        self.assertEqual(planner.set_text(text, 4, "d", "c"), "@P\r\n- a\r\n    !-   b (KA)  \t\r\n- d")

    def test_in_task_data(self):
        d = planner.to_data(planner.parse("@P\n- a (KA) Oct24\n"))
        self.assertEqual(d["projects"][0]["projects"][0]["tasks"][0]["text"], "a (KA) Oct24")

    def test_refused(self):
        text = "@P\n-a\n- b\n"
        for line, value, title in [(3, "", "b"), (3, "two\nlines", "b"), (3, "x", "stale"), (1, "x", None),
                                   (2, "- x", "a")]:          # "-- x" would turn the task into a note
            with self.subTest(value=value, title=title), self.assertRaises(planner.EditError):
                planner.set_text(text, line, value, title)


class TestAddWithFields(EditBase):
    def test_task_and_subtask_with_fields(self):
        text = "@P\n- a\n\t- b\n\n@Q\n- c\n"
        out = planner.add_with_fields("task", text, 1, {"title": "draft report", "who": "KA, RT", "effort": "M", "date": "Oct24"}, "P")
        self.assertEqual(out, "@P\n- a\n\t- b\n- draft report (KA, RT) (m) Oct24\n\n@Q\n- c\n")
        out = planner.add_with_fields("subtask", text, 2, {"title": "x", "date": "~T1", "who": "", "effort": None}, "a")
        self.assertEqual(out, "@P\n- a\n\t- b\n\t- x ~T1\n\n@Q\n- c\n")
        out = planner.add_with_fields("task", "@P", 1, {"title": "first", "effort": "s"}, "P")   # file with no final newline
        self.assertEqual(out, "@P\n- first (s)")

    def test_fields_override_tokens_in_the_title(self):
        out = planner.add_with_fields("task", "@P\n", 1, {"title": "y (JS) Oct20", "who": "KA", "date": "Oct24"}, "P")
        self.assertEqual(out, "@P\n- y (KA) Oct24\n")

    def test_refused_as_a_whole(self):
        for fields in ({"title": "x", "date": "Oct32"}, {"title": "x", "effort": "huge"}, {"title": "x", "who": "ka"},
                       {"title": "", "who": "KA"}, {"who": "KA"}, {"title": "x", "date": 5}, "nope"):
            with self.subTest(fields=fields), self.assertRaises(planner.EditError):
                planner.add_with_fields("task", "@P\n- a\n", 1, fields, "P")


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


class TestAddTask(EditBase):
    def test_goes_after_the_projects_last_line(self):
        text = read_example()
        p = next(p for p in planner.parse(text) if p.name == "HDC")
        out = planner.add_task(text, p.line, "book venue (KA) Nov03", "HDC")
        a, b = text.splitlines(keepends=True), out.splitlines(keepends=True)
        new = self.find(planner.parse(out), "book venue")
        self.assertEqual(b[new.line - 1], "- book venue (KA) Nov03\n")
        self.assertEqual(a, b[:new.line - 1] + b[new.line:])
        self.assertEqual((new.parent, new.project.name, new.project.line), (None, "HDC", p.line))
        self.assertEqual(new.project.tasks[-1], new)

    def test_after_subtasks_and_notes_before_blank_and_next_project(self):
        self.assertEqual(planner.add_task("@P\n- a\n\t- b\n\t-- n\n\n@Q\n- c\n", 1, "x", "P"),
                         "@P\n- a\n\t- b\n\t-- n\n- x\n\n@Q\n- c\n")
        self.assertEqual(planner.add_task("@P\n- a\nWinter\n- b\n", 1, "x"), "@P\n- a\n- x\nWinter\n- b\n")

    def test_empty_project_and_indent(self):
        self.assertEqual(planner.add_task("@P\n\n@Q\n", 1, "x", "P"), "@P\n- x\n\n@Q\n")
        self.assertEqual(planner.add_task("@P\n    - a\nFall\n", 1, "x"), "@P\n    - a\n    - x\nFall\n")

    def test_no_project_and_line_endings(self):
        self.assertEqual(planner.add_task("- a\n@Q", 1, "x", "(no project)"), "- a\n- x\n@Q")
        self.assertEqual(planner.add_task("Win\n@P\r\n- a", 2, "x"), "Win\n@P\r\n- a\r\n- x")
        self.assertEqual(planner.add_task("@P\r\n- a\r\n", 1, "x"), "@P\r\n- a\r\n- x\r\n")

    def test_project_lines_in_data(self):
        d = planner.to_data(planner.parse("Fall\n@P\n- a\n@Q\n"))
        self.assertEqual(d["targets"], [{"name": "P", "line": 2, "path": None, "folder": None, "section": "Fall"},
                                        {"name": "Q", "line": 4, "path": None, "folder": None, "section": "Fall"}])
        self.assertEqual(d["projects"][0]["projects"][0]["line"], 2)

    def test_line_0_is_the_files_own_project(self):
        self.assertEqual(planner.add_task("", 0, "a", "HDC"), "- a\n")
        self.assertEqual(planner.add_task("@Stream\r\n- b\r\n", 0, "a", "HDC"), "- a\r\n@Stream\r\n- b\r\n")
        self.assertEqual(planner.add_task("- x\n\n@Stream\n- b\n", 0, "a", "HDC"), "- x\n- a\n\n@Stream\n- b\n")
        self.assertEqual(planner.add_task("Fall\n- x\n", 2, "a", "HDC"), "Fall\n- x\n- a\n")   # its own project: any name

    def test_rejects_bad_and_stale(self):
        for bad in ("", "  ", "a\nb"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.add_task("@P\n- a\n", 1, bad)
        for line, title in ((2, None), (1, "Q"), (9, None)):
            with self.subTest(line=line), self.assertRaises(planner.EditError):
                planner.add_task("@P\n- a\n", line, "x", title)


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
            page = r.read()
        self.assertIn(b'src="app.js"', page)
        self.assertIn(b'href="app.css"', page)
        for path, ctype, inside in (("/app.js", "text/javascript", b"/api/edit"), ("/app.css", "text/css", b"--fz")):
            with urllib.request.urlopen(self.url + path) as r:
                self.assertTrue(r.headers["Content-Type"].startswith(ctype))
                self.assertEqual(r.headers["Cache-Control"], "no-cache")
                self.assertIn(inside, r.read())

    def test_no_portfolio(self):
        with urllib.request.urlopen(self.url + "/api/portfolio") as r:
            self.assertEqual(json.loads(r.read()), {"name": None})
        self.assertEqual(self.post("/api/portfolio", {"op": "project", "name": "X"})[0], 409)
        self.assertEqual(self.post("/api/parse", {"all": True})[0], 409)

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

    def test_edit_add_task(self):
        code, d = self.post("/api/edit", {"text": "@P\n- a\n", "line": 1, "op": "task", "value": "b (KA)", "title": "P"})
        self.assertEqual((code, d["text"]), (200, "@P\n- a\n- b (KA)\n"))
        self.assertEqual(d["data"]["people"][0]["name"], "KA")

    def test_edit_text(self):
        code, d = self.post("/api/edit", {"text": "@P\n- a (KA)\n", "line": 2, "op": "text", "value": "b (RT) (s)", "title": "a"})
        self.assertEqual((code, d["text"]), (200, "@P\n- b (RT) (s)\n"))
        self.assertEqual(d["data"]["people"][0]["name"], "RT")

    def test_edit_task_with_fields(self):
        code, d = self.post("/api/edit", {"text": "@P\n- a\n", "line": 1, "op": "task", "title": "P",
                                          "value": {"title": "b", "who": "RT", "effort": "s", "date": "Oct24"}})
        self.assertEqual((code, d["text"]), (200, "@P\n- a\n- b (RT) (s) Oct24\n"))
        code, d = self.post("/api/edit", {"text": "@P\n- a\n", "line": 1, "op": "task", "title": "P",
                                          "value": {"title": "b", "date": "soon"}})
        self.assertEqual(code, 409)
        code, d = self.post("/api/edit", {"text": "@P\n- a\n", "line": 2, "op": "date", "title": "a", "value": {"x": 1}})
        self.assertEqual(code, 409)

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

    def test_parse_and_edit_with_planner(self):
        week = {"kind": "week", "year": 2026, "index": 43}
        code, d = self.post("/api/parse", {"text": read_example(), "today": "2026-10-12", "planner": week})
        self.assertEqual((code, d["planner"]["label"]), (200, "Oct 19-25"))
        code, d = self.post("/api/edit", {"text": "@P\n- a\n", "line": 2, "op": "plan", "value": "Oct20",
                                          "title": "a", "today": "2026-10-12", "planner": week})
        self.assertEqual((code, d["text"]), (200, "@P\n- a >Oct20\n"))
        self.assertEqual(d["data"]["planner"]["columns"][1]["tasks"][0]["title"], "a")
        code, d = self.post("/api/edit", {"text": "@P\n- a\n", "line": 2, "op": "priority", "value": "wk43",
                                          "title": "a", "today": "2026-10-12", "planner": week})
        self.assertEqual(d["data"]["planner"]["priorities"][0]["title"], "a")
        code, d = self.post("/api/parse", {"text": "", "today": "2026-10-12", "planner": {"kind": "month"}})
        self.assertEqual(d["planner"]["label"], "Oct 2026")
        self.assertEqual(self.post("/api/parse", {"text": "", "planner": {"kind": "week", "year": 2026}})[0], 400)
        self.assertEqual(self.post("/api/parse", {"text": "", "planner": {"kind": "decade"}})[0], 400)

    def test_edit_bad_op_or_value_is_409(self):
        for extra in ({"op": "explode", "value": ""}, {"op": "date", "value": 5}):
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


class TestServerPickedFile(Base):
    """No file on the command line: the page browses a folder and opens one notes file there."""
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.dir.name)
        os.mkdir(os.path.join(self.root, "work"))
        for name, data in [("work/plan.txt", b"@P\r\n- a\r\n"), ("notes.md", b"- b\n"), ("photo.png", b"x"), (".hidden.txt", b"")]:
            with open(os.path.join(self.root, name), "wb") as f:
                f.write(data)
        self.server = planner.make_server(0, None, browse_root=self.root)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.dir.cleanup()
        super().tearDown()

    post, send = TestServer.post, TestServer.send

    def get(self, path):
        return self.send(urllib.request.Request(self.url + path))

    def test_browse_lists_folders_and_notes_files(self):
        code, d = self.get("/api/browse?dir=" + urllib.parse.quote(self.root))
        self.assertEqual(code, 200)
        self.assertEqual([(e["name"], e["kind"]) for e in d["entries"]], [("work", "dir"), ("notes.md", "file")])
        self.assertIsNone(d["parent"])
        code, d = self.get("/api/browse?dir=" + urllib.parse.quote(os.path.join(self.root, "work")))
        self.assertEqual((d["parent"], [e["name"] for e in d["entries"]]), (self.root, ["plan.txt"]))

    def test_browse_and_open_stay_inside_the_root(self):
        self.assertEqual(self.get("/api/browse?dir=" + urllib.parse.quote(os.path.dirname(self.root)))[0], 403)
        self.assertEqual(self.get("/api/browse?dir=" + urllib.parse.quote(os.path.join(self.root, "..")))[0], 403)
        for path in (os.path.join(self.root, "photo.png"), os.path.join(os.path.dirname(self.root), "x.txt"), 5):
            with self.subTest(path=path):
                self.assertEqual(self.post("/api/open", {"path": path})[0], 403)
        self.assertEqual(self.post("/api/open", {"path": os.path.join(self.root, "gone.txt")})[0], 404)
        req = urllib.request.Request(self.url + "/api/browse", headers={"Origin": "https://evil.example"})
        self.assertEqual(self.send(req)[0], 403)

    def test_open_save_conflict_close(self):
        plan = os.path.join(self.root, "work", "plan.txt")
        code, d = self.post("/api/open", {"path": plan})
        self.assertEqual((code, d["name"], d["path"], d["text"], d["picked"]), (200, "plan.txt", plan, "@P\r\n- a\r\n", True))
        code, d2 = self.post("/api/file", {"path": plan, "text": "@P\n- a\n- c\n", "version": d["version"]})
        self.assertEqual(code, 200)
        with open(plan, "rb") as f:
            self.assertEqual(f.read(), b"@P\r\n- a\r\n- c\r\n")         # CRLF kept, like file mode
        code, c = self.post("/api/file", {"path": plan, "text": "x", "version": d["version"]})   # stale version
        self.assertEqual((code, c["conflict"]), (409, True))
        self.assertEqual(self.get("/api/file?path=" + urllib.parse.quote(plan))[1]["text"], "@P\r\n- a\r\n- c\r\n")
        self.assertEqual(self.get("/api/file")[1], {"name": None})          # no path: no command-line file
        self.assertEqual(self.post("/api/close", {"path": plan})[1], {"closed": True})
        code, c = self.post("/api/file", {"path": plan, "text": "x", "version": d2["version"]})
        self.assertEqual((code, c.get("notOpen")), (409, True))               # closed: can't be written any more
        self.assertEqual(self.get("/api/file?path=" + urllib.parse.quote(plan))[0], 409)
        with open(plan, "rb") as f:
            self.assertEqual(f.read(), b"@P\r\n- a\r\n- c\r\n")

    def test_several_files_open_at_once(self):
        plan, notes = os.path.join(self.root, "work", "plan.txt"), os.path.join(self.root, "notes.md")
        a, b = self.post("/api/open", {"path": plan})[1], self.post("/api/open", {"path": notes})[1]
        self.assertEqual(self.post("/api/open", {"path": plan})[0], 200)     # opening an open file again is fine
        self.assertEqual(self.post("/api/file", {"path": plan, "text": "A", "version": a["version"]})[0], 200)
        self.assertEqual(self.post("/api/file", {"path": notes, "text": "B", "version": b["version"]})[0], 200)
        for path, want in ((plan, b"A"), (notes, b"B")):
            with open(path, "rb") as f:
                self.assertEqual(f.read(), want)
        self.post("/api/close", {"path": plan})
        self.assertEqual(self.post("/api/file", {"path": notes, "text": "C", "version": planner.file_version(b"B")})[0], 200)
        self.assertEqual(self.post("/api/file", {"path": plan, "text": "x", "version": planner.file_version(b"A")})[0], 409)

    def test_unopened_files_cannot_be_read_or_written(self):
        plan = os.path.join(self.root, "work", "plan.txt")             # e.g. after a server restart: open it first
        for path in (plan, None, 5, os.path.join(self.root, "notes.md")):
            with self.subTest(path=path):
                code, d = self.post("/api/file", {"path": path, "text": "x", "version": None})
                self.assertEqual((code, d.get("notOpen")), (409, True))
        self.assertEqual(self.get("/api/file?path=" + urllib.parse.quote(plan))[0], 409)
        with open(plan, "rb") as f:
            self.assertEqual(f.read(), b"@P\r\n- a\r\n")

    def test_create_new_file(self):
        new = os.path.join(self.root, "work", "q4.txt")
        code, d = self.post("/api/open", {"path": new, "create": True})
        self.assertEqual((code, d["name"], d["text"], d["picked"]), (200, "q4.txt", "", True))
        self.assertTrue(os.path.isfile(new))
        self.assertEqual(self.post("/api/file", {"path": new, "text": "@Q4\n", "version": d["version"]})[0], 200)
        self.assertEqual(self.post("/api/open", {"path": new, "create": True})[0], 409)      # already exists
        for bad in (os.path.join(self.root, "nofolder", "x.txt"), os.path.join(self.root, "x.png"),
                    os.path.join(os.path.dirname(self.root), "x.txt")):
            with self.subTest(path=bad):
                self.assertEqual(self.post("/api/open", {"path": bad, "create": True})[0], 403)
                self.assertFalse(os.path.exists(bad))

    def test_command_line_file_cannot_be_switched(self):
        with tempfile.TemporaryDirectory() as other:
            notes = os.path.join(other, "plan.txt")
            open(notes, "w").close()
            server = planner.make_server(0, notes, browse_root=self.root)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}"
                for req in (urllib.request.Request(url + "/api/browse"),
                            urllib.request.Request(url + "/api/open", json.dumps({"path": os.path.join(self.root, "notes.md")}).encode(),
                                                   {"Content-Type": "application/json"})):
                    self.assertEqual(self.send(req)[0], 409)
                self.assertFalse(self.send(urllib.request.Request(url + "/api/file"))[1]["picked"])
            finally:
                server.shutdown(); server.server_close()


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
            ((EXAMPLE, "timline"), "is not a file, a portfolio folder or a view"),
            (("no-such-file.txt",), "is not a file, a portfolio folder or a view"),
            ((EXAMPLE, EXAMPLE), "only one notes file"),
            ((EXAMPLE, "--today"), "--today needs a value"),
            ((EXAMPLE, "--today", "Feb30"), "bad --today value"),
            ((EXAMPLE, "--today", "soon"), "bad --today value"),
            (("--serve", "--port"), "--port needs a value"),
            (("--serve", "--port", "abc"), "bad --port value"),
            (("--serve", "--port", "70000"), "bad --port value"),
            (("--serve", EXAMPLE, "timeline"), "at most one notes file"),
            (("--import", EXAMPLE), "use --import"),
            (("--import", "no-such-file.txt", "somewhere"), "use --import"),
            (("--import", EXAMPLE, os.path.join(HERE, "no-such-dir", "folio")), "parent folder doesn't exist"),
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

    def test_portfolio_folder(self):
        out = self.run_cli(PORTFOLIO, "--today", "2026-10-12")
        for heading in ("PROJECTS", "TIMELINE", "PEOPLE", "UPCOMING", "WEEK"):
            self.assertIn(heading, out)
        self.assertIn("site visit prep   Sep 30   OVERDUE", out)
        self.assertIn("Mon 12\n    [x] @HDC  gather requirements (RT)\n    [ ] @HDC  inbox zero  (habit)", out)
        with tempfile.TemporaryDirectory() as d:
            for rel, text in (("A/backlog.kf", "- own\n@Stream\n- b\n"), ("A/habits.kf", "- walk *weekly Sat, Sun\n")):
                os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
                with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
                    f.write(text)
            out = self.run_cli(d, "projects", "week", "--today", "2026-10-12")
            self.assertIn("@A   0/1 done", out)
            self.assertIn("@A · Stream   0/1 done", out)                  # a sub-group, under its project's name
            self.assertIn("Sat/Sun 17-18\n    [ ] @A  walk  (habit, Sat)\n    [ ] @A  walk  (habit, Sun)", out)
            self.assertIn("No projects or tasks found.", self.run_cli(os.path.join(d, "A")))   # a project folder isn't a portfolio

    def test_import(self):
        with tempfile.TemporaryDirectory() as d:
            folio = os.path.join(d, "folio")
            self.assertIn("HDC, MDM, OPS", self.run_cli("--import", EXAMPLE, folio, "--split"))
            self.assertIn("already has a backlog", self.run_cli("--import", EXAMPLE, folio, "--split", code=1))
            self.assertIn("example", self.run_cli("--import", EXAMPLE, folio))
            with open(os.path.join(folio, "example", "backlog.kf"), encoding="utf-8") as f:
                self.assertEqual(f.read(), read_example())


# ---------- notable, delete, archive ----------

class TestNotable(EditBase):
    def test_prefix(self):
        ps = planner.parse("@P\n(!)- a Oct20\n(!)~- b\n(!)!- c\n- d\n\t(!)- e\n")
        got = [(t.title, t.status, t.notable, t.level) for t in ps[0].all_tasks()]
        self.assertEqual(got, [("a", "open", True, 0), ("b", "doing", True, 0), ("c", "done", True, 0),
                               ("d", "open", False, 0), ("e", "open", True, 1)])
        self.assertEqual(ps[0].tasks[0].end, date(2026, 10, 20))
        self.assertTrue(planner.to_data(ps)["projects"][0]["projects"][0]["tasks"][0]["notable"])

    def test_set_notable(self):
        text = "@P\n\t~- a (KA)\r\n"
        on = planner.set_notable(text, 2, "on", "a")
        self.assertEqual(on, "@P\n\t(!)~- a (KA)\r\n")
        self.assertEqual(planner.set_notable(on, 2, "", "a"), text)
        self.assertEqual(planner.set_notable(text, 2, "off", "a"), text)
        for bad in ("yes", "1"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_notable(text, 2, bad, "a")

    def test_status_keeps_the_circle(self):
        self.assertEqual(planner.set_status("(!)- a\n", 1, "done"), "(!)!- a\n")
        self.assertEqual(planner.set_status("(!)!- a\n", 1, "open"), "(!)- a\n")
        self.assertEqual(planner.set_text("(!)- a\n", 1, "b (KA)"), "(!)- b (KA)\n")

    def test_subtasks_and_tasks_under_a_circled_task(self):
        self.assertEqual(planner.add_subtask("@P\n(!)- a\n- b\n", 2, "x"), "@P\n(!)- a\n\t- x\n- b\n")
        self.assertEqual(planner.add_task("@P\n(!)- a\n\nNext\n", 1, "x", "P"), "@P\n(!)- a\n- x\n\nNext\n")


class TestDelete(EditBase):
    def test_removes_the_task_its_subtasks_and_notes(self):
        text = "@P\n- a\n\t-- note\n\t- a1\n\t\t- a2\n\n\t- a3\n- b\n"
        self.assertEqual(planner.delete_task(text, 2, "", "a"), "@P\n- b\n")
        self.assertEqual(planner.delete_task(text, 4, "", "a1"), "@P\n- a\n\t-- note\n\n\t- a3\n- b\n")
        self.assertEqual(planner.delete_task(text, 8, "", "b"), "@P\n- a\n\t-- note\n\t- a1\n\t\t- a2\n\n\t- a3\n")

    def test_keeps_blank_lines_and_what_follows(self):
        self.assertEqual(planner.delete_task("@P\r\n- a\r\n\r\n@Q\r\n- b", 2), "@P\r\n\r\n@Q\r\n- b")
        self.assertEqual(planner.delete_task("@P\n- a\n- b", 3), "@P\n- a\n")
        self.assertEqual(planner.delete_task("Fall\n- a\nWinter\n- b\n", 2), "Fall\nWinter\n- b\n")

    def test_stale_is_refused(self):
        with self.assertRaises(planner.EditError):
            planner.delete_task("@P\n- a\n", 2, "", "b")
        with self.assertRaises(planner.EditError):
            planner.delete_task("@P\n- a\n", 1, "")


class TestArchive(EditBase):
    TEXT = "Fall\n- own (KA)\n@A\n- a Oct20\n\t!- a1\n\t\t-- n\n\t- a2\n\n!- b\n\t!- b1\n@B\n(!)!- c\n- d\n\t!- d1\n"

    def test_take_task(self):
        rest, block, group = planner.take_task(self.TEXT, 5, "a1")
        self.assertEqual(block, ["!- a1\n", "\t-- n\n"])
        self.assertEqual(group, "A")
        self.assertEqual(rest, self.TEXT.replace("\t!- a1\n\t\t-- n\n", ""))
        self.assertIsNone(planner.take_task(self.TEXT, 2, "own")[2])

    def test_take_done_takes_finished_tasks_only(self):
        rest, moved = planner.take_done(self.TEXT)
        self.assertEqual(moved, [("A", ["!- b\n", "\t!- b1\n"]), ("B", ["(!)!- c\n"])])   # a1, d1: their parents aren't done
        self.assertEqual(rest, "Fall\n- own (KA)\n@A\n- a Oct20\n\t!- a1\n\t\t-- n\n\t- a2\n\n@B\n- d\n\t!- d1\n")
        rest, moved = planner.take_done(self.TEXT, 11)                  # only @B
        self.assertEqual([g for g, _ in moved], ["B"])
        with self.assertRaises(planner.EditError):
            planner.take_done("- a\n")

    def test_put_in_archive(self):
        self.assertEqual(planner.put_in_archive("", "A", ["- x\n"]), "@A\n- x\n")
        self.assertEqual(planner.put_in_archive("", None, ["- x\n"]), "- x\n")
        old = "- own\n\n@A\n- a\n\n@B\n- b"
        self.assertEqual(planner.put_in_archive(old, "A", ["- x\n"]), "- own\n\n@A\n- a\n- x\n\n@B\n- b\n")
        self.assertEqual(planner.put_in_archive(old, "B", ["- x\n"]), "- own\n\n@A\n- a\n\n@B\n- b\n- x\n")
        self.assertEqual(planner.put_in_archive(old, None, ["- x\n"]), "- own\n- x\n\n@A\n- a\n\n@B\n- b\n")
        self.assertEqual(planner.put_in_archive(old, "C", ["- x\n"]), "- own\n\n@A\n- a\n\n@B\n- b\n\n@C\n- x\n")

    def test_archive_dates_fall_in_their_year(self):
        planner.TODAY = planner.archive_today(2025)
        t = planner.parse("- a Dec15--Jan10\n- b Jan03\n- c ~Q4\n")[0].tasks
        self.assertEqual([(x.start, x.end) for x in t], [(date(2025, 12, 15), date(2026, 1, 10)),
                                                         (date(2025, 1, 3), date(2025, 1, 3)),
                                                         (date(2025, 10, 1), date(2025, 12, 31))])


# ---------- habits ----------

class TestHabits(EditBase):
    today = "2026-11-06"                                               # a Friday
    TEXT = "- stretch *daily\n- gym (KA) *weekly Mon, Wed, Fri\n\t-- with RT\n- rent *monthly 1st\n- standup *weekdays\n"

    def test_frequencies(self):
        ts = planner.parse(self.TEXT)[0].tasks
        self.assertEqual([[s for s, _ in t.reminders] for t in ts], [["daily"], ["weekly Mon, Wed, Fri"], ["monthly 1st"], ["weekdays"]])
        a, b = planner.date(2026, 11, 2), planner.date(2026, 11, 8)
        days = {t.title: [d.day for d in due] for _, t, _, due, _ in planner.habit_rows(planner.parse(self.TEXT), a, b)}
        self.assertEqual(days, {"stretch": [2, 3, 4, 5, 6, 7, 8], "gym": [2, 4, 6], "rent": [], "standup": [2, 3, 4, 5, 6]})
        self.assertEqual(planner.next_reminder("weekly Mon, Wed"), planner.date(2026, 11, 9))
        self.assertEqual(planner.next_reminder("weekdays"), planner.date(2026, 11, 6))
        self.assertEqual(planner.every_label("weekly mon, wed"), "Mon, Wed")
        self.assertEqual(self.task("call *weekly Fri, then").title, "call , then")   # only day names join the list

    def test_tick_and_untick(self):
        a = planner.tick_habit(self.TEXT, 1, "Nov06", "stretch")
        self.assertEqual(a, self.TEXT.replace("- stretch *daily\n", "- stretch *daily\n\t-- done Nov06\n"))
        b = planner.tick_habit(a, 1, "Nov05")
        self.assertIn("\t-- done Nov06 Nov05\n", b)
        self.assertEqual(planner.parse(b)[0].tasks[0].log(), [planner.date(2026, 11, 5), planner.date(2026, 11, 6)])
        self.assertEqual(planner.tick_habit(b, 1, "Nov05"), b)                    # already
        self.assertEqual(planner.tick_habit(planner.tick_habit(b, 1, "-Nov06"), 1, "-Nov05"), self.TEXT)
        self.assertEqual(planner.tick_habit(self.TEXT, 2, "-Nov04"), self.TEXT)
        c = planner.tick_habit(self.TEXT, 2, "Nov04", "gym")                   # its own log goes first; other notes stay
        self.assertIn("- gym (KA) *weekly Mon, Wed, Fri\n\t-- done Nov04\n\t-- with RT\n", c)

    def test_log_reads_back_to_the_latest_day_so_far(self):
        t = planner.parse("- x *daily\n\t-- done Nov06 Nov07 Jan02\n")[0].tasks[0]
        self.assertEqual(t.log(), [planner.date(2025, 11, 7), planner.date(2026, 1, 2), planner.date(2026, 11, 6)])
        self.assertEqual(t.notes, ["done Nov06 Nov07 Jan02"])
        self.assertEqual(planner.to_data(planner.parse("- x *daily\n\t-- done Nov06\n\t-- done with Lisa\n"))
                         ["projects"][0]["projects"][0]["tasks"][0]["notes"], ["done with Lisa"])   # not a log: a note

    def test_tick_refusals(self):
        for bad in ("Feb30", "tomorrow", "Nov"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.tick_habit(self.TEXT, 1, bad)
        out = planner.tick_habit(self.TEXT, 1, "Nov07")                      # the latest Nov 7 so far: last year's
        self.assertEqual(planner.parse(out)[0].tasks[0].log(), [planner.date(2025, 11, 7)])

    def test_set_every(self):
        self.assertEqual(planner.set_every(self.TEXT, 1, "weekly Tue, Thu").splitlines()[0], "- stretch *weekly Tue, Thu")
        self.assertEqual(planner.set_every("- x (KA)\r\n", 1, "*weekdays"), "- x (KA) *weekdays\r\n")
        self.assertEqual(planner.set_every("- x *monthly 1st *Oct13\n", 1, ""), "- x *Oct13\n")
        self.assertEqual(planner.set_every("- x\n", 1, ""), "- x\n")
        for bad in ("Oct13", "weekly Fry", "hourly", "monthly 40th"):
            with self.subTest(bad=bad), self.assertRaises(planner.EditError):
                planner.set_every("- x\n", 1, bad)
        out = planner.add_with_fields("task", "@P\n", 1, {"title": "read", "who": "KA", "every": "daily"}, "P")
        self.assertEqual(out, "@P\n- read (KA) *daily\n")

    def test_planner_habits(self):
        d = planner.to_data([], None, ("week", 2026, 45), planner.parse(self.TEXT.replace("- stretch *daily\n", "- stretch *daily\n\t-- done Nov02\n")))
        h = {x["title"]: x for x in d["planner"]["habits"]}
        self.assertEqual(sorted(h), ["gym", "rent", "standup", "stretch"])
        self.assertEqual((h["gym"]["due"], h["gym"]["every_label"]), (["2026-11-02", "2026-11-04", "2026-11-06"], "Mon, Wed, Fri"))
        self.assertEqual(h["stretch"]["done"], ["2026-11-02"])
        page = planner.page_data("- stretch *daily\n- no frequency yet\n!- retired *daily\n", "HDC", None, ("week", 2026, 45), habits=True)
        self.assertEqual([(x["title"], x["every"]) for x in page["planner"]["habits"]], [("stretch", ["daily"]), ("no frequency yet", [])])

    def test_archive_last_years_log(self):
        planner.set_today("2027-01-05")
        rest, moved = planner.take_habit_log("- stretch *daily\n\t-- done Dec30 Dec31 Jan02\n- gym *weekly Mon\n\t-- done Dec28\n", 2026)
        self.assertEqual(rest, "- stretch *daily\n\t-- done Jan02\n- gym *weekly Mon\n")
        self.assertEqual(moved, [("Habits", ["- stretch *daily\n", "\t-- done Dec30 Dec31\n"]), ("Habits", ["- gym *weekly Mon\n", "\t-- done Dec28\n"])])
        self.assertEqual(planner.to_data([], habits=planner.parse("- x *daily\n\t-- done Dec30\n"))["planner"]["log_years"], [2026])
        with self.assertRaises(planner.EditError):
            planner.take_habit_log(rest, 2025)


# ---------- the portfolio ----------

class TestPortfolio(Base):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()
        super().tearDown()

    def write(self, rel, text=""):
        full = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def test_parse_names_the_implicit_project(self):
        ps = planner.parse("- a\n@Stream\n- b", "HDC")
        self.assertEqual([p.name for p in ps], ["HDC", "Stream"])
        self.assertEqual(planner.parse("- a")[0].name, "(no project)")

    def test_kinds(self):
        for rel, kind in [("HDC", "project"), ("HDC/backlog.kf", "backlog"), ("HDC/quicknote.kf", "quicknote"),
                          ("HDC/habits.kf", "habits"), ("HDC/notes/Client", "section"), ("HDC/notes/a.md", "page"),
                          ("HDC/notes/Client/b.kf", "page"), ("HDC/notes/c.txt", "page"), ("HDC/archive/2026.kf", "archive"),
                          ("HDC/archive/26.kf", None), ("HDC/other.kf", None), ("HDC/notes/a/b/c.kf", None),
                          ("HDC/notes/x.png", "section"), ("HDC/notes/Client/x.png", None), (".trash", None), ("HDC/.git", None), ("HDC/../x", None),
                          ("", None), ("HDC//backlog.kf", None), (None, None), (5, None)]:
            with self.subTest(rel=rel):
                self.assertEqual(planner.portfolio_kind(rel), kind)

    def test_paths_stay_inside(self):
        self.assertEqual(planner.portfolio_path(self.root, "HDC/backlog.kf"), os.path.join(self.root, "HDC", "backlog.kf"))
        for rel in ("../x", "HDC/../../x", "/etc", "HDC\\..\\x", ".trash/HDC", "a\0b"):
            with self.subTest(rel=rel), self.assertRaises(planner.PortfolioError):
                planner.portfolio_path(self.root, rel)
        with tempfile.TemporaryDirectory() as out:
            os.symlink(out, os.path.join(self.root, "Link"))
            with self.assertRaises(planner.PortfolioError):
                planner.portfolio_path(self.root, "Link/backlog.kf")

    def test_tree(self):
        self.write("HDC/backlog.kf", "- a")
        self.write("HDC/notes/Kickoff.md")
        self.write("HDC/notes/Client/Req.kf")
        self.write("HDC/notes/Client/photo.png")
        self.write("HDC/notes/.hidden.kf")
        self.write("HDC/archive/2025.kf", "- a")
        self.write("HDC/archive/2026.kf", "- b")
        self.write("HDC/archive/2024.kf")                              # empty: not listed
        self.write("HDC/archive/old.kf")
        os.mkdir(os.path.join(self.root, "MDM"))
        os.mkdir(os.path.join(self.root, ".trash"))
        self.write("loose.kf")
        tree = planner.portfolio_tree(self.root)
        self.assertEqual(tree["name"], os.path.basename(self.root))
        self.assertEqual([p["name"] for p in tree["projects"]], ["HDC", "MDM"])
        hdc = tree["projects"][0]
        self.assertEqual(hdc["files"], {"backlog": "HDC/backlog.kf", "quicknote": "HDC/quicknote.kf", "habits": "HDC/habits.kf"})
        self.assertEqual(hdc["made"], ["backlog"])
        self.assertEqual(hdc["notes"], [
            {"kind": "section", "name": "Client", "path": "HDC/notes/Client",
             "pages": [{"kind": "page", "name": "Req", "file": "Req.kf", "type": "kf", "path": "HDC/notes/Client/Req.kf"}]},
            {"kind": "page", "name": "Kickoff", "file": "Kickoff.md", "type": "md", "path": "HDC/notes/Kickoff.md"}])
        self.assertEqual(hdc["archive"], [{"year": 2026, "path": "HDC/archive/2026.kf"}, {"year": 2025, "path": "HDC/archive/2025.kf"}])
        self.assertEqual(tree["projects"][1]["notes"], [])

    def test_new_project_section_page(self):
        self.assertEqual(planner.new_project(self.root, " HDC "), "HDC")
        self.assertTrue(os.path.isdir(os.path.join(self.root, "HDC")))
        self.assertEqual(os.listdir(os.path.join(self.root, "HDC")), [])     # files are made on first save
        with self.assertRaises(planner.PortfolioError):
            planner.new_project(self.root, "HDC")
        for bad in ("", "  ", ".x", "a/b", "a\\b", "a:b", "a\nb", None):
            with self.subTest(name=bad), self.assertRaises(planner.PortfolioError):
                planner.new_project(self.root, bad)
        self.assertEqual(planner.new_page(self.root, "HDC", "Kickoff"), "HDC/notes/Kickoff.kf")
        self.assertEqual(planner.new_page(self.root, "HDC", "Call.md"), "HDC/notes/Call.md")
        self.assertEqual(planner.new_section(self.root, "HDC", "Client"), "HDC/notes/Client")
        self.assertEqual(planner.new_page(self.root, "HDC", "Req", "Client"), "HDC/notes/Client/Req.kf")
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/notes/Client/Req.kf"))[0], "")
        for args in (("HDC", "Kickoff"), ("HDC", "x", "Nope"), ("Nope", "x")):
            with self.subTest(args=args), self.assertRaises(planner.PortfolioError):
                planner.new_page(self.root, *args)
        for args in (("HDC", "Client"), ("HDC", "x.md"), ("Nope", "x")):
            with self.subTest(args=args), self.assertRaises(planner.PortfolioError):
                planner.new_section(self.root, *args)

    def test_rename(self):
        self.write("HDC/notes/Kickoff.md", "x")
        self.write("HDC/notes/Other.md", "y")
        self.assertEqual(planner.rename_item(self.root, "HDC/notes/Kickoff.md", "First call"), "HDC/notes/First call.md")
        self.assertEqual(planner.rename_item(self.root, "HDC/notes/First call.md", "First call.kf"), "HDC/notes/First call.kf")
        self.assertEqual(planner.rename_item(self.root, "HDC", "Harbour"), "Harbour")
        self.assertEqual(planner.read_notes(os.path.join(self.root, "Harbour/notes/First call.kf"))[0], "x")
        for rel, name in (("Harbour/notes/Other.md", "First call.kf"), ("Harbour/backlog.kf", "x"), ("Nope", "x"),
                          ("Harbour/notes/Other.md", "../x")):
            with self.subTest(rel=rel, name=name), self.assertRaises(planner.PortfolioError):
                planner.rename_item(self.root, rel, name)

    def test_trash_keeps_everything(self):
        self.write("HDC/notes/Kickoff.md", "one")
        self.assertEqual(planner.trash_item(self.root, "HDC/notes/Kickoff.md"), ".trash/HDC/notes/Kickoff.md")
        self.write("HDC/notes/Kickoff.md", "two")
        self.assertEqual(planner.trash_item(self.root, "HDC/notes/Kickoff.md"), ".trash/HDC/notes/Kickoff (2).md")
        self.assertEqual(planner.trash_item(self.root, "HDC"), ".trash/HDC (2)")
        self.assertEqual(planner.read_notes(os.path.join(self.root, ".trash/HDC/notes/Kickoff (2).md"))[0], "two")
        self.assertEqual(planner.portfolio_tree(self.root)["projects"], [])
        for rel in ("HDC", "MDM/backlog.kf", ".trash/HDC"):
            with self.subTest(rel=rel), self.assertRaises(planner.PortfolioError):
                planner.trash_item(self.root, rel)

    def test_import_one_project_unchanged(self):
        text = "Fall\r\n@A\r\n- a\r\n"
        self.assertEqual(planner.import_notes(text, self.root, "work"), {"work": text})
        with open(os.path.join(self.root, "work", "backlog.kf"), "rb") as f:
            self.assertEqual(f.read(), text.encode())

    def test_import_split(self):
        text = "- loose\nFall  Sep01--Dec19\n\n@A\n-- about A\n- a1\n\t- a2 Oct20\n@B\n- b1\nWinter\n@A\n- a3\n"
        out = planner.import_notes(text, self.root, "work", split=True)
        self.assertEqual(out, {"work": "- loose\n", "A": "Fall  Sep01--Dec19\n-- about A\n- a1\n\t- a2 Oct20\n\nWinter\n- a3\n",
                               "B": "Fall  Sep01--Dec19\n- b1\n"})
        a = planner.parse(out["A"], "A")
        self.assertEqual([t.title for p in a for t in p.all_tasks()], ["a1", "a2", "a3"])
        self.assertEqual(a[0].notes, ["about A"])
        with self.assertRaises(planner.PortfolioError):
            planner.import_notes(text, self.root, "work", split=True)

    def test_example_portfolio_is_the_split_example(self):
        made = planner.import_notes(read_example(), self.root, "example", split=True)
        for project, text in made.items():
            with self.subTest(project=project):
                self.assertEqual(planner.read_notes(os.path.join(PORTFOLIO, project, "backlog.kf"))[0], text)
        whole = [t.title for p in planner.parse(read_example()) for t in p.all_tasks()]
        split = [t.title for name, text in made.items() for p in planner.parse(text, name) for t in p.all_tasks()]
        self.assertEqual(sorted(split), sorted(whole))


class TestServerPortfolio(Base):
    """--serve FOLDER: the portfolio's projects, pages and files, by paths relative to it."""
    write = TestPortfolio.write

    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.dir.name)
        self.write("HDC/backlog.kf", "@Stream\n- a Oct20\n- b\n")
        self.write("HDC/notes/Kickoff.md", "# hi")
        self.write("secret.txt", "no")
        self.server = planner.make_server(0, None, portfolio=self.root)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.dir.cleanup()
        super().tearDown()

    post, send = TestServer.post, TestServer.send

    def get(self, path):
        return self.send(urllib.request.Request(self.url + path))

    def file(self, rel):
        return self.get("/api/file?path=" + urllib.parse.quote(rel))

    def test_tree(self):
        code, d = self.get("/api/portfolio")
        self.assertEqual(code, 200)
        self.assertEqual([p["name"] for p in d["projects"]], ["HDC"])
        req = urllib.request.Request(self.url + "/api/portfolio", headers={"Origin": "https://evil.example"})
        self.assertEqual(self.send(req)[0], 403)

    def test_ops(self):
        code, d = self.post("/api/portfolio", {"op": "project", "name": "MDM"})
        self.assertEqual((code, d["path"], [p["name"] for p in d["tree"]["projects"]]), (200, "MDM", ["HDC", "MDM"]))
        self.assertEqual(self.post("/api/portfolio", {"op": "section", "project": "MDM", "name": "Hiring"})[1]["path"], "MDM/notes/Hiring")
        self.assertEqual(self.post("/api/portfolio", {"op": "page", "project": "MDM", "name": "Plan", "section": "Hiring"})[1]["path"],
                         "MDM/notes/Hiring/Plan.kf")
        self.assertEqual(self.post("/api/portfolio", {"op": "rename", "path": "MDM", "name": "Hiring"})[1]["path"], "Hiring")
        code, d = self.post("/api/portfolio", {"op": "trash", "path": "Hiring"})
        self.assertEqual((code, d["path"], [p["name"] for p in d["tree"]["projects"]]), (200, ".trash/Hiring", ["HDC"]))
        self.assertEqual(self.post("/api/portfolio", {"op": "project", "name": "HDC"})[0], 409)
        self.assertEqual(self.post("/api/portfolio", {"op": "project", "name": "../x"})[0], 409)
        self.assertEqual(self.post("/api/portfolio", {"op": "explode"})[0], 400)

    def test_read_and_write_files(self):
        code, d = self.file("HDC/notes/Kickoff.md")
        self.assertEqual((code, d["name"], d["path"], d["text"]), (200, "Kickoff.md", "HDC/notes/Kickoff.md", "# hi"))
        code, d = self.file("HDC/quicknote.kf")                         # not made yet
        self.assertEqual((code, d["text"], d["version"]), (200, "", None))
        code, d = self.post("/api/file", {"path": "HDC/quicknote.kf", "text": "- call Lisa", "version": None})
        self.assertEqual(code, 200)
        self.assertEqual(self.file("HDC/quicknote.kf")[1]["version"], d["version"])
        self.assertEqual(self.post("/api/file", {"path": "HDC/quicknote.kf", "text": "x", "version": None})[0], 409)
        code, d = self.post("/api/file", {"path": "HDC/archive/2026.kf", "text": "- done", "version": None})
        self.assertEqual(code, 200)                                     # archive/ is made on the first save
        self.assertEqual(self.file("HDC/archive/2025.kf")[1]["text"], "")
        self.assertFalse(os.path.exists(os.path.join(self.root, "HDC", "notes", "x")))
        for rel in ("secret.txt", "../x.txt", "HDC", "Nope/backlog.kf", "HDC/notes/Missing/a.kf", "HDC/notes/a.png"):
            with self.subTest(rel=rel):
                self.assertEqual(self.file(rel)[0], 409)
                self.assertEqual(self.post("/api/file", {"path": rel, "text": "x", "version": None})[0], 409)

    def test_edit_a_file_by_path(self):
        code, d = self.file("HDC/backlog.kf")
        req = {"path": "HDC/backlog.kf", "version": d["version"], "line": 2, "title": "a", "op": "status", "value": "done"}
        code, out = self.post("/api/edit", dict(req, today="2026-10-12"))
        self.assertEqual(code, 200)
        self.assertEqual(out["text"], "@Stream\n!- a Oct20\n- b\n")
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC", "backlog.kf")), (out["text"], out["version"]))
        self.assertEqual(out["data"]["projects"][0]["projects"][0]["name"], "Stream")
        code, out = self.post("/api/edit", req)                         # the old version: refused, nothing written
        self.assertEqual((code, out["conflict"]), (409, True))
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC", "backlog.kf"))[0], "@Stream\n!- a Oct20\n- b\n")
        code, out = self.post("/api/edit", dict(req, version=out["version"], title="wrong"))
        self.assertEqual(code, 409)
        self.assertEqual(self.post("/api/edit", dict(req, path="secret.txt"))[0], 409)

    def test_edit_names_the_backlog_project(self):
        self.write("HDC/backlog.kf", "- a\n")
        d = self.file("HDC/backlog.kf")[1]
        code, out = self.post("/api/edit", {"path": "HDC/backlog.kf", "version": d["version"], "line": 1, "title": "a",
                                            "op": "status", "value": "doing"})
        self.assertEqual(code, 200)
        self.assertEqual(out["data"]["projects"][0]["projects"][0]["name"], "HDC")

    def test_page_parse_names_the_project(self):
        code, d = self.post("/api/parse", {"text": "", "name": "HDC"})
        self.assertEqual(d["targets"], [{"name": "HDC", "line": 0, "path": None, "folder": None, "section": None}])
        code, d = self.post("/api/edit", {"text": "", "name": "HDC", "line": 0, "title": "HDC", "op": "task", "value": "a"})
        self.assertEqual((code, d["text"]), (200, "- a\n"))
        self.assertEqual(d["data"]["projects"][0]["projects"][0]["name"], "HDC")
        self.assertEqual(d["data"]["targets"][0]["line"], 1)

    def test_all_projects(self):
        self.write("MDM/backlog.kf", "- c (KA) Oct14\n")
        os.mkdir(os.path.join(self.root, "OPS"))                       # no backlog yet
        code, d = self.post("/api/parse", {"all": True, "today": "2026-10-12"})
        self.assertEqual(code, 200)
        self.assertEqual(sorted(d["versions"]), ["HDC/backlog.kf", "HDC/habits.kf", "MDM/backlog.kf", "MDM/habits.kf",
                                                 "OPS/backlog.kf", "OPS/habits.kf"])
        self.assertIsNone(d["versions"]["OPS/backlog.kf"])
        names = [(p["name"], p["folder"], p["path"]) for sec in d["projects"] for p in sec["projects"]]
        self.assertEqual(names, [("Stream", "HDC", "HDC/backlog.kf"), ("MDM", "MDM", "MDM/backlog.kf")])
        self.assertEqual(d["projects"][0]["projects"][0]["tasks"][0]["path"], "HDC/backlog.kf")
        self.assertEqual([(t["name"], t["line"]) for t in d["targets"]], [("HDC", 0), ("OPS", 0), ("Stream", 1), ("MDM", 1)])
        self.assertEqual(d["people"][0]["tasks"][0]["folder"], "MDM")
        self.assertEqual(self.post("/api/edit", {"path": "MDM/backlog.kf", "version": "stale", "line": 1, "title": "c",
                                                 "op": "status", "value": "done"})[0], 409)
        code, out = self.post("/api/edit", {"path": "MDM/backlog.kf", "version": d["versions"]["MDM/backlog.kf"], "all": True,
                                            "line": 1, "title": "c", "op": "status", "value": "done"})
        self.assertEqual((code, out["text"], out["before"]), (200, "!- c (KA) Oct14\n", "- c (KA) Oct14\n"))
        self.assertEqual(out["data"]["versions"]["MDM/backlog.kf"], out["version"])
        code, out = self.post("/api/edit", {"path": "OPS/backlog.kf", "version": None, "all": True,
                                            "line": 0, "title": "OPS", "op": "task", "value": {"title": "first", "who": "RT"}})
        self.assertEqual((code, out["text"]), (200, "- first (RT)\n"))
        self.assertIn("OPS", [p["name"] for sec in out["data"]["projects"] for p in sec["projects"]])

    def test_all_projects_merges_sections_by_title(self):
        self.write("A/backlog.kf", "Fall\n- a\n")
        self.write("B/backlog.kf", "Fall\n- b\nWinter\n- c\n")
        d = planner.portfolio_data(self.root)
        self.assertEqual([(s["title"], [p["name"] for p in s["projects"]]) for s in d["projects"]],
                         [("Fall", ["A", "B"]), ("Winter", ["B"]), (None, ["Stream"])])

    def archive(self, **extra):
        d = self.file("HDC/backlog.kf")[1]
        return self.post("/api/archive", dict({"path": "HDC/backlog.kf", "version": d["version"], "archive_year": 2026}, **extra))

    def test_archive_a_task(self):
        self.write("HDC/backlog.kf", "- own\n@Stream\n!- a Oct20\n\t!- a1\n- b\n")
        code, d = self.archive(line=3, title="a")
        self.assertEqual(code, 200)
        self.assertEqual(d["text"], "- own\n@Stream\n- b\n")
        self.assertEqual((d["archive"], d["moved"]), ("HDC/archive/2026.kf", 2))
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/backlog.kf")), (d["text"], d["version"]))
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/archive/2026.kf"))[0], "@Stream\n!- a Oct20\n\t!- a1\n")
        self.assertEqual(d["tree"]["projects"][0]["archive"], [{"year": 2026, "path": "HDC/archive/2026.kf"}])
        self.assertEqual([u["path"] for u in d["undo"]], ["HDC/backlog.kf", "HDC/archive/2026.kf"])
        self.assertEqual(d["undo"][1]["before"], "")
        for u in d["undo"]:                                             # Undo: both files back as they were
            self.assertEqual(self.post("/api/file", {"path": u["path"], "text": u["before"], "version": u["version"]})[0], 200)
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/backlog.kf"))[0], "- own\n@Stream\n!- a Oct20\n\t!- a1\n- b\n")
        code, d = self.archive(line=1, title="own", archive_year=2025)   # the project's own task: no @ in the archive
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/archive/2025.kf"))[0], "- own\n")

    def test_archive_done_and_all_projects(self):
        self.write("HDC/backlog.kf", "!- x\n@Stream\n!- a\n- b\n")
        d = self.post("/api/parse", {"all": True})[1]
        code, out = self.post("/api/archive", {"path": "HDC/backlog.kf", "version": d["versions"]["HDC/backlog.kf"], "archive_year": 2026,
                                               "done": True, "project_line": 2, "all": True})
        self.assertEqual((code, out["text"], out["moved"]), (200, "!- x\n@Stream\n- b\n", 1))
        self.assertEqual(out["data"]["versions"]["HDC/backlog.kf"], out["version"])

    def test_archive_refusals(self):
        self.write("HDC/backlog.kf", "- a\n")
        self.assertEqual(self.archive(line=1, title="a", version="old")[0], 409)          # stale
        self.assertEqual(self.archive(line=1, title="b")[0], 409)                         # not that task
        self.assertEqual(self.archive(done=True)[0], 409)                                 # nothing finished
        self.assertEqual(self.archive(line=1, title="a", archive_year="2026")[0], 400)
        self.assertEqual(self.archive(line=1, title="a", path="HDC/notes/Kickoff.md")[0], 409)
        self.assertEqual(self.archive(line=1, title="a", path="HDC/archive/2026.kf")[0], 409)
        self.assertFalse(os.path.exists(os.path.join(self.root, "HDC/archive")))
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/backlog.kf"))[0], "- a\n")

    def test_archive_page_reads_in_its_year(self):
        code, d = self.post("/api/parse", {"text": "- a Jan03\n", "name": "HDC", "year": 2025})
        self.assertEqual(d["projects"][0]["projects"][0]["tasks"][0]["span"]["start"], "2025-01-03")
        self.assertEqual(self.post("/api/parse", {"text": "", "year": "2025"})[0], 400)

    def test_habits_in_the_portfolio(self):
        self.write("HDC/habits.kf", "- stretch *daily\n")
        d = self.post("/api/parse", {"all": True, "today": "2026-11-06"})[1]
        self.assertEqual([(x["title"], x["path"], x["folder"]) for x in d["planner"]["habits"]], [("stretch", "HDC/habits.kf", "HDC")])
        code, out = self.post("/api/edit", {"path": "HDC/habits.kf", "version": d["versions"]["HDC/habits.kf"], "all": True, "today": "2026-11-06",
                                            "line": 1, "title": "stretch", "op": "tick", "value": "Nov06"})
        self.assertEqual((code, out["text"]), (200, "- stretch *daily\n\t-- done Nov06\n"))
        self.assertEqual(out["data"]["planner"]["habits"][0]["done"], ["2026-11-06"])
        code, d = self.post("/api/parse", {"text": out["text"], "name": "HDC", "habits": True, "today": "2026-11-06"})
        self.assertEqual(d["planner"]["habits"][0]["done"], ["2026-11-06"])
        code, d = self.post("/api/parse", {"text": "- x *daily\n\t-- done Dec30\n", "name": "HDC", "habits": True, "year": 2025})
        self.assertEqual(d["projects"][0]["projects"][0]["tasks"][0]["log"], ["2025-12-30"])   # an archive: its own year

    def test_archive_habit_log(self):
        self.write("HDC/habits.kf", "- stretch *daily\n\t-- done Dec30 Jan02\n")
        v = self.file("HDC/habits.kf")[1]["version"]
        code, out = self.post("/api/archive", {"path": "HDC/habits.kf", "version": v, "archive_year": 2026, "habit_log": True,
                                               "today": "2027-01-05"})
        self.assertEqual((code, out["text"]), (200, "- stretch *daily\n\t-- done Jan02\n"))
        self.assertEqual(planner.read_notes(os.path.join(self.root, "HDC/archive/2026.kf"))[0], "@Habits\n- stretch *daily\n\t-- done Dec30\n")
        self.assertEqual(self.post("/api/archive", {"path": "HDC/backlog.kf", "version": self.file("HDC/backlog.kf")[1]["version"],
                                                    "archive_year": 2026, "habit_log": True})[0], 409)

    def test_file_browser_is_off(self):
        self.assertEqual(self.get("/api/browse")[0], 409)
        self.assertEqual(self.post("/api/open", {"path": os.path.join(self.root, "secret.txt")})[0], 409)


if __name__ == "__main__":
    unittest.main()
