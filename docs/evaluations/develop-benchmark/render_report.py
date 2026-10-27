"""Render the bounded historical benchmark from its adjacent, public data files."""

import csv
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas


HERE = Path(__file__).resolve().parent
ISSUE = "https://github.com/justinthelaw/law-config/issues/71"
UPDATE = ISSUE + "#issuecomment-6434762307"
WIDTH, HEIGHT = letter
LEFT, RIGHT = 44, WIDTH - 44
INK, MUTED, LINE = "#172D36", "#405963", "#CED9D9"
TEAL, PALE, BLUE = "#006B60", "#E7F4F0", "#456581"


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


def page(c, number, section, title, subtitle, source, url):
    text(c, LEFT, 30, "DEVELOP  /  EVALUATION NOTES", 9, TEAL, "Helvetica-Bold")
    text(c, RIGHT - 113, 30, "26-27 OCTOBER 2026", 9, MUTED)
    rule(c, 49)
    text(c, LEFT, 72, section.upper(), 10, TEAL, "Helvetica-Bold")
    text(c, LEFT, 96, title, 28, INK, "Helvetica-Bold")
    paragraph(c, LEFT, 142, subtitle, size=12, leading=17, color=MUTED)
    rule(c, 730)
    link(c, LEFT, 742, source, url)
    text(c, RIGHT - 36, 742, f"{number:02d} / 06", 9, MUTED)


def heading(c, y, value):
    text(c, LEFT, y, value, 15, INK, "Helvetica-Bold")


def note(c, y, title, body):
    text(c, LEFT, y, title, 12, INK, "Helvetica-Bold")
    return paragraph(c, LEFT, y + 20, body, size=10.8, leading=14.5)


def delta(control, develop):
    return (develop / control - 1) * 100


def summary(c, cases, totals):
    page(c, 1, "01   Findings", "What did Develop change?",
         "Both arms passed their case-specific acceptance checks in all five completed "
         "historical pairs. None showed a production-behavior advantage for Develop.",
         "Source  /  historical results and case selection", ISSUE + "#evidence-g:~:text=final%20selected%20sources")
    for x, key, label in [(LEFT, "seconds", "release-to-final time"),
                          (320, "total_context", "total context tokens")]:
        box(c, x, 214, 248, 94, PALE)
        pct = delta(totals["control"][key], totals["develop"][key])
        text(c, x + 15, 221, f"+{pct:.1f}%", 32, TEAL, "Helvetica-Bold")
        text(c, x + 16, 270, label, 12, INK)
    paragraph(c, LEFT, 323, "Develop relative to control, using summed measurements across "
              "five cases. Time includes review and waiting. Context includes cached input.", color=MUTED)
    heading(c, 400, "Two of eight selected cases are complete")
    step = (RIGHT - LEFT + 4) / len(cases)
    for i, case in enumerate(cases):
        x = LEFT + step * i
        complete = case["disposition"] == "Complete"
        box(c, x, 436, step - 4, 23, TEAL if complete else LINE)
        text(c, x + 6, 441, f"{i + 1:02d}", 9,
             "#FFFFFF" if complete else MUTED, "Helvetica-Bold")
    paragraph(c, LEFT, 475, "01-02  Requests and Cobra.     03-08  Six cases still lack valid pairs.",
              size=10.5, color=MUTED)
    rule(c, 520)
    note(c, 546, "Which five cases contributed to the totals?",
         "Requests and Cobra are in the final slate. Starlette, Flask and Hugo are supplemental "
         "historical pairs. Each supplies one paired observation. All five are Python or Go projects.")
    note(c, 629, "How far can the findings travel?",
         "The target changed from 20 cases to eight after some outcomes were known. Roux chose "
         "the design and interpreted the results. They warrant independent reassessment.")
    c.showPage()


def method(c):
    page(c, 2, "02   Method", "One task, two isolated arms",
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


def bars(c, x, title, unit, metric, divisor, maximum, ticks, pairs):
    text(c, x, 204, title, 13, INK, "Helvetica-Bold")
    text(c, x, 225, unit, 9.5, MUTED)
    span = 143
    for tick in ticks:
        gx = x + span * tick / maximum
        box(c, gx, 258, 0.5, 275, LINE)
        text(c, gx - 2, 241, str(tick), 8, MUTED)
    for i, (_, pair) in enumerate(pairs):
        for offset, arm, color in [(0, "control", BLUE), (18, "develop", TEAL)]:
            value = float(pair[arm][metric]) / divisor
            if value > maximum:
                raise ValueError(f"Chart scale exceeded for {metric}: {value}")
            width = span * value / maximum
            top = 269 + i * 56 + offset
            box(c, x, top, width, 9, color)
            text(c, x + width + 4, top - 2, f"{value:.2f}", 8.5, INK)


def costs(c, pairs, totals):
    page(c, 3, "03   Measured resources", "What did each pair use?",
         "The same five historical pairs appear in both charts. Each bar starts at zero. "
         "Time and context have separate scales.",
         "Source  /  all 30 historical ledger rows", ISSUE + "#evidence-f:~:text=final%20complete%2030-row%20metric%20ledger")
    bars(c, 137, "Elapsed time", "Minutes per arm", "seconds", 60, 15, [0, 5, 10, 15], pairs)
    bars(c, 368, "Total context", "Millions of tokens per arm", "total_context",
         1_000_000, 3, [0, 1, 2, 3], pairs)
    for i, (name, _) in enumerate(pairs):
        text(c, LEFT, 275 + i * 56, name, 10.5, INK, "Helvetica-Bold")
    for x, color, label in [(LEFT, BLUE, "Control (upper bar)"), (205, TEAL, "Develop (lower bar)")]:
        box(c, x, 553, 14, 8, color)
        text(c, x + 20, 549, label, 10, MUTED)
    rule(c, 578)
    for x, label in [(LEFT, "FIVE-PAIR SUM"), (156, "SECONDS"), (240, "UNCACHED IN"),
                     (353, "CACHED IN"), (452, "OUTPUT"), (515, "CONTEXT")]:
        text(c, x, 594, label, 8, MUTED, "Helvetica-Bold")
    for i, arm in enumerate(("control", "develop")):
        row = totals[arm]
        y = 619 + 24 * i
        text(c, LEFT, y, arm.title(), 10.5, INK, "Helvetica-Bold")
        text(c, 156, y, f"{row['seconds']:,.1f}", 10)
        for x, key in [(240, "uncached_input"), (353, "cached_input"),
                       (452, "output"), (515, "total_context")]:
            text(c, x, y, f"{int(row[key]):,}", 10)
    paragraph(c, LEFT, 683, "Output includes reasoning. Totals exclude coordinator, grader and "
              "human gold usage, which are unavailable. The ledger does not establish billed cost.",
              size=10, leading=13.5, color=MUTED)
    c.showPage()


def quality(c):
    page(c, 4, "04   Quality evidence", "How did the patches compare?",
         "Acceptance is measured per case. Qualitative preferences below come from the historical "
         "blind assessments. Different test sets make pooled test counts misleading.",
         "Source  /  case-level acceptance and judgments", ISSUE + "#evidence-a:~:text=historical%20partial%20report")
    entries = [
        ("Requests", "SELECTED  /  7 OF 7",
         "Both handled file-like proxies and passed 243 socket-free native checks, with 13 skipped. "
         "The assessors found mixed maintenance and test tradeoffs. Full HTTP coverage was incomplete."),
        ("Cobra", "SELECTED  /  13 LEAF SUBCASES",
         "Both satisfied the validator requirement and passed the full Go suite. Gold retained more "
         "contextual diagnostics. The two agents added complementary regression tests."),
        ("Starlette", "SUPPLEMENTAL  /  12 OF 12",
         "Both agents preserved a repeated-slash root-path boundary that gold broke. Their production "
         "fixes matched. The improvement over gold was reproduced after the trials."),
        ("Flask", "SUPPLEMENTAL  /  17 OF 17",
         "Both preserved explicit host and port overrides with an invalid configured port. Gold raised "
         "an error in this post-hoc check. Assessors modestly preferred Develop's regression tests."),
        ("Hugo", "SUPPLEMENTAL  /  6 API CASES AND 1 REAL TEMPLATE",
         "Runtime behavior matched across both arms. Each improved template regression coverage over "
         "gold. Assessors favored Develop's additional pipeline and conversion boundary tests."),
    ]
    for i, (name, label, detail) in enumerate(entries):
        y = 203 + 97 * i
        rule(c, y)
        text(c, LEFT, y + 10, name, 14.5, INK, "Helvetica-Bold")
        text(c, 156, y + 14, label, 8.5, TEAL, "Helvetica-Bold")
        paragraph(c, LEFT, y + 38, detail, size=10.7, leading=14.5)
    paragraph(c, LEFT, 695, "Only the tested paths support these comparisons.", size=10, color=MUTED)
    c.showPage()


def remaining(c, cases):
    page(c, 5, "05   Final slate", "Where do the eight cases stand?",
         "The first five projects are external. The last three are user-owned and have prior-context "
         "risk. Each case label links to its merged gold PR.",
         "Source  /  frozen cases and admission results", ISSUE + "#evidence-g:~:text=final%20selected%20sources")
    details = {
        "Requests": "Both arms passed all seven acceptance checks.",
        "Cobra": "Both arms passed 13 leaf subcases and the full Go suite.",
        "Tokio": "No arms. Worker baseline 26/26. The new API was absent on base.",
        "fmt": "Develop partial passed 13/13. Final review hit a service limit. Control unstarted.",
        "Svelte": "No arms. Independent checks passed 8/8 on both references. Gold-derived checks went from 0/2 to 2/2.",
        "Personal site": "Offline install and build passed. Five browser projects still need runtime admission.",
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
    paragraph(c, LEFT, 688, "Six selected pairs remain. fmt and law-config each retain one fresh "
              "complete-pair retry. The separate Vue attempt exhausted its retry.", size=10, color=MUTED)
    c.showPage()


def implications(c):
    page(c, 6, "06   Decisions", "What should Develop keep or test?",
         "The record supports specific test practices and a new cost experiment. It cannot "
         "establish broader quality gains or savings from shorter reviews.",
         "Source  /  continuation outcome and recommendations", UPDATE)
    heading(c, 202, "Why the benchmark stopped")
    y = paragraph(c, LEFT, 231, "The original run paused for handoff after repeated service limits, "
                  "and its scheduled restart was canceled. The ledger retains 20 attempted arms "
                  "and 10 human references. Five attempted arms have only lower-bound usage.", size=10.8)
    y = paragraph(c, LEFT, y + 9, "The continuation recovered all 16 selected base/gold archives "
                  "and the pinned Linux CLI. Four representative Tokio role profiles passed 14 synthetic "
                  "checks each, both directly and in descendants. This covered one configuration.", size=10.8)
    y = paragraph(c, LEFT, y + 9, "Device sign-in was unavailable. The pinned app server opened a "
                  "thread without an authenticated account. Desktop builds differed from the frozen "
                  "CLI. Execution stopped at the user's request before a scored turn.", size=10.8)
    rule(c, y + 18)
    heading(c, y + 34, "Recommendations")
    for i, (title, body) in enumerate([
        ("Keep requirement-linked tests.", "Preserve boundary cases like Flask's overrides and "
         "Hugo's pipeline inputs. Measure the behavior each test protects."),
        ("Measure review costs by phase.", "Record planning, implementation and review usage "
         "before testing smaller packets in a separately versioned comparison."),
        ("Prove the fixture distinguishes the change.", "Freeze behavior criteria before release. "
         "Identify gold-derived tests and keep ambiguous pilots visible."),
        ("Qualify one complete matched pilot.", "Verify same-account inference, isolation, "
         "instruction loading and per-request accounting. Retain failures and unknowns."),
    ]):
        top = y + 68 + i * 59
        text(c, LEFT, top, f"0{i + 1}", 10, TEAL, "Helvetica-Bold")
        text(c, LEFT + 28, top - 1, title, 11, INK, "Helvetica-Bold")
        paragraph(c, LEFT + 28, top + 15, body, RIGHT - LEFT - 28, 10.1, 13)
    c.showPage()


def main():
    cases = rows("cases.csv")
    ledger = rows("ledger.csv")
    paired = {}
    for row in ledger:
        if row["paired_eligible"] == "True":
            pair = paired.setdefault(row["case"], {})
            if row["arm"] in pair or row["status"] != "completed" or row["usage"] != "complete_native":
                raise ValueError(f"Invalid eligible row for {row['case']} / {row['arm']}")
            pair[row["arm"]] = row
    labels = {"psf/requests/7505": "Requests", "spf13/cobra/2397": "Cobra",
              "encode/starlette/3718": "Starlette", "pallets/flask/6096": "Flask",
              "gohugoio/hugo/15474": "Hugo"}
    if labels.keys() != paired.keys() or any(p.keys() != {"control", "develop"} for p in paired.values()):
        raise ValueError("The ledger does not contain the five historical pairs described here.")
    pairs = [(label, paired[case]) for case, label in labels.items()]
    metrics = ("seconds", "uncached_input", "cached_input", "output", "total_context")
    totals = {arm: {metric: sum(float(pair[arm][metric]) for _, pair in pairs)
                    for metric in metrics} for arm in ("control", "develop")}
    rl_config.useA85 = False  # Keep compressed PDF streams binary.
    c = Canvas(str(HERE / "report.pdf"), pagesize=letter, invariant=1, pageCompression=1)
    c.setTitle("Develop benchmark | Matched historical comparisons")
    c.setCreator("Develop benchmark report renderer")
    c.setAuthor("law-config")
    c.setSubject("Evaluation method, historical evidence and incomplete cases for issue 71")
    summary(c, cases, totals)
    method(c)
    costs(c, pairs, totals)
    quality(c)
    remaining(c, cases)
    implications(c)
    c.save()


if __name__ == "__main__":
    main()
