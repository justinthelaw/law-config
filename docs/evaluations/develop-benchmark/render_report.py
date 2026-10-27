"""Render the historical benchmark and two independent source-packet cohorts."""

import csv
import json
import math
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas


HERE = Path(__file__).resolve().parent
ISSUE = "https://github.com/justinthelaw/law-config/issues/71"
UPDATE = ISSUE + "#issuecomment-6434762307"
RESULTS = "https://github.com/justinthelaw/law-config/blob/e36c8d848d33385c3fcbf1d4dc08175e5cce648c/docs/evaluations/develop-benchmark/replication/results.json"
WIDTH, HEIGHT = letter
LEFT, RIGHT = 44, WIDTH - 44
INK, MUTED, LINE = "#172D36", "#405963", "#CED9D9"
TEAL, PALE, BLUE = "#006B60", "#E7F4F0", "#456581"
RUST, LIGHT = "#904424", "#F2F5F5"
METRICS = ("seconds", "uncached_input", "cached_input", "output", "total_context")
COHORTS = {"recovered-fixture": "Recovered fixtures", "replacement-fixture": "Replacement fixtures"}

# Historical task-specific acceptance and blind assessments from Evidence A and G.
EVIDENCE = {
    "Requests": ("7/7", "Mixed maintenance and test tradeoffs",
                 "Both handled file-like proxies and passed 243 socket-free native checks, with 13 skipped. "
                 "The assessors found mixed maintenance and test tradeoffs. Full HTTP coverage was incomplete."),
    "Cobra": ("13 leaf subcases", "Mixed overall with complementary tests",
              "Both satisfied the validator requirement and passed the full Go suite. Gold retained more "
              "contextual diagnostics. The two agents added complementary regression tests."),
    "Starlette": ("12/12", "Complementary boundary tests",
                  "Both agents preserved a repeated-slash root-path boundary that gold broke. Their production "
                  "fixes matched. The improvement over gold was reproduced after the trials."),
    "Flask": ("17/17", "Develop's tests modestly preferred",
              "Both preserved explicit host and port overrides with an invalid configured port. Gold raised "
              "an error in this post-hoc check. Assessors modestly preferred Develop's regression tests."),
    "Hugo": ("6 API + 1 template", "Develop's tests modestly preferred",
             "Runtime behavior matched across both arms. Each improved template regression coverage over "
             "gold. Assessors favored Develop's additional pipeline and conversion boundary tests."),
}


def rows(name):
    with (HERE / name).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def text(c, x, y, value, size=10.5, color=INK, font="Helvetica"):
    c.setFillColor(HexColor(color))
    c.setFont(font, size)
    c.drawString(x, HEIGHT - y - size, value)


def paragraph(c, x, y, value, width=RIGHT - LEFT, size=11, leading=15, color=INK):
    for line in simpleSplit(value, "Helvetica", size, width):
        text(c, x, y, line, size, color)
        y += leading
    return y


def box(c, x, y, width, height, color):
    c.setFillColor(HexColor(color))
    c.rect(x, HEIGHT - y - height, width, height, fill=1, stroke=0)


def rule(c, y):
    box(c, LEFT, y, RIGHT - LEFT, 0.65, LINE)


def link(c, x, y, label, url, size=9.5):
    text(c, x, y, label, size, TEAL, "Helvetica-Bold")
    width = c.stringWidth(label, "Helvetica-Bold", size)
    c.linkURL(url, (x, HEIGHT - y - size - 2, x + width, HEIGHT - y + 1))


def page(c, section, title, subtitle, source, url):
    anchor = f"page-{c.getPageNumber()}"
    c.bookmarkPage(anchor)
    outline = title if title != "What each arm produced" else subtitle.split("   /   ")[0] + " case evidence"
    if section.split("   /   ")[0] in COHORTS.values():
        outline += " · " + section.split("   /   ")[0]
    c.addOutlineEntry(outline, anchor)
    text(c, LEFT, 30, "DEVELOP  /  EVALUATION NOTES", 9, TEAL, "Helvetica-Bold")
    text(c, RIGHT - 113, 30, "26-27 OCTOBER 2026", 9, MUTED)
    rule(c, 49)
    text(c, LEFT, 72, section.upper(), 10, TEAL, "Helvetica-Bold")
    text(c, LEFT, 96, title, 28, INK, "Helvetica-Bold")
    paragraph(c, LEFT, 142, subtitle, size=12, leading=17, color=MUTED)
    rule(c, 730)
    link(c, LEFT, 742, source, url)
    right_text(c, RIGHT, 742, f"PAGE {c.getPageNumber():02d}", 9, MUTED)


def heading(c, y, value):
    text(c, LEFT, y, value, 15, INK, "Helvetica-Bold")


def note(c, y, title, body):
    text(c, LEFT, y, title, 12, INK, "Helvetica-Bold")
    return paragraph(c, LEFT, y + 20, body, size=10.8, leading=14.5)


def delta(control, develop):
    return (develop / control - 1) * 100


def sum_arms(pairs):
    return {arm: {metric: sum(pair[arm][metric] for _, pair in pairs) for metric in METRICS}
            for arm in ("control", "develop")}


def change(pair, metric):
    control, develop = pair["control"][metric], pair["develop"][metric]
    return develop - control, delta(control, develop)


def summary(c, cases, pairs, totals):
    page(c, "Historical workflow   /   26 October", "Both arms passed all five tasks",
         "Develop finished two tasks faster and three slower. It used more context on every task. "
         "Neither arm showed better production behavior on the tested paths.",
         "Source  /  historical results and case selection", ISSUE + "#evidence-g:~:text=final%20selected%20sources")
    selected = {case["label"] for case in cases}
    heading(c, 198, "Develop compared with control")
    box(c, LEFT, 228, RIGHT - LEFT, 21, LIGHT)
    for x, label in [(50, "TASK / SLATE"), (140, "BOTH PASSED"), (237, "BLIND ASSESSMENT"),
                     (365, "ELAPSED TIME"), (472, "CONTEXT TOKENS")]:
        text(c, x, 234, label, 8.2, MUTED, "Helvetica-Bold")
    for i, (name, pair) in enumerate(pairs):
        y = 255 + i * 40
        acceptance, assessment, _ = EVIDENCE[name]
        seconds, elapsed_pct = change(pair, "seconds")
        tokens, context_pct = change(pair, "total_context")
        text(c, 50, y, name, 11.5, INK, "Helvetica-Bold")
        text(c, 50, y + 16, "Selected" if name in selected else "Supplemental", 9.3, MUTED)
        text(c, 140, y + 3, acceptance, 9.8)
        paragraph(c, 237, y + 1, assessment, 115, 10, 12.5)
        direction = "faster" if seconds < 0 else "slower"
        text(c, 365, y, f"{abs(elapsed_pct):.1f}% {direction}", 11, TEAL if seconds < 0 else RUST,
             "Helvetica-Bold")
        text(c, 365, y + 16, f"{seconds:+.1f} s", 9.3, MUTED)
        text(c, 472, y, f"{context_pct:.1f}% more", 11, INK, "Helvetica-Bold")
        text(c, 472, y + 16, f"{tokens:+,}", 9.3, MUTED)
        rule(c, y + 34)

    heading(c, 477, "Two selected pairs versus all five completed pairs")
    box(c, LEFT, 506, RIGHT - LEFT, 20, LIGHT)
    for x, label in [(50, "COMPLETED PAIRS"), (237, "BOTH PASSED"), (365, "ELAPSED TIME"),
                     (472, "CONTEXT TOKENS")]:
        text(c, x, 511, label, 8.2, MUTED, "Helvetica-Bold")
    selected_pairs = [(name, pair) for name, pair in pairs if name in selected]
    for i, (label, subset, cohort) in enumerate([
        ("Selected", selected_pairs, sum_arms(selected_pairs)), ("All historical", pairs, totals)
    ]):
        y = 534 + 23 * i
        text(c, 50, y, f"{label} ({len(subset)} pairs)", 10.6, INK, "Helvetica-Bold")
        text(c, 237, y, f"{len(subset)} of {len(subset)} tasks", 10.4)
        text(c, 365, y, f"{change(cohort, 'seconds')[1]:.1f}% slower", 10.5, RUST, "Helvetica-Bold")
        text(c, 472, y, f"{change(cohort, 'total_context')[1]:.1f}% more", 10.5, INK, "Helvetica-Bold")
    paragraph(c, LEFT, 586, "Percentages use control as the baseline. The two summaries compare sums "
              "across tasks. Time includes reviews and waiting. The historical resource table gives the measurements for each arm.",
              size=10, leading=13, color=MUTED)
    box(c, LEFT, 624, RIGHT - LEFT, 29, PALE)
    text(c, LEFT + 9, 631, "Billed dollars are unavailable.", 10.5, INK, "Helvetica-Bold")
    text(c, LEFT + 166, 631, "Context counts uncached input, cached input and output.", 10.4)
    paragraph(c, LEFT, 669, "Roux chose the design and interpreted the results. The target fell from 20 cases "
              "to eight after some outcomes were known. Only two selected cases finished. Each of the five "
              "Python or Go tasks had one pair, limiting conclusions about other tasks.", size=10.3, leading=14)
    c.showPage()


def method(c):
    page(c, "Historical workflow   /   26 October", "One task, two isolated arms",
         "Compare Codex with and without Develop under the same review process. The merged "
         "human PR supplies a third reference for behavior and patch quality.",
         "Source  /  frozen protocol and portable inputs", ISSUE + "#evidence-h:~:text=independent%20payload%20receipt")
    for x, label, body, fill in [
        (LEFT, "CONTROL", "Clean base and repository guidance. Develop is inaccessible.", "#EDF2F6"),
        (225, "DEVELOP", "Same clean base and guidance, plus the frozen Develop package.", PALE),
        (406, "EVALUATOR", "Separate gold checkout, hidden acceptance tests and arm mapping.", "#F6F0E7"),
    ]:
        box(c, x, 207, 162, 98, fill)
        text(c, x + 10, 219, label, 10, INK, "Helvetica-Bold")
        paragraph(c, x + 10, 240, body, 142, 10.3, 13.5)
    note(c, 331, "1. Freeze and admit each case",
         "Verify the gold merge and its first parent, requirement and toolchain hashes. Run base "
         "and gold checks offline. Keep the worker prompt free of PR identifiers and solution hints.")
    note(c, 403, "2. Match execution and test the boundaries",
         "Use CLI 0.159.2, gpt-6.1-sol at medium effort and Develop 0.9.0. Run arms serially "
         "with equal resources and time limits. Each gets one synthetic base commit. Deny command "
         "egress, sibling, evaluator and auth paths for workers, reviewers and descendants.")
    note(c, 489, "3. Measure the full workflow",
         "Each arm in the five completed pairs used one implementation root, two planning reviewers and two final "
         "reviewers. Start the clock before instruction loading. Reconcile final cumulative usage "
         "once per native thread. Retain waits, retries, partials and missing values.")
    note(c, 575, "4. Grade anonymous patches",
         "Check acceptance and new regressions. Hide arm identities and timing from graders. "
         "Compare behavior, tests, security and maintenance against gold. Use targeted reproductions "
         "for disagreements and retain uncertainty when evidence is inconclusive.")
    paragraph(c, LEFT, 671, "Limits include possible style leakage or memorization, prior gold "
              "exposure for acceptance authors, and retrospective tool-event auditing.",
              size=10, leading=13.5, color=MUTED)
    c.showPage()


def right_text(c, x, y, value, size=10, color=INK, font="Helvetica"):
    text(c, x - c.stringWidth(value, font, size), y, value, size, color, font)


def costs(c, pairs, totals):
    page(c, "Historical workflow   /   26 October", "Time and tokens by task",
         "Each row includes the implementation and review work for one arm. Seconds run from "
         "release through final receipt, including waits. Token counts come from native usage.",
         "Source  /  all 30 historical ledger rows", ISSUE + "#evidence-f:~:text=final%20complete%2030-row%20metric%20ledger")
    heading(c, 197, "Five completed historical pairs")
    box(c, LEFT, 225, RIGHT - LEFT, 22, LIGHT)
    text(c, 50, 231, "TASK", 8.3, MUTED, "Helvetica-Bold")
    text(c, 142, 231, "ARM", 8.3, MUTED, "Helvetica-Bold")
    columns = [(255, "SECONDS"), (336, "UNCACHED IN"), (416, "CACHED IN"),
               (482, "OUTPUT"), (561, "CONTEXT")]
    for x, label in columns:
        right_text(c, x, 231, label, 8.3, MUTED, "Helvetica-Bold")
    for i, (name, pair) in enumerate([*pairs, ("Five-pair sum", totals)]):
        y = 252 + i * 41
        if pair is totals:
            box(c, LEFT, y - 1, RIGHT - LEFT, 37, LIGHT)
        text(c, 50, y + 4, name, 10.5, INK, "Helvetica-Bold")
        for j, arm in enumerate(("control", "develop")):
            baseline = y + 2 + j * 15
            text(c, 142, baseline, arm.title(), 9.8, BLUE if arm == "control" else TEAL)
            for (x, _), metric in zip(columns, METRICS):
                value = pair[arm][metric]
                label = f"{value:,.1f}" if metric == "seconds" else f"{value:,}"
                right_text(c, x, baseline, label)
        rule(c, y + 35)

    text(c, LEFT, 520, "Elapsed time change", 13.5, INK, "Helvetica-Bold")
    text(c, LEFT, 544, "Develop minus control, in seconds", 10, MUTED)
    origin = 174
    scale = 0.65  # Points per second, shared across tasks.
    text(c, 112, 566, "Faster", 8.5, TEAL)
    text(c, origin - 2, 566, "0", 8.5, MUTED)
    text(c, 214, 566, "Slower", 8.5, RUST)
    box(c, origin, 583, 0.6, 82, LINE)
    for i, (name, pair) in enumerate(pairs):
        seconds, _ = change(pair, "seconds")
        y = 583 + i * 17
        width = seconds * scale
        text(c, LEFT, y, name, 9.8)
        box(c, origin + min(width, 0), y + 3, abs(width), 7, TEAL if seconds < 0 else RUST)
        right_text(c, 286, y, f"{seconds:+.1f} s", 9.8)

    x = 316
    text(c, x, 520, "Additional context by type", 13.5, INK, "Helvetica-Bold")
    extra, _ = change(totals, "total_context")
    text(c, x, 544, f"Share of the {extra:,} extra tokens", 10, MUTED)
    components = [("uncached_input", "Uncached input", BLUE), ("cached_input", "Cached input", TEAL),
                  ("output", "Output", RUST)]
    offset = x
    for i, (metric, label, color) in enumerate(components):
        more, _ = change(totals, metric)
        width = (RIGHT - x) * more / extra
        box(c, offset, 569, width, 14, color)
        offset += width
        y = 597 + i * 21
        box(c, x, y + 3, 7, 7, color)
        text(c, x + 12, y, label, 10)
        right_text(c, RIGHT, y, f"+{more:,} ({more / extra:.1%})", 10)
    paragraph(c, LEFT, 680, "Billed dollars are unavailable. Cached and uncached input are counted "
              "separately. Output includes reasoning. Coordinator, grader and human reference usage "
              "are unknown and excluded.", size=10.2, leading=14, color=MUTED)
    c.showPage()


def quality(c, cases, pairs):
    page(c, "Historical workflow   /   26 October", "How did the patches compare?",
         "Acceptance is measured per case. Qualitative preferences below come from the historical "
         "blind assessments. Different test sets make pooled test counts misleading.",
         "Source  /  case-level acceptance and judgments", ISSUE + "#evidence-a:~:text=historical%20partial%20report")
    selected = {case["label"] for case in cases}
    for i, (name, _) in enumerate(pairs):
        acceptance, _, detail = EVIDENCE[name]
        slate = "Selected" if name in selected else "Supplemental"
        y = 203 + 97 * i
        rule(c, y)
        text(c, LEFT, y + 10, name, 14.5, INK, "Helvetica-Bold")
        text(c, 156, y + 14, f"{slate}  /  BOTH PASSED {acceptance}".upper(), 8.5, TEAL, "Helvetica-Bold")
        paragraph(c, LEFT, y + 38, detail, size=10.7, leading=14.5)
    paragraph(c, LEFT, 695, "Only the tested paths support these comparisons.", size=10, color=MUTED)
    c.showPage()


def remaining(c, cases):
    page(c, "Historical workflow   /   26 October", "Where did the eight cases stand?",
         "These are the dispositions on 26 October, before the source-packet trials. The first five projects are external. "
         "The last three are user-owned and have prior-context risk. Case labels link to the gold PRs.",
         "Source  /  frozen cases and admission results", ISSUE + "#evidence-g:~:text=final%20selected%20sources")
    details = {
        "Requests": "Both arms passed all seven acceptance checks.",
        "Cobra": "Both arms passed 13 leaf subcases and the full Go suite.",
        "Tokio": "No arms. Worker baseline 26/26. The new API was absent on base.",
        "fmt": "Develop partial passed 13/13. Final review hit a service limit. Control unstarted.",
        "Svelte": "No arms. Independent checks passed 8/8 on both references. Gold-derived checks went from 0/2 to 2/2.",
        "Personal site": "Offline install and build passed. Five browser projects still needed runtime admission.",
        "law-config": "Develop stopped before edits. Control unstarted. Acceptance was 2/7 on base and 7/7 on gold.",
        "Runner-space": "No arms. Behavioral checks went from 3/9 to 9/9. Six native permission failures affected both references.",
    }
    for x, label in [(LEFT, "CASE / GOLD PR"), (190, "FIRST / LIMIT"), (295, "LAST VERIFIED STATE")]:
        text(c, x, 201, label, 8.5, MUTED, "Helvetica-Bold")
    for i, case in enumerate(cases):
        y = 222 + i * 56
        rule(c, y)
        label = case["label"]
        number = case["pr_url"].split("/")[-1]
        link(c, LEFT, y + 7, f"{label} #{number}", case["pr_url"], 10)
        text(c, LEFT, y + 27, case["disposition"], 9, MUTED)
        text(c, 190, y + 8, case["first_arm"].title(), 10)
        text(c, 190, y + 27, case["minutes_per_arm"] + " min / arm", 9, MUTED)
        paragraph(c, 295, y + 7, details[label], RIGHT - 295, 10, 12.5)
    paragraph(c, LEFT, 684, "Six selected pairs remained. fmt and law-config each retained one fresh pair "
              "retry. Outside the selected slate, Click's pilot was ambiguous, Vue exhausted its retry "
              "and FastAPI lacked a completed control arm.", size=10, color=MUTED)
    c.showPage()


def implications(c, pairs, ledger):
    page(c, "Historical workflow   /   26 October", "What did the first five pairs suggest?",
         "The five completed tasks each ran once per arm. Test one change at a time in fresh "
         "matched pairs, with the same review roles, time limits and blind grading in both arms.",
         "Source  /  continuation outcome and recommendations", UPDATE)
    by_task = dict(pairs)
    selected = sum_arms([(name, by_task[name]) for name in ("Requests", "Cobra")])
    hypotheses = [
        ("Could smaller review packets save time and context?",
         f"On Requests and Cobra, Develop took {change(selected, 'seconds')[0]:.1f} s longer in total "
         f"and used {change(selected, 'total_context')[0]:,} more tokens. Both tasks had mixed blind assessments.",
         "Measure time and tokens by phase. Test a shorter packet against current Develop. Keep it "
         "if time and tokens fall, acceptance still passes and graders find no quality loss or new regressions."),
        ("Which test guidance earns its cost?",
         f"Assessors favored Develop's tests on Flask and Hugo. Develop finished Flask "
         f"{abs(change(by_task['Flask'], 'seconds')[0]):.1f} s faster and Hugo "
         f"{change(by_task['Hugo'], 'seconds')[0]:.1f} s slower. Develop used more context on both.",
         "Compare focused boundary-test guidance with current instructions. Check whether new tests "
         "catch the override or pipeline failure. Blind-grade coverage and record elapsed time and tokens."),
        ("Can the fixture distinguish a working change?",
         "On Svelte, independent checks passed 8/8 on base and gold. Only the two gold-derived "
         "checks distinguished them.",
         "Freeze an independent check that fails on base and passes on gold. Label gold-derived evidence. "
         "Verify inference, isolation, instruction loading and usage in a matched pilot before expanding."),
    ]
    y = 199
    for i, (title, observation, experiment) in enumerate(hypotheses, start=1):
        rule(c, y)
        text(c, LEFT, y + 10, f"0{i}", 10, TEAL, "Helvetica-Bold")
        text(c, LEFT + 28, y + 7, title, 13.5, INK, "Helvetica-Bold")
        x = LEFT + 28
        y = paragraph(c, x, y + 31, observation, RIGHT - x, 10.5, 14)
        y = paragraph(c, x, y + 5, experiment, RIGHT - x, 10.5, 14) + 16
    box(c, LEFT, y + 2, RIGHT - LEFT, 22, LIGHT)
    text(c, LEFT + 7, y + 6, "WHY THE HISTORICAL RUN STOPPED", 9, MUTED, "Helvetica-Bold")
    attempts = [row for row in ledger if row["arm"] != "gold"]
    elapsed = sum(float(row["seconds"]) for row in attempts)
    known_context = sum(int(row["total_context"]) for row in attempts)
    lower_bounds = sum(row["usage"] == "known_lower_bound_only" for row in attempts)
    y = paragraph(c, LEFT, y + 32, "After repeated service limits, the run paused and its restart was "
                  f"canceled. The {len(attempts)} attempted arms used {elapsed:,.1f} recorded seconds and at least "
                  f"{known_context:,} tokens. Usage is a lower bound for {lower_bounds} arms. All "
                  f"{len(ledger) - len(attempts)} human references lack time and usage data.", size=10.2, leading=13)
    paragraph(c, LEFT, y + 6, "The first continuation recovered 16 base/gold snapshots and the pinned "
              "Linux CLI. Four Tokio role profiles each passed 14 checks directly and in descendants. Device "
              "sign-in was unavailable, the pinned server had no authenticated account and desktop builds "
              "differed. At the user's request, that continuation stopped before a scored turn.",
              size=10.2, leading=13)
    c.showPage()


def printable(value):
    if value is None:
        return "Unavailable"
    if isinstance(value, dict):
        return "  ".join(f"{str(key).replace('_', ' ').capitalize()} — {printable(part)}"
                         for key, part in value.items())
    if isinstance(value, list):
        return "  ".join(printable(part) for part in value)
    return (str(value).replace("→", " to ").replace("≥", ">=").replace("≤", "<=")
            .replace(" ", " ").replace(" ", " "))


def prose(value):
    value = printable(value).replace("failed_or_incomplete", "failed or incomplete")
    clauses = value.replace(". pass for ", ". Pass for ").removeprefix("Tie: ").split("; ")
    return ". ".join(clause[:1].upper() + clause[1:] for clause in clauses)


def lines(c, value, width, size, font="Helvetica"):
    # The source data can contain long identifiers and unbroken hashes.
    wrapped = []
    for line in simpleSplit(printable(value), font, size, width):
        while c.stringWidth(line, font, size) > width:
            lo, hi = 1, len(line)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if c.stringWidth(line[:mid], font, size) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            wrapped.append(line[:lo])
            line = line[lo:]
        wrapped.append(line)
    return wrapped or [""]


class Section:
    """Flow tables and evidence paragraphs through identically headed pages."""
    def __init__(self, c, section, title, subtitle, source="Source  /  instruction-assisted results", url=RESULTS):
        self.c = c
        self.header = (section, title, subtitle, source, url)
        self.start()

    def start(self):
        page(self.c, *self.header)
        self.y = max(193, 157 + 17 * len(simpleSplit(self.header[2], "Helvetica", 12, RIGHT - LEFT)))
        self.top = self.y

    def ensure(self, height):
        if self.y + height > 718:
            self.c.showPage()
            self.start()
            return True
        return False

    def body(self, value, size=10.7, color=INK, gap=9, font="Helvetica"):
        leading = size + 3.7
        for line in lines(self.c, value, RIGHT - LEFT, size, font):
            self.ensure(leading)
            text(self.c, LEFT, self.y, line, size, color, font)
            self.y += leading
        self.y += gap

    def subhead(self, value):
        self.ensure(54)
        rule(self.c, self.y)
        self.y += 8
        self.body(value, 13, gap=5, font="Helvetica-Bold")

    def table(self, headers, widths, rows, numeric=()):
        if abs(sum(widths) - (RIGHT - LEFT)) > 1:
            raise ValueError("Table columns do not fit the report.")
        header = [lines(self.c, h, w - 12, 8.1, "Helvetica-Bold") for h, w in zip(headers, widths)]
        header_height = 9 + 10.2 * max(map(len, header))

        def paint(content, cells, is_header=False):
            size, leading = (8.1, 10.2) if is_header else (10, 12.5)
            font = "Helvetica-Bold" if is_header else "Helvetica"
            height = 9 + leading * max(map(len, content))
            if is_header:
                box(self.c, LEFT, self.y, RIGHT - LEFT, height, LIGHT)
            x = LEFT
            for i, (column, width) in enumerate(zip(content, widths)):
                color = MUTED if is_header else INK
                if str(cells[i]).endswith((" faster", " less")):
                    color = TEAL
                elif str(cells[i]).endswith((" slower", " more")):
                    color = RUST
                for j, line in enumerate(column):
                    y = self.y + 4 + j * leading
                    if i in numeric:
                        right_text(self.c, x + width - 6, y, line, size, color, font)
                    else:
                        text(self.c, x + 6, y, line, size, color, font)
                x += width
            self.y += height
            if not is_header:
                rule(self.c, self.y)

        self.ensure(header_height + 21.5)
        paint(header, headers, True)
        for row in rows:
            content = [lines(self.c, v, w - 12, 10) for v, w in zip(row, widths)]
            count = max(map(len, content))
            if count * 12.5 + 9 <= 718 - self.top - header_height and self.ensure(count * 12.5 + 9):
                paint(header, headers, True)
            offset = 0
            while offset < count:
                if self.ensure(21.5):
                    paint(header, headers, True)
                end = min(count, offset + int((718 - self.y - 9) // 12.5))
                chunk = [col[offset:end] for col in content]
                if offset and not chunk[0] and len(content[0]) == 1:
                    chunk[0] = content[0]
                paint(chunk, row)
                offset = end
        self.y += 9

    def finish(self):
        self.c.showPage()


def validate_replication(info, inputs):
    seen = set()
    for case in info["cases"]:
        if case["id"] in seen or set(case["arms"]) != {"control", "develop"}:
            raise ValueError(f"Duplicate case or incomplete arm pair for {case['id']}")
        if case.get("cohort") not in COHORTS or case["cohort"] != inputs[case["id"]]["cohort"]:
            raise ValueError(f"Missing or conflicting source-packet cohort for {case['id']}")
        seen.add(case["id"])
        for arm in case["arms"].values():
            for field in METRICS:
                value = arm[field]
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                           or not math.isfinite(value) or value < 0):
                    raise ValueError(f"Invalid {field} for {case['id']}")
            parts = [arm[f] for f in ("uncached_input", "cached_input", "output")]
            if None not in parts and arm["total_context"] is not None and sum(parts) != arm["total_context"]:
                raise ValueError(f"Inconsistent context total for {case['id']}")
            if type(arm["implementation_pass"]) not in (bool, type(None)):
                raise ValueError(f"Unknown implementation outcome for {case['id']}")


def measure(value, metric):
    if value is None:
        return "Unavailable"
    if metric == "seconds":
        return f"{value:,.1f} s"
    return f"{value:,}"


def difference(pair, metric):
    a, b = (pair[k][metric] for k in ("control", "develop"))
    if a is None or b is None:
        return "Unavailable"
    if a == b:
        return "Same"
    direction = ("faster" if b < a else "slower") if metric == "seconds" else ("less" if b < a else "more")
    if a == 0:
        return f"{measure(abs(b-a), metric)} {direction}"
    return f"{abs(delta(a, b)):.1f}% {direction}"


def combined(pairs):
    def total(arm, field):
        items = [pair[arm][field] for pair in pairs]
        return sum(items) if items and None not in items else None
    return {arm: {key: total(arm, key) for key in METRICS} for arm in ("control", "develop")}


def quality_label(arm):
    # Lack of an applicable patch is a submitted-arm outcome with no test score.
    if arm["artifact_applicable"] is False and arm["implementation_pass"] is False:
        return "No patch"
    return {True: "Pass", False: "Fail", None: "Unresolved"}[arm["implementation_pass"]]


def passed(cases, arm):
    yes = sum(case["arms"][arm]["implementation_pass"] is True for case in cases)
    unknown = sum(case["arms"][arm]["implementation_pass"] is None for case in cases)
    return f"{yes}/{len(cases)}" + (f" ({unknown} unresolved)" if unknown else "")


def paired_tasks(runs):
    return f"{len(runs)} paired " + ("task" if len(runs) == 1 else "tasks")


def compiler_finding(observations):
    arms = observations.get("runner", {})
    if set(arms) != {"control", "develop"} or any(a.get("suites") for a in arms.values()):
        return None
    logs = {arm: row.get("post_blind_compiler_diagnostics", {}) for arm, row in arms.items()}
    if not all(any("TS6133" in d and "inspectTarget" in d for d in log.get("primary", {}).get("diagnostics", []))
               for log in logs.values()):
        return None
    additional = sum("TS7006" in d for d in logs["develop"].get("authored", {}).get("diagnostics", []))
    finding = "Both runner-space builds stopped on the unused inspectTarget import (TS6133). "
    if additional:
        finding += f"Develop's test code also had {additional} implicit-any errors (TS7006). "
    return finding + "Neither arm reached a runtime suite."


def dashboard(c, cases, pairs, groups, compiler):
    historic_selected = {case["label"] for case in cases}
    selected = [pair for name, pair in pairs if name in historic_selected]
    flow = Section(c, "Scorecard   /   26–27 October", "What changed with Develop?",
                   f"Only {len(selected)} of {len(cases)} selected tasks completed both repository-workflow arms. "
                   f"Both arms passed those tasks. The {sum(map(len, groups.values()))} new pairs used source packets in a separate experiment. "
                   "Percentages compare Develop with its matched control.")
    link(c, LEFT + 236, 742, "Source  /  historical ledger", ISSUE + "#evidence-f", 9.5)
    summary_rows = []
    for name, n, values in [("Historical · selected", len(selected), combined(selected)),
                            ("Historical · all pairs", len(pairs), combined([p for _, p in pairs]))]:
        summary_rows.append((name, f"{n}/{n} each", difference(values, "seconds"), difference(values, "total_context")))
    for cohort, runs in groups.items():
        totals = combined([case["arms"] for case in runs])
        control, develop = (passed(runs, arm) for arm in ("control", "develop"))
        outcomes = f"{control} each" if control == develop else f"C {control} · D {develop}"
        summary_rows.append((COHORTS[cohort], outcomes,
                             difference(totals, "seconds"), difference(totals, "total_context")))
    flow.table(("TASK SET", "TASKS PASSED¹", "ELAPSED TIME", "CONTEXT TOKENS"),
               (154, 121, 124, 125), summary_rows)
    flow.body("¹ The two historical selected pairs are included in the five-pair total. "
              "C = control, D = Develop. Billed dollars are unavailable.",
              9.3, MUTED, gap=8)
    flow.subhead("Historical tasks")
    flow.table(("PROJECT / SLATE", "QUALITY · BOTH", "ELAPSED TIME", "CONTEXT TOKENS"),
               (154, 121, 124, 125), [
                   (f"{name} · {'selected' if name in historic_selected else 'supplemental'}",
                    f"Pass · {EVIDENCE[name][0]}", difference(pair, "seconds"), difference(pair, "total_context"))
                   for name, pair in pairs])
    flow.subhead("What to test next")
    historical = combined(selected)
    flow.body("Test shorter review inputs at fixed review depth. On the two selected historical tasks, "
              f"Develop used {difference(historical, 'total_context')} context and was "
              f"{difference(historical, 'seconds')}. Keep the change only if blind review and "
              "acceptance evidence hold up.", 10.5)
    if compiler:
        flow.body("Try one compiler report before the final response. Both runner-space patches applied, "
                  "but an unused import stopped both builds. Test whether equal access to diagnostics "
                  "improves the number of patches that reach runtime checks.", 10.5)
    else:
        flow.body("In the new trials, models proposed exact edits from a source packet. Compare artifact "
                  "application, behavior, time and tokens separately for tasks using recovered or replacement "
                  "fixtures. The next page shows each new task and its test scope.", 10.5)
    flow.finish()


def new_tasks(c, cases, groups, inputs):
    published = {case["case"] for case in cases}
    flow = Section(c, "Instruction-assisted   /   27 October", "How did the new tasks compare?",
                   "Each new task had one control and one Develop arm. Quality is the observed case-specific "
                   "result. Elapsed time and context show Develop's change from its paired control.")
    scope = {
        "recovered-fixture": "These tasks reused archived behavior checks. Workers received source excerpts, "
                             "and a separate evaluator applied and tested their final edits.",
        "replacement-fixture": "These tasks used newly written hidden behavior checks, sealed before the "
                               "arms ran. Their measurements have their own denominator.",
    }
    for cohort, runs in groups.items():
        flow.subhead(f"{COHORTS[cohort]}  /  {paired_tasks(runs)}")
        flow.body(scope[cohort], 10, MUTED, gap=5)
        rows = []
        for case in runs:
            slate = "selected" if inputs[case["id"]]["case"] in published else "supplemental"
            scores = ["No patch" if quality_label(case["arms"][a]) == "No patch"
                      else printable(case["arms"][a]["quality"]) for a in ("control", "develop")]
            rows.append((f"{case['name']} · {slate}", case["stratum"], " · ".join(scores),
                         difference(case["arms"], "seconds"), difference(case["arms"], "total_context")))
        flow.table(("PROJECT / SLATE", "STRATUM", "CONTROL / DEVELOP", "ELAPSED TIME", "CONTEXT TOKENS"),
                   (112, 76, 134, 101, 101), rows)
    runs = [case for group in groups.values() for case in group]
    if any(not arm["artifact_applicable"] for case in runs for arm in case["arms"].values()):
        flow.body("No patch means the edits could not be tested. Those attempts still contributed time and usage.", 9.8, MUTED)
    site = next((case for case in runs if case["id"] == "site"), None)
    if site and any(arm["implementation_pass"] is None for arm in site["arms"].values()):
        flow.body("Personal site  /  " + site["suite_note"], 9.8, MUTED)
    flow.finish()


def packet_resources(c, cohort, runs):
    flow = Section(c, COHORTS[cohort] + "   /   27 October", "Time and tokens in the new trials",
                   f"{COHORTS[cohort]} · {paired_tasks(runs)}. "
                   "Each row counts the planning, implementation, review and final response for one arm. "
                   "The tables include unsuccessful submissions. Aggregate percentages compare sums across tasks.")
    pairs = [(r["name"], r["arms"]) for r in runs]
    totals = combined([arms for _, arms in pairs])
    resource_rows = []
    for name, pair in [*pairs, (f"{len(runs)}-pair sum", totals)]:
        for i, arm in enumerate(("control", "develop")):
            resource_rows.append((name if i == 0 else "", arm.title(),
                                  *(measure(pair[arm][metric], metric) for metric in METRICS)))
    flow.table(("PROJECT", "ARM", "ELAPSED", "UNCACHED IN", "CACHED IN", "OUTPUT", "CONTEXT"),
               (95, 57, 68, 80, 80, 62, 82), resource_rows, (2, 3, 4, 5, 6))
    types = (("uncached_input", "uncached input"), ("cached_input", "cached input"), ("output", "output"))
    if all(totals[a][k] is not None for k, _ in types for a in ("control", "develop")):
        changes = [f"{totals['develop'][k] - totals['control'][k]:+,} {label}" for k, label in types]
        flow.body(f"Develop minus control across these tasks was {', '.join(changes)} tokens.", 10.3, gap=4)
    flow.body("Context = uncached input + cached input + output, including reasoning. These counts show "
              "model workload. A dollar figure would require billable usage and applicable rates.", 10, MUTED)
    charts = (("seconds", "Elapsed time", LEFT + 168, LEFT + 287),
              ("total_context", "Context tokens", LEFT + 369, RIGHT - 5))
    changes = {(name, metric): change(pair, metric)[1] for name, pair in pairs for metric, *_ in charts
               if pair["control"][metric] and pair["develop"][metric] is not None}
    if changes:
        flow.ensure(55 + len(pairs) * 20)
        flow.subhead("Time and context relative to Control")
        for _, label, zero, _ in charts:
            text(c, zero - 50, flow.y, label, 9.2, MUTED, "Helvetica-Bold")
        flow.y += 17
        maximum = max(abs(value) for value in changes.values()) or 1
        for name, pair in pairs:
            text(c, LEFT + 4, flow.y, name, 10)
            for metric, _, zero, end in charts:
                value = changes.get((name, metric))
                if value is not None:
                    w = 50 * value / maximum
                    box(c, zero, flow.y - 1, 0.7, 17, LINE)
                    box(c, zero + min(w, 0), flow.y + 3, abs(w), 7, TEAL if value < 0 else RUST)
                right_text(c, end, flow.y, difference(pair, metric), 9.5, INK)
            flow.y += 20
    flow.finish()


def phase_totals(runs, phase_rows):
    included = {r["id"] for r in runs}
    totals = {}
    for row in phase_rows:
        if row["case"] not in included:
            continue
        key = (row["case"], row["condition"], row["phase"])
        if key in totals:
            raise ValueError(f"Duplicate phase receipt for {key}.")
        totals[key] = int(row["total_context"])
    order = ("plan", "plan-intent", "plan-artifact", "implement", "evidence-intent", "evidence-artifact", "seal")
    by_phase = {phase: {} for phase in order}
    for arm in ("control", "develop"):
        for phase in order:
            values = [totals.get((r["id"], arm, phase)) for r in runs]
            by_phase[phase][arm] = sum(values) if values and None not in values else None
        for r in runs:
            values = [totals.get((r["id"], arm, phase)) for phase in order]
            total = r["arms"][arm]["total_context"]
            if None not in values and total is not None and total != sum(values):
                raise ValueError(f"Phase context does not reconcile for {r['id']} / {arm}.")
    return by_phase


def packet_context(c, cohort, runs, phases, phase_rows):
    flow = Section(c, COHORTS[cohort] + "   /   27 October", "Which phases used the most context?",
                   f"{COHORTS[cohort]} · {paired_tasks(runs)}. "
                   "Every call received the source material and instructions for its arm. The figures below count "
                   "uncached input, cached input and output summed across tasks. Concurrent calls each contribute usage.",
                   "Source  /  phase usage ledger", RESULTS.replace("results.json", "phase-usage.csv"))
    names = {"plan": "Planning", "plan-intent": "Plan review · intent", "plan-artifact": "Plan review · artifact",
             "implement": "Implementation", "evidence-intent": "Final review · intent",
             "evidence-artifact": "Final review · artifact", "seal": "Final response"}
    phase_display = []
    for phase, values in phases.items():
        a, b = values["control"], values["develop"]
        phase_display.append((names[phase], measure(a, "tokens"), measure(b, "tokens"),
                              f"{b-a:+,}" if a is not None and b is not None else "Unavailable"))
    flow.table(("PHASE", "CONTROL", "DEVELOP", "CHANGE IN TOKENS"),
               (166, 110, 110, 138), phase_display, (1, 2, 3))
    case_ids = {r["id"] for r in runs}
    recorded = [row for row in phase_rows if row["case"] in case_ids]
    acknowledgments = sum(r["procedure_acknowledged"] == "True" for r in recorded)
    observed_tools = [r["observed_tool_items"] for r in recorded]
    tool_count = sum(map(int, observed_tools)) if recorded and all(x.isdigit() for x in observed_tools) else None
    flow.body(f"The ledger contains {len(recorded)} of {len(runs)*14} expected phase receipts. "
              f"{acknowledgments} acknowledge the instructions. Recorded tool items total "
              f"{measure(tool_count, 'items')}.", 10, MUTED)
    flow.subhead("External and user-owned tasks")
    rows = []
    for stratum in dict.fromkeys(r["stratum"] for r in runs):
        subset = [r for r in runs if r["stratum"] == stratum]
        pair = combined([r["arms"] for r in subset])
        rows.append((stratum, ", ".join(r["name"] for r in subset),
                     f"{passed(subset, 'control')} · {passed(subset, 'develop')}",
                     difference(pair, "seconds"), difference(pair, "total_context")))
    flow.table(("STRATUM", "PROJECTS", "PASS · C / D", "ELAPSED TIME", "CONTEXT TOKENS"),
               (93, 137, 90, 102, 102), rows)
    flow.body("Each pass count uses all released tasks in that group. User-owned projects carry additional "
              "prior-context risk. These small groups describe the observed tasks.", 10, MUTED)
    flow.finish()


def packet_case(c, case, inputs):
    prepared = inputs[case["id"]]
    flow = Section(c, COHORTS[case["cohort"]] + "   /   27 October", "What each arm produced",
                   printable(case["name"]) + "   /   " + prepared["case"])
    link(c, LEFT + 236, 742, "Source  /  test observations", RESULTS.replace("results.json", "observations.json"))
    owner, repository, pull = prepared["case"].split("/")
    link(c, LEFT, flow.y, f"Merged human reference  /  {owner}/{repository} #{pull}",
         f"https://github.com/{owner}/{repository}/pull/{pull}", 9.5)
    flow.y += 19
    flow.body("User-owned project · prior exposure unknown" if "user" in str(case["stratum"]).lower()
              else "External project · possible prior exposure", 9.5, TEAL, gap=5, font="Helvetica-Bold")
    order = " then ".join(a.title() for a in prepared["arm_order"])
    flow.body(f"{prepared['packet_method']} · {prepared['packet_bytes']:,} packet bytes · "
              f"{prepared['minutes_per_arm']} min per arm · {order}", 9.5, MUTED, gap=5)
    flow.body(prepared["requirement"])
    flow.table(("BASE REFERENCE", "GOLD REFERENCE", "BLIND CORRECTNESS", "BLIND MAINTAINABILITY"),
               (136, 136, 123, 129), [(printable(case["base_reference"]), printable(case["gold_reference"]),
                                       prose(case["blind"]["correctness"]), prose(case["blind"]["maintainability"]))])
    flow.subhead("Candidate results")
    outcomes = []
    for arm in ("control", "develop"):
        data = case["arms"][arm]
        label = quality_label(data)
        if label == "No patch":
            score = "No patch · no tests"
            detail = data.get("application_reason") or "The final edits could not be applied."
        else:
            score = f"{label} · {printable(data['quality'])}"
            detail = data["quality_detail"]
        outcomes.append((arm.title(), score, prose(detail)))
    flow.table(("ARM", "OUTCOME", "TEST EVIDENCE OR APPLICATION RESULT"), (69, 134, 321), outcomes)
    flow.subhead("What the evidence covers")
    flow.body(prose(case["interpretation"]))
    if case.get("suite_note"):
        flow.body(prose(case["suite_note"]), 10, MUTED)
    flow.finish()


def packet_judgments(c, cohort, runs, judgments, compiler):
    flow = Section(c, COHORTS[cohort] + "   /   27 October", "What did the blind reviewers find?",
                   f"{COHORTS[cohort]} · {paired_tasks(runs)}. "
                   "Two reviewers separately assessed correctness and maintainability. "
                   "The labels A and B were assigned anonymously. The key below identifies the arms for each judgment.",
                   "Source  /  independent blind judgments", RESULTS.replace("results.json", "blind-judgments.json"))
    for case in runs:
        flow.subhead(case["name"])
        for lane, label in (("correctness", "Correctness"), ("maintainability", "Maintainability and tests")):
            flow.ensure(48)
            flow.body(f"{label}  /  {printable(case['blind'][lane]).capitalize()}",
                      10.8, TEAL, gap=3, font="Helvetica-Bold")
            review = next((j for j in judgments if j["case"] == case["id"] and j["lane"] == lane), None)
            if not review:
                flow.body("The public results contain the preference only.", 9.8, MUTED)
                continue
            mapping = review["anonymous_key"]
            flow.body(f"A = {mapping['A']}   ·   B = {mapping['B']}", 9.3, MUTED, gap=3)
            basis = review["observations"].get("basis")
            if basis:
                flow.body(prose(basis))
            if lane == "maintainability" and review["observations"].get("test_coverage"):
                flow.body(review["observations"]["test_coverage"], 10, MUTED)
        if case["id"] == "runner" and compiler:
            flow.body("Compiler logs checked after blind review  /  " + compiler, 10, INK)
    flow.finish()


def packet_method(c, info, procedure, manifest, inputs):
    flow = Section(c, "Instruction-assisted   /   27 October", "How the new trials ran",
                   "Each arm received excerpts from the same frozen base and returned exact text edits. "
                   "The model could read its packet and peer feedback. It had no repository tools or test results.",
                   "Source  /  frozen instruction-assisted procedure", RESULTS.replace("results.json", "procedure.json"))
    flow.subhead("Treatment and control")
    flow.body(f"Both used {procedure['model']} at {procedure['effort']} effort and the same task requirement, "
              "base packet, output schema, time limit and review roles. Develop also received the selected "
              f"frozen Develop instructions, {procedure['treatment_source']['bytes_per_phase']:,} bytes on each "
              "of seven calls. Each phase had to return the supplied instruction receipt.")
    flow.subhead("Seven model calls in each arm")
    flow.body("A fresh thread produced a plan. Two planning reviewers independently checked intent and the "
              "proposed implementation. A fourth thread proposed edits. Two evidence reviewers inspected the "
              "proposal. A final thread sealed the returned edits. The two reviewers ran concurrently at each checkpoint.")
    flow.subhead("What counted as a pass")
    flow.body("Anonymous artifacts went to separate evaluators. They first applied the submitted edits to the "
              "untouched base. An empty or non-applying artifact earned no implementation credit and received no "
              "candidate test score. Applied artifacts faced the case's admitted checks. A separate blind judgment "
              "compared correctness and maintainability. Cases use different suites and thresholds.")
    flow.subhead("Timing, scope and reference limits")
    flow.body("Each task ran once per arm. Elapsed time captures the model and review workflow. The resource table "
              "uses the reported arm usage. Setup, evaluator runs and independent judging are outside those totals. "
              "The human reference contributes behavior and code, with unknown implementation time and usage.")
    flow.body("Gold is the original merged change. Prior exposure varies by project. Small, purposefully selected "
              "samples and one pair per task limit conclusions about other work. The recovered and replacement "
              "fixtures use different acceptance evidence. Each has its own score and resource summary. Historical "
              "and source-packet execution also differ in tool access, context and review procedure.")
    flow.finish()

    flow = Section(c, "Coverage   /   27 October", "Which work remains open?",
                   "The original eight-case slate and its retry allowances belong to the historical full workflow. "
                   "The new source-packet runs measure a separate task with different tools and instructions.")
    flow.subhead("Full native workflow")
    flow.body(info["native_status"])
    flow.subhead("Selected tasks missing a full native pair")
    scored = {inputs[case["id"]]["case"]: case for case in info["cases"]}
    state_rows = []
    for original in manifest:
        if original["disposition"] == "Complete":
            continue
        case = scored.get(original["case"])
        status = " · ".join(quality_label(case["arms"][a]) for a in ("control", "develop")) if case else "No scored pair"
        state_rows.append((original["label"], original["disposition"],
                           COHORTS[case["cohort"]] if case else "Pending or held", status))
    flow.table(("PROJECT", "26 OCT NATIVE STATE", "NEW PACKET FIXTURES", "CONTROL / DEVELOP"),
               (113, 119, 148, 144), state_rows)
    flow.body("Requests and Cobra completed historical native pairs. The table tracks the six other "
              "selected tasks. A new packet result leaves its native experiment open.", 10, MUTED)
    if info["holds"]:
        flow.subhead("Cases on hold")
        for hold in info["holds"]:
            flow.body(hold["name"], 10.7, TEAL, gap=2, font="Helvetica-Bold")
            flow.body(hold["reason"])
    flow.finish()


def next_experiments(c, groups, phases, compiler):
    flow = Section(c, "Next experiments", "What should the next trial test?",
                   "Use fresh matched pairs, preserve failures, and change one element at a time. "
                   "The observed differences specify what to measure in a follow-up.")
    misses = {cohort: {a: sum(quality_label(r["arms"][a]) == "No patch" for r in runs)
                        for a in ("control", "develop")} for cohort, runs in groups.items()}
    if compiler:
        flow.subhead("1. Would compiler feedback help patches reach runtime tests?")
        flow.body(compiler, 10.5, gap=4)
        flow.body("On fresh TypeScript tasks, give both arms one compiler report and equal repair time. "
                  "Compare with the existing tool-free procedure. Count builds and runtime passes separately, "
                  "then compare time and tokens.", 10, MUTED)
    if any(count for arms in misses.values() for count in arms.values()):
        if not compiler:
            flow.subhead("1. Can reviewers catch edits that will not apply?")
        for cohort, counts in misses.items():
            n = len(groups[cohort])
            flow.body(f"{COHORTS[cohort]} had no applicable patch for {counts['control']}/{n} control and "
                      f"{counts['develop']}/{n} Develop submissions.", 10.5, gap=3)
        flow.body("Test one apply check and an equally budgeted repair in a separate experiment. Keep every "
                  "submitted arm in the denominator.", 10, MUTED)
    first = bool(compiler) or any(count for arms in misses.values() for count in arms.values())
    flow.subhead(f"{2 if first else 1}. Which review prompt catches incomplete behavior?")
    fmt = next((r for r in groups.get("recovered-fixture", []) if r["id"] == "fmt"), None)
    if fmt:
        flow.body(f"Both fmt patches applied. Control passed {fmt['arms']['control']['quality']} and Develop "
                  f"passed {fmt['arms']['develop']['quality']}. Both still failed on bounded output and "
                  "surrounding literal text.", 10.5, gap=4)
    flow.body("On fresh C++ tasks, compare current Develop with a short review prompt to trace the change "
              "through each public entry point. Freeze independent checks for boundary behavior before the arms run.",
              10, MUTED)
    flow.subhead(f"{3 if first else 2}. Can a shorter review preserve quality?")
    flow.body("The four review calls per new task accounted for the following context.", 10.5, gap=4)
    review_rows = []
    for cohort, by_phase in phases.items():
        review = [by_phase[p] for p in ("plan-intent", "plan-artifact", "evidence-intent", "evidence-artifact")]
        values = [sum(row[arm] for row in review) if all(row[arm] is not None for row in review) else None
                  for arm in ("control", "develop")]
        review_rows.append((COHORTS[cohort], len(groups[cohort]), *(measure(v, "tokens") for v in values)))
    flow.table(("FIXTURES", "PAIRS", "CONTROL REVIEW TOKENS", "DEVELOP REVIEW TOKENS"),
               (156, 54, 155, 159), review_rows, (1, 2, 3))
    flow.body("Test shorter Develop review inputs at the same review depth. Compare phase time and usage. "
              "Require unchanged acceptance and blind-review quality, then compare resource use.",
              10, MUTED)
    flow.finish()


def main(result_path=None, output_path=None):
    cases = rows("cases.csv")
    ledger = rows("ledger.csv")
    public = HERE / "replication"
    replication = json.loads((result_path or public / "results.json").read_text())
    inputs = json.loads((public / "inputs.json").read_text())
    procedure = json.loads((public / "procedure.json").read_text())
    judgments = json.loads((public / "blind-judgments.json").read_text())
    observations = json.loads((public / "observations.json").read_text())
    validate_replication(replication, inputs)
    groups = {cohort: [case for case in replication["cases"] if case["cohort"] == cohort] for cohort in COHORTS}
    groups = {cohort: runs for cohort, runs in groups.items() if runs}
    phase_rows = rows("replication/phase-usage.csv")
    phases = {cohort: phase_totals(runs, phase_rows) for cohort, runs in groups.items()}
    paired = {}
    for row in ledger:
        if row["paired_eligible"] == "True":
            pair = paired.setdefault(row["case"], {})
            if row["arm"] in pair or row["status"] != "completed" or row["usage"] != "complete_native":
                raise ValueError(f"Invalid eligible row for {row['case']} / {row['arm']}")
            usage = {metric: float(row[metric]) if metric == "seconds" else int(row[metric]) for metric in METRICS}
            if usage["total_context"] != usage["uncached_input"] + usage["cached_input"] + usage["output"]:
                raise ValueError(f"Inconsistent context total for {row['case']} / {row['arm']}")
            pair[row["arm"]] = usage
    labels = {"psf/requests/7505": "Requests", "spf13/cobra/2397": "Cobra",
              "encode/starlette/3718": "Starlette", "pallets/flask/6096": "Flask",
              "gohugoio/hugo/15474": "Hugo"}
    if labels.keys() != paired.keys() or any(p.keys() != {"control", "develop"} for p in paired.values()):
        raise ValueError("The ledger does not contain the five historical pairs described here.")
    pairs = [(label, paired[case]) for case, label in labels.items()]
    totals = sum_arms(pairs)
    rl_config.useA85 = False  # Keep compressed PDF streams binary.
    c = Canvas(str(output_path or HERE / "report.pdf"), pagesize=letter, invariant=1, pageCompression=1)
    c.setTitle("Develop benchmark | Historical and instruction-assisted trials")
    c.setCreator("Develop benchmark report renderer")
    c.setAuthor("law-config")
    c.setSubject("Quality, elapsed time and usage across historical, recovered-fixture and replacement-fixture trials")
    compiler = compiler_finding(observations) if any(r["id"] == "runner" for r in replication["cases"]) else None
    dashboard(c, cases, pairs, groups, compiler)
    new_tasks(c, cases, groups, inputs)
    next_experiments(c, groups, phases, compiler)
    for cohort, runs in groups.items():
        packet_resources(c, cohort, runs)
        packet_context(c, cohort, runs, phases[cohort], phase_rows)
        for case in runs:
            packet_case(c, case, inputs)
        packet_judgments(c, cohort, runs, judgments, compiler)
    packet_method(c, replication, procedure, cases, inputs)
    summary(c, cases, pairs, totals)
    method(c)
    costs(c, pairs, totals)
    quality(c, cases, pairs)
    remaining(c, cases)
    implications(c, pairs, ledger)
    c.save()


if __name__ == "__main__":
    main()
