"""Exercise the production review adapter through the real watcher."""

import copy
import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_monitor import Watcher
from pipeline_support import WatchError, ensure_read_only
from pipeline_test_support import FakeClock, target
from test_pipeline_checks import CoverageRunner
import watch_pipelines


BOT = {"login": "chatgpt-codex-connector[bot]", "type": "Bot", "__typename": "Bot"}


def connection(nodes=(), truncated=False):
    return {"nodes": list(nodes), "pageInfo": {"hasPreviousPage": truncated}}


def reaction(content, hour=2, identifier=1):
    return {"id": identifier, "content": content, "created_at": f"2026-01-01T0{hour}:00:00Z", "user": BOT}


def review(current, *, hour=3, state="APPROVED", body=""):
    return {"author": BOT, "state": state, "submittedAt": f"2026-01-01T0{hour}:00:00Z",
            "body": body, "url": "https://github.com/owner/project/pull/7#review", "commit": {"oid": current.head}}


def request(*, hour=2, association="OWNER", body="@codex review", identifier=77):
    return {"databaseId": identifier, "author": {"login": "person", "__typename": "User"}, "authorAssociation": association,
            "createdAt": f"2026-01-01T0{hour}:00:00Z", "bodyText": body}


def receipt(oid, hour=3):
    return {
        "author": BOT, "createdAt": f"2026-01-01T0{hour}:00:00Z",
        "includesCreatedEdit": False, "lastEditedAt": None,
        "body": (
            "<!-- codex-review-receipt:v1 -->\n\n"
            "Codex Review: Didn't find any major issues. More of your lovely PRs please.\n\n"
            f"**Reviewed commit:** `{oid}`\n\n"
            "<details> <summary>ℹ️ About Codex in GitHub</summary>\n<br/>\n\n"
            "[Your team has set up Codex to review pull requests in this repo]"
            "(https://chatgpt.com/codex/cloud/settings/general). Reviews are triggered when you\n"
            '- Open a pull request for review\n- Mark a draft as ready\n- Comment "@codex review".\n\n'
            "If Codex has suggestions, it will comment; otherwise it will react with 👍.\n\n"
            'Codex can also answer questions or update the PR. Try commenting "@codex address that feedback".\n'
            "</details>"
        ),
    }


class ReviewRunner(CoverageRunner):
    def __init__(self, current=None, *, reactions=(), request_reactions=None, reviews=(), comments=(), threads=()):
        super().__init__(current or target())
        self.pr = {"number": 7, "url": "https://github.com/owner/project/pull/7", "headRefOid": self.current.head,
                   "headRefName": self.current.branch, "headRepositoryOwner": {"login": "owner"},
                   "isCrossRepository": False, "baseRefName": "main"}
        self.reactions = list(reactions)
        self.request_reactions = request_reactions or {}
        self.resolved_receipt_sha = self.current.head
        self.selected = {
            "number": 7, "state": "OPEN", "url": self.pr["url"], "headRefName": self.current.branch,
            "headRefOid": self.current.head, "baseRefName": "main", "isCrossRepository": False,
            "headRepository": {"nameWithOwner": "owner/project"},
            "commits": {"nodes": [{"commit": {"oid": self.current.head, "committedDate": "2026-01-01T01:00:00Z"}}]},
            "comments": connection(comments), "reviews": connection(reviews), "reviewThreads": connection(threads),
        }
        self.graph_errors = None

    def __call__(self, argv, cwd=None, optional=False):
        ensure_read_only(argv)
        if argv[:3] == ["gh", "api", "graphql"]:
            self.calls.append(argv)
            return json.dumps({"data": {"repository": {"pullRequest": self.selected}}, "errors": self.graph_errors})
        if argv[:3] == ["gh", "api", f"repos/{self.current.repository}/commits/{self.current.head[:10]}"]:
            self.calls.append(argv)
            return self.resolved_receipt_sha
        if argv[:2] == ["gh", "api"] and "/reactions?" in argv[2]:
            self.calls.append(argv)
            if "/issues/comments/" in argv[2]:
                return json.dumps(self.request_reactions.get(int(argv[2].split("/")[-2]), []))
            return json.dumps(self.reactions)
        return super().__call__(argv, cwd, optional)


class ReviewSelectionTests(unittest.TestCase):
    def snapshot_cli(self, runner, *arguments):
        events = []

        def run(argv, cwd=None, optional=False, **kwargs):
            if argv == ["git", "rev-parse", "--show-toplevel"]:
                return str(runner.current.path)
            if argv == ["git", "submodule", "status", "--recursive"]:
                return ""
            return runner(argv, cwd, optional)

        with patch.object(watch_pipelines, "run_command", run), patch.object(
            Watcher, "print_event", events.append
        ):
            result = watch_pipelines.main(["--repo", str(runner.current.path), "--once", *arguments])
        return result, events

    def test_default_cli_completes_ci_without_reading_vendor_reviews(self):
        runner = ReviewRunner(comments=[request()])
        result, events = self.snapshot_cli(runner)
        self.assertEqual(result, 0)
        self.assertEqual(events[-1]["result"], "passed")
        self.assertFalse(any(call[:3] == ["gh", "api", "graphql"] for call in runner.calls))
        self.assertFalse(any(event["event"] == "review" for event in events))

    def test_selected_codex_review_does_not_accept_an_old_sha(self):
        runner = ReviewRunner(target(head="b" * 40), comments=[request()], reviews=[review(target())])
        result, events = self.snapshot_cli(runner, "--review-provider", "codex")
        self.assertEqual(result, 3)
        self.assertEqual(events[-1]["result"], "pending")
        self.assertTrue(any(event["event"] == "review" and event["status"] == "active" for event in events))

    def test_selected_codex_review_accepts_current_sha_evidence(self):
        for comments in ([], [request()]):
            with self.subTest(comments=comments):
                runner = ReviewRunner(comments=comments, reviews=[review(target())])
                result, events = self.snapshot_cli(runner, "--review-provider", "codex")
                self.assertEqual(result, 0)
                self.assertEqual(events[-1]["result"], "passed")
                self.assertTrue(any(event["event"] == "review" and event["status"] == "passed" for event in events))

    def test_selected_codex_review_blocks_without_evidence_or_request(self):
        result, events = self.snapshot_cli(ReviewRunner(), "--review-provider", "codex")
        self.assertEqual(result, 2)
        self.assertTrue(any("No current-head Codex review evidence" in event.get("reason", "") for event in events))

    def test_selected_codex_review_blocks_with_only_old_sha_evidence(self):
        runner = ReviewRunner(target(head="b" * 40), reviews=[review(target())])
        result, events = self.snapshot_cli(runner, "--review-provider", "codex")
        self.assertEqual(result, 2)
        self.assertTrue(any("No current-head Codex review evidence" in event.get("reason", "") for event in events))

    def test_selected_codex_review_blocks_without_an_open_pull_request(self):
        runner = ReviewRunner()
        runner.pr = None
        result, events = self.snapshot_cli(runner, "--review-provider", "codex")
        self.assertEqual(result, 2)
        self.assertTrue(any("requires an open pull request" in event.get("reason", "") for event in events))

    def test_default_cli_can_complete_ci_without_a_pull_request(self):
        runner = ReviewRunner()
        runner.pr = None
        result, events = self.snapshot_cli(runner)
        self.assertEqual(result, 0)
        self.assertEqual(events[-1]["result"], "passed")


class ProductionReviewTests(unittest.TestCase):
    def snapshot(self, runner):
        events = []
        monitor = Watcher([runner.current], runner=runner, emit=events.append, monitor_reviews=True)
        status = monitor.watch(once=True)
        return status, monitor, events

    def test_comment_receipt_completes_the_requested_review_without_reactions(self):
        current = target(head="a5f445178faeceaf9b496a9fae1fb930813de4a6")
        for oid, apostrophe in ((current.head[:10], "'"), (current.head, "\u2019")):
            with self.subTest(oid=oid):
                evidence = receipt(oid)
                evidence["body"] = evidence["body"].replace("Didn't", "Didn" + apostrophe + "t")
                runner = ReviewRunner(current, comments=[request(), evidence])
                status, monitor, _ = self.snapshot(runner)
                self.assertEqual(status, 0)
                self.assertEqual(monitor.review_states[current.key].source, "receipt")

    def test_watch_finishes_when_receipt_replaces_the_eyes_reaction(self):
        current = target()
        runner = ReviewRunner(current, comments=[request()], request_reactions={77: [reaction("eyes", hour=3)]})
        clock = FakeClock()
        events = []

        def finish_review(seconds):
            clock.sleep(seconds)
            runner.request_reactions.clear()
            runner.selected["comments"] = connection([request(), receipt(current.head[:10], hour=4)])

        monitor = Watcher([current], runner=runner, emit=events.append, monitor_reviews=True,
                          clock=clock.now, sleep=finish_review, interval=5, discovery_grace=10, settle=0)
        self.assertEqual(monitor.watch(), 0)
        self.assertEqual([e["source"] for e in events if e["event"] == "review"], ["eyes", "receipt"])

    def test_untrusted_stale_and_unrecognized_receipts_do_not_pass(self):
        valid = receipt(target().head[:10])
        for name, overrides in (
            ("spoofed actor", {"author": {**BOT, "__typename": "User"}}),
            ("other bot", {"author": {**BOT, "login": "another-bot"}}),
            ("edited", {"lastEditedAt": "2026-01-01T04:00:00Z"}),
            ("edited creation", {"includesCreatedEdit": True}),
            ("predates request", {"createdAt": "2026-01-01T01:00:00Z"}),
            ("timestamp tie", {"createdAt": "2026-01-01T02:00:00Z"}),
            ("old revision", {"body": receipt("b" * 10)["body"]}),
            ("shorter prefix", {"body": receipt("a" * 7)["body"]}),
            ("quoted receipt", {"body": "Example:\n" + valid["body"]}),
            ("other verdict", {"body": valid["body"].replace("Didn't find any", "Found two")}),
            ("missing help block", {"body": valid["body"].split("\n\n<details>")[0]}),
            ("finding on verdict line", {"body": valid["body"].replace("More of your lovely PRs please.", "[P1] Fix authentication.")}),
            ("finding between details", {"body": valid["body"] + "\n\nFix authentication.\n<details>More.</details>"}),
            ("finding inside details", {"body": valid["body"].replace("</details>", "Fix authentication.</details>")}),
            ("finding before commit", {"body": valid["body"].replace("**Reviewed", "Fix the leak.\n\n**Reviewed")}),
            ("finding after receipt", {"body": valid["body"] + "\n\nFix the leak."}),
        ):
            with self.subTest(name=name):
                runner = ReviewRunner(comments=[request(), {**valid, **overrides}])
                self.assertEqual(self.snapshot(runner)[0], 3)
        for missing in ("lastEditedAt", "includesCreatedEdit"):
            with self.subTest(missing=missing):
                runner = ReviewRunner(comments=[request(), {k: v for k, v in valid.items() if k != missing}])
                self.assertEqual(self.snapshot(runner)[0], 3)

    def test_short_receipt_needs_exact_provider_resolution(self):
        runner = ReviewRunner(comments=[request(), receipt(target().head[:10])])
        runner.resolved_receipt_sha = target().head[:10] + "b" * 30
        self.assertEqual(self.snapshot(runner)[0], 3)

    def test_receipt_lookup_allows_only_the_scoped_sha_read(self):
        endpoint = "repos/owner/project/commits/a5f445178f"
        command = ["gh", "api", endpoint, "--method", "GET", "-H", "Accept: application/vnd.github.sha",
                   "--hostname", "git.example.com"]
        ensure_read_only(command)
        for index, invalid in ((2, endpoint + "/comments"), (2, endpoint[:-1]), (4, "POST"),
                               (6, "Authorization: injected"), (8, "git.example.com/path")):
            with self.subTest(index=index, invalid=invalid):
                modified = command.copy()
                modified[index] = invalid
                with self.assertRaises(WatchError):
                    ensure_read_only(modified)

    def test_receipt_cannot_clear_unresolved_threads_or_an_adverse_review(self):
        current = target()
        thread = {"id": "t", "isResolved": False, "comments": connection([{"author": BOT, "bodyText": "Fix leak"}])}
        for adverse in ({"threads": [thread]}, {"reviews": [review(current, state="CHANGES_REQUESTED")]}):
            with self.subTest(adverse=adverse):
                runner = ReviewRunner(current, comments=[request(), receipt(current.head[:10], hour=4)], **adverse)
                self.assertEqual(self.snapshot(runner)[0], 1)

    def test_receipt_cannot_supersede_a_standing_adverse_review_on_rerequest(self):
        current = target()
        for hour in (3, 4):
            with self.subTest(hour=hour):
                runner = ReviewRunner(current, comments=[request(hour=4), receipt(current.head[:10], hour=5)],
                                      reviews=[review(current, hour=hour, state="CHANGES_REQUESTED")])
                self.assertEqual(self.snapshot(runner)[0], 1)

    def test_receipt_after_resolved_comments_respects_standing_formal_decisions(self):
        current = target()
        feedback = review(current, hour=3, state="COMMENTED", body="Fix the leak.")
        changes = review(current, hour=2, state="CHANGES_REQUESTED")
        approval = review(current, hour=3)
        for reviews, expected in (
            ([feedback], 0), ([changes, feedback], 1), ([changes, feedback, approval], 0),
            ([review(current, hour=5, state="COMMENTED", body="Still leaks.")], 1),
        ):
            with self.subTest(reviews=reviews):
                runner = ReviewRunner(current, comments=[request(hour=4), receipt(current.head, hour=6)],
                                      reviews=reviews, threads=[{"isResolved": True}])
                self.assertEqual(self.snapshot(runner)[0], expected)

    def test_change_request_survives_a_push_until_dismissed_or_superseded(self):
        old, current = target(), target(head="b" * 40)
        changes = review(old, hour=2, state="CHANGES_REQUESTED")
        changes["url"] = "https://github.com/owner/project/pull/7#prior-review"
        neutral = review(current, hour=5, state="COMMENTED", body="")
        for reviews, expected in (
            ([changes], 1), ([changes, neutral], 1),
            ([{**changes, "state": "DISMISSED"}], 0),
            ([changes, review(old, hour=3)], 0), ([changes, review(current, hour=5)], 0),
            ([changes, review(old, hour=2)], 1), ([review(old, hour=2), changes], 1),
        ):
            with self.subTest(reviews=reviews):
                runner = ReviewRunner(current, comments=[request(hour=4), receipt(current.head, hour=6)],
                                      reviews=reviews)
                code, monitor, _ = self.snapshot(runner)
                self.assertEqual(code, expected)
                if expected == 1:
                    self.assertEqual(monitor.review_states[current.key].findings[0]["url"], changes["url"])
        waiting = ReviewRunner(current, comments=[request(hour=4)], reviews=[changes])
        self.assertEqual(self.snapshot(waiting)[0], 3)

    def test_superseded_current_change_request_still_needs_current_completion(self):
        old, current = target(), target(head="b" * 40)
        reviews = [review(current, hour=3), review(current, hour=4, state="CHANGES_REQUESTED"), review(old, hour=5)]
        for extra, expected, source in (([], 3, "request"), ([receipt(current.head, hour=6)], 0, "receipt")):
            with self.subTest(source=source):
                runner = ReviewRunner(current, comments=[request(hour=2), *extra], reviews=reviews)
                code, monitor, _ = self.snapshot(runner)
                self.assertEqual(code, expected)
                self.assertEqual(monitor.review_states[current.key].source, source)

    def test_approval_cannot_hide_feedback_tied_with_a_superseded_change_request(self):
        old, current = target(), target(head="b" * 40)
        changes = review(current, hour=3, state="CHANGES_REQUESTED")
        feedback = review(current, hour=3, state="COMMENTED", body="Fix unsafe command.")
        for tied in ([changes, feedback], [feedback, changes]):
            with self.subTest(tied=tied):
                runner = ReviewRunner(current, comments=[request(), receipt(current.head, hour=6)],
                                      reviews=[*tied, review(old, hour=5)])
                self.assertEqual(self.snapshot(runner)[0], 1)

    def test_receipt_only_clears_feedback_strictly_before_the_latest_trigger(self):
        current = target()
        received = receipt(current.head, hour=6)
        for trigger, reactions in ((request(hour=4), {}), (request(), {77: [reaction("eyes", hour=4)]})):
            for hour, extra, expected in ((3, [received], 0), (4, [received], 1), (4, [], 3), (5, [received], 1)):
                with self.subTest(trigger=trigger, hour=hour, receipt=bool(extra)):
                    feedback = review(current, hour=hour, state="COMMENTED", body="Fix the leak.")
                    runner = ReviewRunner(current, comments=[trigger, *extra], reviews=[feedback],
                                          request_reactions=reactions, threads=[{"isResolved": True}])
                    code, monitor, _ = self.snapshot(runner)
                    self.assertEqual(code, expected)
                    if expected == 1:
                        self.assertEqual(monitor.review_states[current.key].findings[0]["excerpt"], "Fix the leak.")

    def test_superseded_change_cannot_hide_separate_current_head_feedback(self):
        old, current = target(), target(head="b" * 40)
        feedback = review(current, hour=3, state="COMMENTED", body="Fix the leak.")
        changes = review(current, hour=5, state="CHANGES_REQUESTED")
        for clearance, expected in (([], 1), ([review(current, hour=4)], 0)):
            history = [feedback, *clearance, changes, review(old, hour=6)]
            for reviews in (history, history[::-1]):
                with self.subTest(clearance=clearance, reviews=reviews):
                    runner = ReviewRunner(current, comments=[request(), receipt(current.head, hour=7)], reviews=reviews)
                    code, monitor, _ = self.snapshot(runner)
                    self.assertEqual(code, expected)
                    if expected == 1:
                        self.assertEqual(monitor.review_states[current.key].findings[0]["excerpt"], "Fix the leak.")

    def test_positive_evidence_must_postdate_a_superseded_change_request(self):
        old, current = target(), target(head="b" * 40)
        for change_head in (old, current):
            history = [review(change_head, hour=4, state="CHANGES_REQUESTED"), review(old, hour=5)]
            for hour, expected in ((3, 3), (4, 3), (6, 0)):
                for notes, reviews in (([receipt(current.head, hour=hour)], history),
                                       ([], [*history, review(current, hour=hour)])):
                    with self.subTest(change_head=change_head.head, hour=hour, receipt=bool(notes)):
                        runner = ReviewRunner(current, comments=[request(), *notes], reviews=reviews)
                        self.assertEqual(self.snapshot(runner)[0], expected)

    def test_another_revision_cannot_revive_a_superseded_current_submission(self):
        old, current = target(), target(head="b" * 40)
        history = [review(current, hour=3, state="CHANGES_REQUESTED"), review(old, hour=4),
                   review(old, hour=5, state="CHANGES_REQUESTED", body="Still blocked.")]
        for extra, expected in (([], 3), ([receipt(current.head, hour=6)], 1)):
            with self.subTest(receipt=bool(extra)):
                runner = ReviewRunner(current, comments=[request(), *extra], reviews=history)
                code, monitor, _ = self.snapshot(runner)
                self.assertEqual(code, expected)
                if expected == 1:
                    self.assertEqual(monitor.review_states[current.key].findings[0]["excerpt"], "Still blocked.")

    def test_inflight_prior_revision_feedback_can_veto_current_completion(self):
        old, other, current = target(), target(head="c" * 40), target(head="b" * 40)
        automatic = [receipt(current.head, hour=7)]
        request_only = [request(hour=4)]
        manual = request_only + automatic
        for comments, hour, clearance, expected in (
            (manual, 3, [], 0), (manual, 4, [], 1), (manual, 5, [], 1),
            (manual, 5, [review(old, hour=6)], 0), (manual, 5, [review(other, hour=6)], 1),
            (manual, 5, [review(current, hour=6)], 0), (manual, 5, [review(current, hour=5)], 1),
            (automatic, 0, [], 0), (automatic, 1, [], 1), (automatic, 2, [], 1), (request_only, 5, [], 3),
        ):
            with self.subTest(comments=comments, hour=hour, clearance=clearance):
                feedback = review(old, hour=hour, state="COMMENTED", body="Fix the concurrent finding.")
                runner = ReviewRunner(current, comments=comments, reviews=[feedback, *clearance], threads=[{"isResolved": True}])
                runner.runs[0]["createdAt"] = "2026-01-01T01:00:00Z"
                runner.selected["commits"]["nodes"][0]["commit"]["committedDate"] = "2026-01-01T06:00:00Z"
                code, monitor, _ = self.snapshot(runner)
                self.assertEqual(code, expected)
                if expected == 1:
                    self.assertEqual(monitor.review_states[current.key].findings[0]["excerpt"], feedback["body"])

    def test_timestamp_correlated_thumb_does_not_pass(self):
        runner = ReviewRunner(reactions=[reaction("eyes"), reaction("+1", hour=3, identifier=2)])
        result, monitor, _ = self.snapshot(runner)
        self.assertEqual(result, 3)
        self.assertEqual(monitor.review_states[runner.current.key].status, "active")

    def test_review_discovery_needs_no_local_epoch_conversion(self):
        class WindowsEpochDateTime(datetime):
            @classmethod
            def fromtimestamp(cls, *args, **kwargs):
                raise OSError(22, "Invalid argument")

        runner = ReviewRunner()
        runner.runs = []
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        with patch("pipeline_monitor.datetime", WindowsEpochDateTime):
            monitor.discover_runs(initial=True)
        self.assertEqual(monitor.review_activation[runner.current.key], datetime(1970, 1, 1, tzinfo=timezone.utc))

    def test_thumb_without_eye_is_still_not_approval(self):
        runner = ReviewRunner(reactions=[reaction("+1", hour=3)])
        result, monitor, _ = self.snapshot(runner)
        self.assertEqual(result, 3)
        self.assertEqual(monitor.review_states[runner.current.key].source, "unverified-reaction")

    def test_exact_head_submitted_review_passes(self):
        current = target()
        runner = ReviewRunner(current, reactions=[reaction("eyes")], reviews=[review(current)])
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_complete_no_feedback_review_passes(self):
        for body in (
            "Codex reviewed this pull request and didn't find any major issues.",
            "  Codex reviewed this pull request and didn\u2019t find any major issues.\n",
        ):
            with self.subTest(body=body):
                runner = ReviewRunner(reviews=[review(target(), state="COMMENTED", body=body)])
                self.assertEqual(self.snapshot(runner)[0], 0)

    def test_neutral_header_cannot_hide_additional_review_text(self):
        for body in (
            "Codex reviewed this pull request.\n\n[P1] Fix the authorization bypass.",
            "Here are some automated review suggestions for this pull request.\n\n[P2] Handle missing values.",
            "Codex reviewed this pull request and didn't find any major issues.\n\nPlease inspect the retry path.",
            "Codex reviewed this pull request and didn't find any major issues.\n```\n[P1] unsafe()\n```",
            "Quoted: Codex reviewed this pull request and didn't find any major issues.",
            "Here are some automated review suggestions for this pull request.",
        ):
            with self.subTest(body=body):
                runner = ReviewRunner(reviews=[review(target(), state="COMMENTED", body=body)])
                result, monitor, events = self.snapshot(runner)
                self.assertEqual(result, 1)
                self.assertEqual(monitor.review_states[runner.current.key].status, "failed")
                self.assertTrue(any(event["event"] == "review-finding" for event in events))

    def test_review_on_old_sha_never_approves_new_sha(self):
        old, new = target(), target(head="b" * 40)
        runner = ReviewRunner(new, reactions=[reaction("eyes"), reaction("+1", hour=4, identifier=2)], reviews=[review(old)])
        self.assertEqual(self.snapshot(runner)[0], 3)

    def test_previous_request_remains_required_after_new_commit(self):
        runner = ReviewRunner(target(head="b" * 40), comments=[request(hour=0)], reviews=[review(target())])
        self.assertEqual(self.snapshot(runner)[0], 3)

    def test_new_request_invalidates_an_earlier_exact_head_review(self):
        current = target()
        runner = ReviewRunner(current, comments=[request(hour=4)], reviews=[review(current, hour=3)])
        self.assertEqual(self.snapshot(runner)[0], 3)

    def test_same_second_request_invalidates_observed_review_even_if_removed(self):
        runner = ReviewRunner(reviews=[review(target(), hour=3)])
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 0)
        runner.selected["comments"] = connection([request(hour=3)])
        self.assertEqual(monitor.watch(once=True), 3)
        runner.selected["comments"] = connection()
        self.assertEqual(monitor.watch(once=True), 3)
        runner.selected["reviews"] = connection([review(runner.current, hour=4)])
        self.assertEqual(monitor.watch(once=True), 0)

    def test_conflicting_same_second_reviews_never_pass_by_list_order(self):
        current = target()
        for state in ("CHANGES_REQUESTED", "COMMENTED"):
            finding = review(current, state=state, body="Fix the unsafe fallback")
            approval = review(current)
            for reviews in ([approval, finding], [finding, approval]):
                with self.subTest(state=state, reviews=reviews):
                    runner = ReviewRunner(current, comments=[request()], reviews=reviews)
                    self.assertEqual(self.snapshot(runner)[0], 1)

    def test_deleted_request_does_not_revive_older_acknowledgment(self):
        runner = ReviewRunner(comments=[request(hour=4)], reactions=[reaction("eyes")])
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 3)
        self.assertFalse(monitor.review_states[runner.current.key].acknowledged)
        runner.selected["comments"] = connection()
        self.assertEqual(monitor.watch(once=True), 3)
        self.assertFalse(monitor.review_states[runner.current.key].acknowledged)
        self.assertIn(runner.current.key, monitor.unacknowledged_reviews)

    def test_selected_review_without_trusted_request_or_evidence_blocks(self):
        for comments in ([], [request(association="CONTRIBUTOR")], [request(body="Quoted example:\n@codex review")]):
            with self.subTest(comments=comments), self.assertRaisesRegex(WatchError, "No current-head Codex review evidence"):
                self.snapshot(ReviewRunner(comments=comments))

    def test_outdated_unresolved_codex_thread_remains_a_finding(self):
        current = target()
        thread = {"id": "thread7", "isResolved": False, "isOutdated": True, "path": "module.py", "line": 4,
                  "comments": connection([{"author": BOT, "bodyText": "Fix this ghp_abcdefghijklmnopqrstuvwx", "url": "https://github.com/comment"}])}
        runner = ReviewRunner(current, reviews=[review(current)], threads=[thread])
        status, monitor, events = self.snapshot(runner)
        self.assertEqual(status, 1)
        finding = monitor.review_states[current.key].findings[0]
        self.assertTrue(finding["outdated"])
        self.assertIn("[REDACTED]", finding["excerpt"])
        self.assertTrue(any(event["event"] == "review-finding" for event in events))

    def test_resolved_thread_does_not_block_exact_review(self):
        current = target()
        runner = ReviewRunner(current, reviews=[review(current)], threads=[{"isResolved": True}])
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_changes_requested_and_actionable_review_body_fail(self):
        current = target()
        for state in ("CHANGES_REQUESTED", "COMMENTED"):
            with self.subTest(state=state):
                runner = ReviewRunner(current, reviews=[review(current, state=state, body="The handler loses events.")])
                self.assertEqual(self.snapshot(runner)[0], 1)

    def test_graphql_errors_and_truncated_connections_never_pass(self):
        for surface in ("errors", "comments", "reviews", "reviewThreads", "reactions"):
            with self.subTest(surface=surface):
                runner = ReviewRunner()
                if surface == "errors":
                    runner.graph_errors = [{"message": "permission denied"}]
                elif surface == "reactions":
                    runner.reactions = [reaction("eyes", identifier=i) for i in range(100)]
                else:
                    runner.selected[surface]["pageInfo"]["hasPreviousPage"] = True
                with self.assertRaisesRegex(WatchError, "coverage|access"):
                    self.snapshot(runner)

    def test_changed_head_or_base_between_discovery_and_review_blocks(self):
        for field, value in (("headRefOid", "c" * 40), ("baseRefName", "release")):
            with self.subTest(field=field):
                runner = ReviewRunner()
                runner.selected[field] = value
                with self.assertRaisesRegex(WatchError, "changed"):
                    self.snapshot(runner)

    def test_head_changed_before_discovery_blocks(self):
        runner = ReviewRunner()
        runner.pr["headRefOid"] = "c" * 40
        with self.assertRaisesRegex(WatchError, "differs"):
            self.snapshot(runner)

    def test_saturated_pr_discovery_blocks(self):
        runner = ReviewRunner()
        def run(argv, cwd=None, optional=False):
            if argv[:3] == ["gh", "pr", "list"]:
                return json.dumps([runner.pr] * 100)
            return runner(argv, cwd, optional)
        with self.assertRaisesRegex(WatchError, "100-item limit"):
            Watcher([runner.current], runner=run, emit=lambda event: None, monitor_reviews=True).watch(once=True)

    def test_same_labels_keep_review_state_independent(self):
        first = ReviewRunner(reviews=[review(target())])
        second_target = replace(target(), path=Path("/elsewhere/project"), root=Path("/elsewhere/project"), repository="other/project")
        second = ReviewRunner(second_target, reactions=[reaction("eyes")])
        second.pr["headRepositoryOwner"] = {"login": "other"}
        second.selected["headRepository"] = {"nameWithOwner": "other/project"}
        def run(argv, cwd=None, optional=False):
            return (second if cwd == second_target.path else first)(argv, cwd, optional)
        monitor = Watcher([first.current, second.current], runner=run, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 3)
        self.assertEqual(monitor.review_states[first.current.key].status, "passed")
        self.assertEqual(monitor.review_states[second.current.key].status, "active")

    def test_waits_for_exact_head_review_then_completes(self):
        runner = ReviewRunner(reactions=[reaction("eyes"), reaction("+1", hour=3, identifier=2)])
        clock = FakeClock()
        def sleep(seconds):
            clock.sleep(seconds)
            runner.selected["reviews"] = connection([review(runner.current, hour=4)])
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True,
                          clock=clock.now, sleep=sleep, settle=0)
        self.assertEqual(monitor.watch(), 0)
        self.assertGreater(clock.current, 0)

    def test_unacknowledged_request_blocks_after_grace(self):
        runner = ReviewRunner(comments=[request()])
        clock = FakeClock()
        events = []
        monitor = Watcher([runner.current], runner=runner, emit=events.append, monitor_reviews=True,
                          clock=clock.now, sleep=clock.sleep, discovery_grace=10, interval=5)
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["reason"], "Codex review request was not acknowledged")

    def test_later_pr_reactions_cannot_acknowledge_request_or_bypass_grace(self):
        for content in ("eyes", "+1"):
            with self.subTest(content=content):
                runner = ReviewRunner(comments=[request()], reactions=[reaction(content, hour=3)])
                clock = FakeClock()
                events = []
                monitor = Watcher([runner.current], runner=runner, emit=events.append, monitor_reviews=True,
                                  clock=clock.now, sleep=clock.sleep, discovery_grace=10, interval=5, timeout=30)
                self.assertEqual(monitor.watch(), 2)
                self.assertEqual(events[-1]["reason"], "Codex review request was not acknowledged")
                self.assertFalse(monitor.review_states[runner.current.key].acknowledged)
                self.assertEqual(monitor.review_states[runner.current.key].required_since.hour, 2)

    def test_pr_reactions_without_manual_request_keep_review_active_until_exact_review(self):
        for content in ("eyes", "+1"):
            with self.subTest(content=content):
                runner = ReviewRunner(reactions=[reaction(content)])
                clock = FakeClock()
                def sleep(seconds):
                    clock.sleep(seconds)
                    self.assertTrue(monitor.review_states[runner.current.key].acknowledged)
                    self.assertEqual(monitor.review_states[runner.current.key].status, "active")
                    if clock.current > 10:
                        runner.selected["reviews"] = connection([review(runner.current, hour=4)])
                monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True,
                                  clock=clock.now, sleep=sleep, discovery_grace=10, interval=5, settle=0, timeout=30)
                self.assertEqual(monitor.watch(), 0)
                self.assertGreater(clock.current, 10)

    def test_request_comment_acknowledgment_survives_grace_until_exact_review(self):
        runner = ReviewRunner(comments=[request()], request_reactions={77: [reaction("eyes")]})
        clock = FakeClock()
        def sleep(seconds):
            clock.sleep(seconds)
            if clock.current > 10:
                runner.selected["reviews"] = connection([review(runner.current, hour=4)])
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True,
                          clock=clock.now, sleep=sleep, discovery_grace=10, interval=5, settle=0)
        self.assertEqual(monitor.watch(), 0)
        self.assertGreater(clock.current, 10)

    def test_request_comment_reactions_acknowledge_without_approving(self):
        runner = ReviewRunner(comments=[request()], request_reactions={77: [
            reaction("eyes"), reaction("+1", hour=3, identifier=2),
        ]})
        result, monitor, _ = self.snapshot(runner)
        self.assertEqual(result, 3)
        self.assertTrue(monitor.review_states[runner.current.key].acknowledged)
        self.assertEqual(monitor.review_states[runner.current.key].status, "active")

    def test_request_comment_thumb_after_eye_removal_only_acknowledges(self):
        runner = ReviewRunner(comments=[request()], request_reactions={77: [reaction("+1", hour=3)]})
        result, monitor, _ = self.snapshot(runner)
        self.assertEqual(result, 3)
        self.assertTrue(monitor.review_states[runner.current.key].acknowledged)
        self.assertEqual(monitor.review_states[runner.current.key].source, "unverified-reaction")

    def test_reaction_older_than_latest_request_does_not_acknowledge(self):
        runner = ReviewRunner(comments=[request(hour=3)], reactions=[reaction("eyes"), reaction("+1")])
        _, monitor, _ = self.snapshot(runner)
        self.assertFalse(monitor.review_states[runner.current.key].acknowledged)

    def test_request_acknowledgment_requires_codex_bot_identity(self):
        for actor in ({"login": "person", "type": "User"}, {"login": "chatgpt-codex-connector", "type": "User"}):
            with self.subTest(actor=actor):
                eye = dict(reaction("eyes"), user=actor)
                runner = ReviewRunner(comments=[request()], request_reactions={77: [eye]})
                _, monitor, _ = self.snapshot(runner)
                self.assertFalse(monitor.review_states[runner.current.key].acknowledged)

    def test_only_latest_request_comment_can_acknowledge_request(self):
        runner = ReviewRunner(comments=[request(), request(hour=3, identifier=88)],
                              request_reactions={77: [reaction("eyes", hour=4)]})
        _, monitor, _ = self.snapshot(runner)
        self.assertFalse(monitor.review_states[runner.current.key].acknowledged)
        self.assertTrue(any("/issues/comments/88/reactions?" in call[2] for call in runner.calls))
        self.assertFalse(any("/issues/comments/77/reactions?" in call[2] for call in runner.calls))

    def test_new_same_second_request_cannot_reuse_previous_comment_acknowledgment(self):
        runner = ReviewRunner(comments=[request()], request_reactions={77: [reaction("eyes", hour=3)]})
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 3)
        self.assertTrue(monitor.review_states[runner.current.key].acknowledged)
        runner.selected["comments"] = connection([request(identifier=88), request()])
        self.assertEqual(monitor.watch(once=True), 3)
        state = monitor.review_states[runner.current.key]
        self.assertFalse(state.acknowledged)
        self.assertEqual(state.request.comment_id, 88)

    def test_new_same_second_request_receives_its_own_acknowledgment_grace(self):
        runner = ReviewRunner(comments=[request()])
        clock = FakeClock()
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True,
                          clock=clock.now, sleep=clock.sleep, discovery_grace=10)
        self.assertEqual(monitor.watch(once=True), 3)
        clock.sleep(9)
        runner.selected["comments"] = connection([request(identifier=88), request()])
        self.assertEqual(monitor.watch(once=True), 3)
        clock.sleep(2)
        self.assertEqual(monitor.watch(once=True), 3)
        clock.sleep(8)
        self.assertEqual(monitor.watch(once=True), 2)

    def test_deleted_request_does_not_accept_new_pr_or_older_comment_acknowledgment(self):
        runner = ReviewRunner(comments=[request(), request(hour=3, identifier=88)],
                              reactions=[reaction("eyes", hour=4), reaction("+1", hour=5, identifier=2)],
                              request_reactions={77: [reaction("eyes", hour=4)]})
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 3)
        runner.selected["comments"] = connection([request()])
        runner.calls.clear()
        self.assertEqual(monitor.watch(once=True), 3)
        state = monitor.review_states[runner.current.key]
        self.assertFalse(state.acknowledged)
        self.assertEqual(state.required_since.hour, 3)
        self.assertEqual(state.request.comment_id, 88)
        self.assertFalse(any(call[:2] == ["gh", "api"] and "/reactions?" in call[2] for call in runner.calls))
        runner.selected["reviews"] = connection([review(runner.current, hour=4)])
        self.assertEqual(monitor.watch(once=True), 0)

    def test_deleted_request_retains_activity_floor_until_later_exact_review(self):
        runner = ReviewRunner(comments=[request()], request_reactions={77: [reaction("eyes", hour=4)]})
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 3)
        runner.selected["comments"] = connection()
        runner.reactions = [reaction("eyes", hour=5), reaction("+1", hour=5, identifier=2)]
        runner.selected["reviews"] = connection([review(runner.current, hour=4)])
        runner.calls.clear()
        self.assertEqual(monitor.watch(once=True), 3)
        state = monitor.review_states[runner.current.key]
        self.assertFalse(state.acknowledged)
        self.assertEqual(state.required_since.hour, 4)
        self.assertEqual(state.request.comment_id, 77)
        self.assertFalse(any(call[:2] == ["gh", "api"] and "/reactions?" in call[2] for call in runner.calls))
        runner.selected["reviews"] = connection([review(runner.current, hour=5)])
        self.assertEqual(monitor.watch(once=True), 0)

    def test_request_comment_reaction_coverage_is_bounded(self):
        runner = ReviewRunner(comments=[request()], request_reactions={77: [
            reaction("eyes", identifier=i + 1) for i in range(100)
        ]})
        with self.assertRaisesRegex(WatchError, "coverage"):
            self.snapshot(runner)

    def test_missing_or_invalid_request_comment_identifier_blocks(self):
        for identifier in (None, False, -1, "77"):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(WatchError, "comment identifier"):
                    self.snapshot(ReviewRunner(comments=[request(identifier=identifier)]))

    def test_passed_review_disappearing_during_settlement_cannot_complete(self):
        for disappear in ("deleted", "dismissed"):
            with self.subTest(disappear=disappear):
                current = target()
                runner = ReviewRunner(current, reviews=[review(current)])
                clock = FakeClock()
                events = []
                def sleep(seconds):
                    clock.sleep(seconds)
                    runner.selected["reviews"] = connection(
                        [] if disappear == "deleted" else [review(current, state="DISMISSED")]
                    )
                monitor = Watcher([current], runner=runner, emit=events.append, monitor_reviews=True,
                                  clock=clock.now, sleep=sleep, interval=5, settle=10, timeout=20)
                with self.assertRaisesRegex(WatchError, "review evidence disappeared"):
                    monitor.watch()
                self.assertNotIn(current.key, monitor.review_states)
                self.assertNotIn(current.key, monitor.review_fingerprints)
                self.assertFalse(any(event.get("result") == "passed" for event in events))

    def test_review_disappearing_on_final_poll_invalidates_prior_pass(self):
        for disappear in ("deleted", "dismissed"):
            with self.subTest(disappear=disappear):
                current = target()
                runner = ReviewRunner(current, reviews=[review(current)])
                clock = FakeClock()
                graph_reads = 0
                def run(argv, cwd=None, optional=False):
                    nonlocal graph_reads
                    if argv[:3] == ["gh", "api", "graphql"]:
                        graph_reads += 1
                        if graph_reads > 1:
                            runner.selected["reviews"] = connection(
                                [] if disappear == "deleted" else [review(current, state="DISMISSED")]
                            )
                    return runner(argv, cwd, optional)
                monitor = Watcher([current], runner=run, emit=lambda event: None, monitor_reviews=True,
                                  clock=clock.now, sleep=clock.sleep, interval=5, settle=0, timeout=10)
                with self.assertRaisesRegex(WatchError, "review evidence disappeared"):
                    monitor.watch()
                self.assertGreaterEqual(graph_reads, 2)
                self.assertNotIn(current.key, monitor.review_states)

    def test_missing_negative_review_clears_old_findings_and_blocks(self):
        current = target()
        runner = ReviewRunner(current, reviews=[review(current, state="CHANGES_REQUESTED", body="Fix the handler.")])
        monitor = Watcher([current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 1)
        self.assertTrue(monitor.review_states[current.key].findings)
        runner.selected["reviews"] = connection()
        with self.assertRaisesRegex(WatchError, "review evidence disappeared"):
            monitor.watch(once=True)
        self.assertNotIn(current.key, monitor.review_states)
        self.assertNotIn(current.key, monitor.review_fingerprints)
        self.assertEqual(monitor.counts()["reviews_failed"], 0)

    def test_disappearing_request_does_not_make_active_review_optional(self):
        runner = ReviewRunner(comments=[request()])
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None, monitor_reviews=True)
        self.assertEqual(monitor.watch(once=True), 3)
        since = monitor.review_states[runner.current.key].required_since
        runner.selected["comments"] = connection()
        self.assertEqual(monitor.watch(once=True), 3)
        self.assertEqual(monitor.review_states[runner.current.key].required_since, since)


if __name__ == "__main__":
    unittest.main()
