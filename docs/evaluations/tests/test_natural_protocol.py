"""Offline natural-descendant pricing and confirmation controls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'develop-benchmark/panel'), str(ROOT / 'develop-benchmark/workflow'), str(ROOT / 'tools')]
from test_records import sample, write, HASH, confirmation_runtime, confirmation_profiles
import results
import controller
import records
import run
import export_panel
sys.path.insert(0, str(ROOT))
import benchmark

NATURAL = 'pr-quality-confirmation-natural-v1'


class NaturalPricingTests(unittest.TestCase):
    def setUp(self):
        t = {'inputTokens': 100, 'cachedInputTokens': 80, 'cacheWriteInputTokens': 0,
             'outputTokens': 10, 'reasoningOutputTokens': 6, 'totalTokens': 110}
        meter = {'final': {'message_seq': 7, 'usage_seq': 8, 'terminal_seq': 9, 'status': 'completed', 'total': dict(t)}}
        self.row = {'pricing_policy': 'natural-sol-v1', 'state': 'completed', 'root': 'root',
                    'model': 'gpt-6.1-sol', 'effort': 'medium', 'effective_root_model': 'gpt-6.1-sol',
                    'thread_start': {'model': 'gpt-6.1-sol'}, 'threads': ['root', 'child'],
                    'children': ['child'], 'usage': {'root': dict(t), 'child': dict(t)},
                    'turn_meters': {'root': copy.deepcopy(meter), 'child': copy.deepcopy(meter)},
                    'turn_context_receipts': {'root': 'a' * 64, 'child': 'b' * 64},
                    'turn_contexts': {'root': {'final': {'model': 'gpt-6.1-sol', 'effort': 'medium'}},
                                      'child': {'final': {'model': 'gpt-6.1-sol', 'effort': 'high'}}},
                    'review_events': [{'type': 'subAgentActivity', 'kind': 'started',
                                       'agentThreadId': 'child', 'parentThreadId': 'root',
                                       'model': 'gpt-6.1-sol', 'reasoningEffort': 'high'}]}

    def test_sidecar_filters_inherited_turns_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / 'sessions/rollout-child.jsonl'
            path.parent.mkdir()
            events = [
                {'type': 'session_meta', 'payload': {'id': 'child'}},
                {'type': 'session_meta', 'payload': {'id': 'parent'}},
                {'type': 'turn_context', 'payload': {'turn_id': 'parent-turn', 'model': 'other'}},
                {'type': 'turn_context', 'payload': {'turn_id': 'one', 'model': 'gpt-6.1-sol', 'effort': 'medium'}},
                {'type': 'turn_context', 'payload': {'turn_id': 'two', 'model': 'gpt-6.1-sol', 'effort': 'high'}},
            ]
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            value = controller.turn_contexts(home, 'child', {'one': {}, 'two': {}})
            self.assertEqual(set(value['contexts']), {'one', 'two'})
            events.append(events[-1])
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            self.assertIsNone(controller.turn_contexts(home, 'child', {'one': {}, 'two': {}}))
            events[0]['payload']['id'] = 'not-child'
            path.write_text(''.join(json.dumps(e) + '\n' for e in events[:-1]))
            self.assertIsNone(controller.turn_contexts(home, 'child', {'one': {}, 'two': {}}))

    def test_same_sol_different_effort_is_complete(self):
        result = results.usage(self.row)
        self.assertEqual(result['coverage'], 'complete')
        self.assertEqual(result['pricing']['token_coverage'], 'complete')
        self.assertAlmostEqual(result['usd_estimate'], .000296)
        self.assertEqual(result['tokens']['totalTokens'], 220)

    def test_other_model_retains_tokens_and_known_subtotal(self):
        self.row['review_events'][0]['model'] = 'different-model'
        result = results.usage(self.row)
        self.assertEqual(self.row['state'], 'completed')
        self.assertEqual(result['coverage'], 'lower bound')
        self.assertIsNone(result['usd_estimate'])
        self.assertAlmostEqual(result['pricing']['known_usd_lower_bound'], .000148)
        self.assertEqual(result['tokens']['totalTokens'], 220)

    def test_missing_conflicting_and_multi_turn_do_not_price_child(self):
        for change in ('missing', 'conflict', 'orphan', 'multi', 'parent'):
            with self.subTest(change=change):
                row = copy.deepcopy(self.row)
                if change == 'missing': row['review_events'] = []
                if change == 'conflict': row['review_events'].append(dict(row['review_events'][0], model='other'))
                if change == 'orphan': row['children'] = []
                if change == 'multi': row['turn_meters']['child']['other'] = dict(row['turn_meters']['child']['final'])
                if change == 'parent': row['review_events'][0]['parentThreadId'] = 'missing'
                value = results.usage(row)
                self.assertNotEqual(value['coverage'], 'complete')
                self.assertIsNone(value['usd_estimate'])
                self.assertEqual(value['tokens']['totalTokens'], 220)

    def test_missing_or_conflicting_cumulative_meter_is_incomplete(self):
        for mode in ('missing', 'changed'):
            row = copy.deepcopy(self.row)
            if mode == 'missing': del row['turn_meters']['child']['final']['total']
            else: row['turn_meters']['child']['final']['total']['inputTokens'] += 100
            value = results.usage(row)
            self.assertNotEqual(value['coverage'], 'complete')
            self.assertIsNone(value['usd_estimate'])
            self.assertAlmostEqual(value['pricing']['known_usd_lower_bound'], .000148)

    def test_incomplete_terminal_and_qualifier(self):
        self.row['turn_meters']['child']['final']['status'] = 'interrupted'
        self.assertNotEqual(results.usage(self.row)['coverage'], 'complete')
        child = {'kind': 'started', 'agentThreadId': 'child', 'model': 'gpt-6.1-sol', 'reasoningEffort': 'medium'}
        run.verify_qualifier_descendants({'children': ['child'], 'review_events': [child]})
        for bad in ([], [dict(child, reasoningEffort='high')], [dict(child, model='other')], [child, child]):
            with self.assertRaises(ValueError):
                run.verify_qualifier_descendants({'children': ['child'], 'review_events': bad})

    def test_natural_proposal_completes_and_captures_with_different_child(self):
        server = Mock()
        server.inventory.return_value = None
        capture = Mock()
        def execute(_server, _prompt, _skill, row, _budget):
            row.update(_released=1, commands=[], children=['child'],
                       review_events=[{'kind': 'started', 'agentThreadId': 'child',
                                       'model': 'other', 'reasoningEffort': 'high'}])
        with patch.object(run, 'NATURAL_DESCENDANTS', True), \
                patch.object(run.host, 'profile', return_value=(None, None, None)), \
                patch.object(run.host, 'Server', return_value=server), \
                patch.object(run.host, 'execute', side_effect=execute), \
                patch.object(run.guest, 'frozen', return_value=nullcontext()):
            result = run.native({}, 'develop', Path('.'), Path('.'), 'task', capture=capture)
            self.assertEqual(result['state'], 'completed')
            self.assertEqual(result['pricing_policy'], 'natural-sol-v1')
            capture.assert_called_once()
            assessor = run.native({}, 'control', Path('.'), Path('.'), 'task')
        self.assertEqual(assessor['state'], 'blocked')

    def test_portable_cost_reconciliation_rejects_tampering(self):
        usage = results.usage(self.row)
        attribution = dict(usage['pricing'], native_sha256='a' * 64)
        effort = {'coverage': usage['coverage'], 'tokens': usage['tokens'],
                  'estimated_usd': usage['usd_estimate'], 'thread_count': 2, 'child_count': 1,
                  'root_tokens': self.row['usage']['root'], 'descendant_tokens': self.row['usage']['child'],
                  'pricing': attribution}
        records.verify_cost('case', effort, records.CONFIRMATION_RATES)
        for alteration in ('tokens', 'amount', 'count', 'terminal'):
            bad = copy.deepcopy(effort)
            if alteration == 'tokens': bad['pricing']['priced_tokens']['inputTokens'] += 1
            if alteration == 'amount': bad['pricing']['known_usd_lower_bound'] += 1
            if alteration == 'count': bad['pricing']['unpriced_threads'] = 1
            if alteration == 'terminal': bad['pricing']['token_coverage'] = 'lower bound'
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                records.verify_cost('case', bad, records.CONFIRMATION_RATES)

    def test_proven_same_model_multi_turn_costs_cumulative_counter_once(self):
        self.row['turn_meters']['child']['second'] = dict(self.row['turn_meters']['child']['final'], message_seq=10, usage_seq=12, terminal_seq=13)
        self.row['turn_contexts']['child']['second'] = {'model': 'gpt-6.1-sol', 'effort': 'medium'}
        result = results.usage(self.row)
        self.assertEqual(result['coverage'], 'complete')
        self.assertAlmostEqual(result['usd_estimate'], .000296)
        self.row['turn_contexts']['child']['second']['model'] = 'other'
        self.assertIsNone(results.usage(self.row)['usd_estimate'])

    def test_all_unpriced_is_not_zero_dollars(self):
        self.row['effective_root_model'] = None
        self.row['review_events'][0]['model'] = 'other'
        result = results.usage(self.row)
        self.assertIsNone(result['usd_estimate'])
        self.assertIsNone(result['pricing']['known_usd_lower_bound'])
        self.assertEqual(result['tokens']['totalTokens'], 220)

    def test_normal_pilot_reader_accepts_complete_and_unpriced_attribution(self):
        self.row['review_events'][0]['model'] = 'gpt-6.1-terra'
        self.row['turn_contexts']['child']['final']['model'] = 'gpt-6.1-terra'
        original = ROOT / 'runs/tuning/declared-entry-pytest-01/result.json'
        record = json.loads(original.read_text())
        record['observations'] = []
        record['evaluator_protocol'] = record['registration']['evaluator_protocol'] = 'pr-quality-pytest-entry-natural-v1'
        record['registration_sha256'] = hashlib.sha256((json.dumps(record['registration'], indent=2) + '\n').encode()).hexdigest()
        def convert(old, native, native_sha256):
            usage = results.usage(native)
            usage['pricing']['native_sha256'] = native_sha256
            old.update(coverage=usage['coverage'], tokens=usage['tokens'], estimated_usd=usage['usd_estimate'],
                       thread_count=2, child_count=1, root_tokens=native['usage']['root'],
                       descendant_tokens=native['usage']['child'], pricing=usage['pricing'])
        for role in ('control', 'develop'):
            convert(record['submissions'][role]['effort'], self.row, record['submissions'][role]['receipt_sha256']['native'])
        convert(record['prior_develop']['effort'], self.row, 'a' * 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / record['name'] / 'result.json'
            path.parent.mkdir()
            path.write_text(json.dumps(record))
            complete = records.read_pilot(path)['submissions']['develop']['effort']
            self.assertEqual(complete['coverage'], 'complete')
            schema = json.loads((ROOT / 'schemas/panel-v1.json').read_text())
            validator = Draft202012Validator({'$defs': schema['$defs'], '$ref': '#/$defs/effort'})
            validator.validate(complete)
            unknown = copy.deepcopy(self.row)
            unknown['review_events'][0]['model'] = 'other'
            convert(record['submissions']['develop']['effort'], unknown, record['submissions']['develop']['receipt_sha256']['native'])
            path.write_text(json.dumps(record))
            restored = records.read_pilot(path)
            self.assertIsNone(restored['submissions']['develop']['effort']['estimated_usd'])
            self.assertEqual(restored['submissions']['develop']['effort']['tokens']['totalTokens'], 220)
            validator.validate(restored['submissions']['develop']['effort'])
            for malformed in ('total', 'sequence', 'nonterminal', 'partial', 'negative_child', 'negative_both', 'both_nonterminal'):
                native = copy.deepcopy(self.row)
                if malformed == 'total':
                    native['usage']['child']['totalTokens'] = 500
                    native['turn_meters']['child']['final']['total']['totalTokens'] = 500
                if malformed == 'sequence':native['turn_meters']['child']['final']['usage_seq'] = None
                if malformed == 'nonterminal':native['turn_meters']['child']['final']['status'] = 'inProgress'
                if malformed == 'partial':native['usage']['child'].pop('outputTokens')
                if malformed.startswith('negative'):
                    for thread in ('child',) if malformed=='negative_child' else ('root','child'):
                        native['usage'][thread]['inputTokens'] = native['turn_meters'][thread]['final']['total']['inputTokens'] = -1
                if malformed == 'both_nonterminal':
                    for thread in ('root','child'):native['turn_meters'][thread]['final']['status'] = 'inProgress'
                convert(record['submissions']['develop']['effort'], native, record['submissions']['develop']['receipt_sha256']['native'])
                path.write_text(json.dumps(record))
                actual = records.read_pilot(path)['submissions']['develop']['effort']
                self.assertIsNone(actual['estimated_usd'])
                if malformed in ('negative_both','both_nonterminal'):self.assertIsNone(actual['pricing']['known_usd_lower_bound'])
                else:self.assertAlmostEqual(actual['pricing']['known_usd_lower_bound'], .000148)
                if malformed=='negative_both':self.assertIsNone(actual['tokens']['inputTokens'])
            record['submissions']['develop']['effort'].pop('pricing')
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'requires pricing'):
                records.read_pilot(path)

    def test_unknown_price_does_not_become_total_or_win(self):
        self.row['review_events'][0]['model'] = 'other'
        usage = results.usage(self.row)
        row = {'develop': dict(usage, status='ready', state='completed', proposal_sha256='a'*64),
               'control': dict(usage, status='ready', state='completed', proposal_sha256='b'*64),
               'assessors': [{'rotation': i} for i in range(3)], 'pairs': {'develop_control': {'verdict': 'develop'}}}
        self.assertIsNone(results.goal_win(row))


class NaturalConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.manifest, entries = sample(self.path)
        self.rows = {(row['case_id'], row['role']): row for row in entries}
        self.runtime = confirmation_runtime()
        self.control, self.develop = (self.rows['full', k] for k in ('control', 'develop'))
        self.profiles = confirmation_profiles((self.control, self.develop))
        self.case = {'id': 'full', 'comparison': {'develop_control': {'verdict': 'develop'},
                                                  'confirmation': {'profiles': self.profiles}}}
        self.control['readiness'] = self.develop['readiness'] = 'ready'
        for row in (self.control, self.develop):
            row['effort']['pricing'] = {'root_default_verified': True}
        for row, score in ((self.control, 2), (self.develop, 4)):
            for j in row['quality']['assessments']:
                j['scores'] = dict(contract=score, tests=score, design=score, proposal=score)

    def decide(self):
        return records.confirmation_quality(self.case, self.rows, runtime=self.runtime, natural=True)

    def test_three_valued_goal_and_comparator_evidence(self):
        self.assertTrue(self.decide())
        self.develop['effort']['coverage'] = 'lower bound'
        self.develop['effort']['estimated_usd'] = None
        self.assertIsNone(self.decide())
        for j in self.control['quality']['assessments']:
            j['scores'] = dict(contract=4, tests=4, design=4, proposal=4)
        self.assertFalse(self.decide())
        self.develop['readiness'] = 'failed'
        self.assertFalse(self.decide())
        self.control['readiness'] = 'pending'
        self.assertIsNone(self.decide())
        self.control['readiness'] = 'ready'
        self.control['proposal'] = None
        self.assertIsNone(self.decide())
        self.control['proposal'] = 'restored'
        self.control['effort'] = None
        self.develop['readiness'] = 'ready'
        for j in self.control['quality']['assessments']:
            j['scores'] = dict(contract=2, tests=2, design=2, proposal=2)
        self.assertIsNone(self.decide())
        self.control['state'] = 'interrupted'
        self.assertIsNone(self.decide())
        self.profiles['control']['mcp'] = ['not-clean']
        self.assertIsNone(self.decide())

    def test_authenticated_high_root_preserves_price_but_not_default(self):
        fixture = NaturalPricingTests()
        fixture.setUp()
        fixture.row['turn_contexts']['root']['final']['effort'] = 'high'
        measured = results.usage(fixture.row)
        self.assertEqual(measured['coverage'], 'complete')
        self.assertAlmostEqual(measured['usd_estimate'], .000296)
        self.assertFalse(measured['pricing']['root_default_verified'])
        fixture.row['turn_contexts']['root']['final']['effort'] = None
        self.assertIsNone(results.usage(fixture.row)['pricing']['root_default_verified'])

    def test_root_default_is_a_comparability_prerequisite(self):
        self.assertTrue(self.decide())
        self.develop['effort']['pricing']['root_default_verified'] = False
        self.assertIsNone(self.decide())
        self.develop['effort']['pricing']['root_default_verified'] = None
        self.assertIsNone(self.decide())
        self.develop['effort']['pricing']['root_default_verified'] = True
        self.control['effort']['pricing']['root_default_verified'] = False
        self.assertIsNone(self.decide())

    def test_proven_cost_miss_and_missing_grade(self):
        self.develop['effort']['estimated_usd'] = self.control['effort']['estimated_usd'] + 1
        self.develop['quality']['assessments'] = []
        self.assertFalse(self.decide())
        self.develop['effort']['coverage'] = 'lower bound'
        self.develop['effort']['estimated_usd'] = None
        self.assertIsNone(self.decide())
        self.develop['readiness'] = 'pending'
        self.assertIsNone(self.decide())
        self.develop['effort'] = None
        self.assertIsNone(self.decide())
        self.profiles['develop'] = None
        self.assertIsNone(self.decide())

    def test_absent_grade_is_pending_but_observed_failure_is_failed(self):
        _, fresh = sample(self.path)
        row = next(r for r in fresh if r['case_id'] == 'full' and r['role'] == 'develop')
        row['receipt_sha256'].pop('grade')
        row['grade_applied'] = None
        row['stages'] = {}
        row['executable_pass'] = False
        row['readiness'] = 'pending'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        with self.assertRaisesRegex(ValueError, 'readiness contradicts'):
            records.verify_submission(row, records.CONFIRMATION_RATES, False, {})
        row['stages']['preserve'] = {'exit': 42, 'reason': None, 'command': 'synthetic', 'log_sha256': HASH}
        row['readiness'] = 'failed'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        row['stages'] = {}
        row['effort']['prompt_to_terminal_seconds'] = None
        row['readiness'] = 'pending'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        row['receipt_sha256']['grade'] = HASH
        row['grade_applied'] = True
        row['effort']['prompt_to_terminal_seconds'] = 90
        for stages in ({}, {'preserve': {'exit': None, 'reason': 'incomplete', 'command': 'synthetic', 'log_sha256': HASH}}):
            row['stages'] = stages
            records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        row['adjudication'] = {'resolution': 'cleared', 'evidence': 'synthetic clearing'}
        row['readiness'] = 'pending'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        row['adjudication'] = {'resolution': 'confirmed', 'evidence': 'synthetic veto'}
        row['readiness'] = 'failed'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        row['adjudication'] = None
        row['grade_applied'] = False
        row['readiness'] = 'failed'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)
        row['state'] = 'interrupted'
        row['readiness'] = 'unavailable'
        records.verify_submission(row, records.CONFIRMATION_RATES, False, {}, natural=True, deadline=300)

    def test_sidecar_digest_matches_exact_parsed_snapshot(self):
        home = self.path / 'profile'
        path = home / 'sessions/rollout-child.jsonl'
        path.parent.mkdir(parents=True)
        events = [{'type': 'session_meta', 'payload': {'id': 'child'}},
                  {'type': 'turn_context', 'payload': {'turn_id': 'one', 'model': 'gpt-6.1-sol', 'effort': 'medium'}}]
        original = ''.join(json.dumps(event) + '\n' for event in events).encode()
        path.write_bytes(original)
        read = Path.read_bytes
        def append_after_read(file):
            data = read(file)
            with file.open('ab') as stream:
                stream.write(b'{}\n')
            return data
        with patch.object(Path, 'read_bytes', autospec=True, side_effect=append_after_read):
            value = controller.turn_contexts(home, 'child', {'one': {}})
        self.assertEqual(value['trace_sha256'], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(value['trace_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_unallocated_export_is_unknown_and_unbound_usage_rejected(self):
        row = {'state': 'interrupted'}
        score = results.usage(row)
        with patch.dict(export_panel.E.PANEL, protocol=NATURAL):
            actual = export_panel.meter(row, score)
            self.assertEqual(actual['coverage'], 'unknown')
            self.assertIsNone(actual['estimated_usd'])
            self.assertIsNone(actual['pricing']['native_sha256'])
            self.assertEqual(actual['pricing']['unpriced_threads'], 0)
            with self.assertRaisesRegex(ValueError, 'unbound native pricing'):
                export_panel.meter(row, score, HASH)

    def test_portable_natural_bundle_and_named_status(self):
        manifest, rows = sample(self.path)
        manifest['protocol'] = NATURAL
        for case in manifest['cases']:
            selected = [row for row in rows if row['case_id'] == case['id'] and row['role'] != 'upstream']
            profiles = confirmation_profiles(selected)
            for row in selected:
                role, effort = row['role'], row['effort']
                row['grade_applied'] = True
                row['receipt_sha256']['native'] = HASH
                zero = {k: 0 for k in effort['tokens']}
                complete = effort['coverage'] == 'complete'
                if not complete:
                    effort['estimated_usd'] = None
                proof = [{'thread': HASH, 'bound': True, 'meter_consistent': True, 'trace_sha256': HASH,
                          'turns': [{'turn': HASH, 'model': 'gpt-6.1-sol', 'effort': 'medium',
                                     'message_seq': 1, 'usage_seq': 2, 'terminal_seq': 3, 'status': 'completed'}]}]
                effort['pricing'] = {'policy': 'natural-sol-v1', 'token_coverage': 'complete' if complete else 'lower bound',
                                     'priced_tokens': effort['tokens'] if complete else zero,
                                     'unpriced_tokens': zero if complete else effort['tokens'],
                                     'priced_threads': 1 if complete else 0, 'unpriced_threads': 0 if complete else 1,
                                     'unpriced_reasons': {} if complete else {'unpriced': 1},
                                     'known_usd_lower_bound': .00186 if complete else None,
                                     'native_sha256': HASH, 'terminal_proof': proof if complete else [],
                                     'root_start': {'thread': HASH, 'requested_model': 'gpt-6.1-sol',
                                                    'effective_model': 'gpt-6.1-sol', 'requested_effort': 'medium'},
                                     'root_default_verified': True if complete else None}
            case['comparison']['confirmation'] = {'win': records.strict_win(
                next(r for r in rows if r['case_id'] == case['id'] and r['role'] == 'control'),
                next(r for r in rows if r['case_id'] == case['id'] and r['role'] == 'develop'),
                case['comparison']['develop_control']['verdict'], range(3)), 'profiles': profiles,
                'strict_quality_win': None}
        develop = manifest['groups']['all']['observed_by_arm']['develop']
        develop['usd_estimate'] -= .00186
        develop['usd_observations'] -= 1
        write(self.path, manifest, rows)
        loaded, _ = records.read_bundle(self.path / 'run.json')
        self.assertEqual(loaded['protocol'], NATURAL)
        bundles = self.path / 'runs/pr-quality-panel-v2'
        published = bundles.with_name(NATURAL) / 'synthetic'
        published.mkdir(parents=True)
        shutil.copy(self.path / 'run.json', published / 'run.json')
        shutil.copy(self.path / 'submissions.jsonl', published / 'submissions.jsonl')
        with patch.object(benchmark, 'BUNDLES', bundles), patch.object(benchmark, 'STATE', self.path / 'state'):
            status = benchmark.status('test')
        self.assertEqual(status['phase'], 'published')
        self.assertIn('strict_confirmation_quality', status)
        self.assertIsNone(status['strict_confirmation_quality']['all_20_repositories'])

    def test_normal_run_dispatch_and_new_status_without_release(self):
        program = """import argparse,sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=['docs/evaluations','docs/evaluations/tools']
import benchmark as b, native_panel as n, cpu_leases
b.STATE=Path('tmp/pr-quality-panel/isolated-status')
args=argparse.Namespace(action='run',name='no-release',jobs=None,split=None)
with patch.object(b,'configure_temp'), patch.object(b,'require_reader'), patch.object(b,'operator',return_value=nullcontext()), patch.object(b,'published',return_value=None), patch.object(cpu_leases,'lease',return_value=nullcontext()), patch.object(n,'operate',return_value=0) as operate:
 assert b.dispatch(args)==0 and operate.call_count==1
 assert n.E.PANEL['protocol']=='pr-quality-confirmation-natural-v1' and n.E.native.NATURAL_DESCENDANTS
 assert b.status('no-release')['phase']=='new'
print('dispatch/status pass without release')"""
        env = dict(os.environ, DEVELOP_EVAL_COHORT=NATURAL, OAIPKG_DISABLE_META_MISSING='1', PYTHONDONTWRITEBYTECODE='1')
        self.assertIn(b'dispatch/status pass', subprocess.check_output([sys.executable, '-B', '-c', program], cwd=ROOT.parent.parent, env=env))

    def test_selector_preserves_case_configuration_and_root(self):
        program = '''import hashlib,json,sys
sys.path.insert(0,'docs/evaluations/develop-benchmark/panel')
import environment as e
p=dict(e.PANEL);p.pop('protocol')
print(json.dumps({'protocol':e.PANEL['protocol'],'digest':hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest(),
 'count':len(e.CASES),'model':e.PANEL['model'],'effort':e.PANEL['effort'],'natural':e.native.NATURAL_DESCENDANTS,'cohort':bool(e.COHORT)}))'''
        values = []
        for cohort in ('pr-quality-confirmation-v1', NATURAL):
            env = dict(os.environ, DEVELOP_EVAL_COHORT=cohort, OAIPKG_DISABLE_META_MISSING='1', PYTHONDONTWRITEBYTECODE='1')
            values.append(json.loads(subprocess.check_output([sys.executable, '-B', '-c', program], cwd=ROOT.parent.parent, env=env)))
        self.assertEqual(values[0]['digest'], values[1]['digest'])
        for value in values:
            self.assertEqual((value['count'], value['model'], value['effort'], value['cohort']), (20, 'gpt-6.1-sol', 'medium', True))
        self.assertEqual([x['natural'] for x in values], [False, True])


    def test_historical_grader_composition(self):
        program = "import json, environment as e; print(json.dumps(e.CASES))"
        def cases(protocol):
            env = dict(os.environ, DEVELOP_EVAL_COHORT=protocol, PYTHONPATH=str(ROOT / "develop-benchmark/panel"))
            output = subprocess.check_output([sys.executable, "-B", "-c", program], env=env)
            return json.loads(output)

        original = cases("pr-quality-panel-v2")
        runner = cases("pr-quality-runner-v3")
        pytest = cases("pr-quality-pytest-entry-v1")
        self.assertEqual(runner, original | {"runner-space": original["runner-space"] | {
            "check": "runner_lint_ledger_v3.mjs", "loopback_hosts": True}})
        self.assertEqual(pytest, original | {"pytest": original["pytest"] | {"console_preserve": True}})
        self.assertEqual(cases("pr-quality-pytest-entry-natural-v1"), runner | {"pytest": pytest["pytest"]})

    def test_public_entry_selects_new_defaults_and_frozen_cohorts(self):
        program = """import argparse,json,os,sys,types
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock,patch
sys.path[:0]=['docs/evaluations','docs/evaluations/tools','docs/evaluations/develop-benchmark/panel']
import benchmark as b
cfg=json.loads(sys.argv[1]);b.STATE=Path(sys.argv[2])/'state';b.BUNDLES=Path(sys.argv[2])/'bundles/panel'
package=types.ModuleType('confirmation');package.__path__=[]
cohort=types.ModuleType('confirmation.cohort');cohort.NAME='pr-quality-confirmation-v1'
cohort.load=lambda panel:dict(panel,protocol=cohort.NAME)
package.cohort=cohort;sys.modules.update(confirmation=package,**{'confirmation.cohort':cohort})
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
for name,protocol in cfg.get('plans',{}).items():save(b.STATE/'runs'/name/'plan.json',{'name':name,'protocol':protocol})
if cfg.get('registration'):save(b.STATE/'pilots/trial/registration.json',{'evaluator_protocol':cfg['registration'],'plans':{}})
if cfg.get('archive'):save(b.pilot_file('trial'),{'evaluator_protocol':cfg['archive']})
if cfg.get('bundle'):save(b.BUNDLES/'one/run.json',{'name':'trial','protocol':cfg['bundle'],'selection':None,'cohort':'primary'})
if cfg.get('cached'):import environment
calls=[];result={}
def observe(kind):
 import environment as e
 calls.append(kind);result.update(protocol=e.PANEL['protocol'],natural=e.native.NATURAL_DESCENDANTS,roots=[e.PANEL['model'],e.PANEL['effort']],env=os.environ.get('DEVELOP_EVAL_COHORT'))
 if kind=='native':
  server=Mock();server.inventory.return_value=None
  def execute(_server,_prompt,_skill,row,_budget):row.update(_released=1,commands=[],children=['child'],review_events=[{'kind':'started','agentThreadId':'child','model':'other','reasoningEffort':'high'}])
  n=e.native
  with patch.object(n.host,'profile',return_value=(None,None,None)),patch.object(n.host,'Server',return_value=server),patch.object(n.host,'execute',side_effect=execute),patch.object(n.guest,'frozen',return_value=nullcontext()):result['stock_descendant_state']=n.native({},'control',b.STATE,b.STATE,'synthetic',capture=Mock())['state']
 return 0
native=types.SimpleNamespace(operate=lambda args:observe('native'),preflight=lambda:observe('preflight'),setup=Mock())
pilot=types.SimpleNamespace(load_hypothesis=lambda args:None,run=lambda args:observe('native'),N=native)
pilot.C=types.SimpleNamespace(run_dir=lambda name:b.STATE/'runs'/name,verify_evaluator=lambda plan:None,verify_receipt=lambda entry:{})
def load(args):
 import environment as e
 pilot.E=e
pilot.load_hypothesis=load
sys.modules.update(native_panel=native,efficiency_pilot=pilot)
if cfg['action']=='report':sys.modules.update(records=types.SimpleNamespace(read_pilot=lambda path:observe('reader')),export_panel=types.SimpleNamespace(export_pilot=lambda *args:observe('export')))
def published_summary(*args):
 observe('reader')
 return {'selection':None,'cohort':'primary'}, {'phase':'published'}
if cfg.get('bundle'):b.published_summary=published_summary
import cpu_leases
args=argparse.Namespace(action=cfg['action'],name='trial',parent='parent' if cfg['action']=='recover' else None,case='pytest',jobs=None,split=None,treatment=Path(sys.argv[2])/'treatment.json')
save(args.treatment,{})
with patch.object(b,'configure_temp'),patch.object(b,'require_reader'),patch.object(b,'operator',return_value=nullcontext()),patch.object(cpu_leases,'lease',return_value=nullcontext()),patch.object(b.os,'sched_setaffinity'):
 try:result['exit']=b.dispatch(args)
 except ValueError as error:result['error']=str(error)
result['calls']=calls
print(json.dumps(result))"""
        old, natural, fresh = 'pr-quality-panel-v2', 'pr-quality-pytest-entry-natural-v1', 'pr-quality-confirmation-v1'
        cases = [
            ({'action':'run'}, natural), ({'action':'pilot'}, natural), ({'action':'preflight'}, natural),
            ({'action':'run','explicit':old}, old),
            ({'action':'run','plans':{'trial':old}}, old),
            ({'action':'run','plans':{'trial':fresh}}, fresh),
            ({'action':'run','explicit':'pr-quality-confirmation-natural-v1'}, 'pr-quality-confirmation-natural-v1'),
            ({'action':'run','plans':{'trial':'pr-quality-confirmation-natural-v1'}}, 'pr-quality-confirmation-natural-v1'),
            ({'action':'pilot','registration':'pr-quality-pytest-entry-v1','plans':{'trial-prior':'pr-quality-pytest-entry-v1','trial-candidate':'pr-quality-pytest-entry-v1'}}, 'pr-quality-pytest-entry-v1'),
            ({'action':'recover','plans':{'parent':fresh}}, fresh),
            ({'action':'report','registration':old,'plans':{'trial-prior':old,'trial-candidate':old}}, old),
            ({'action':'report','archive':fresh}, old),
            ({'action':'report','bundle':fresh}, old),
            ({'action':'run','bundle':fresh}, old),
            ({'action':'run','plans':{'trial':old},'explicit':natural}, 'frozen cohort'),
            ({'action':'recover','plans':{'trial':natural,'parent':old}}, 'cohorts conflict'),
            ({'action':'run','cached':True}, 'restart benchmark.py'),
            ({'action':'pilot','archive':fresh}, 'restore its original private state'),
        ]
        for index, (case, expected) in enumerate(cases):
            env=dict(os.environ,OAIPKG_DISABLE_META_MISSING='1',PYTHONDONTWRITEBYTECODE='1')
            env.pop('DEVELOP_EVAL_COHORT',None)
            if 'explicit' in case:env['DEVELOP_EVAL_COHORT']=case['explicit']
            with self.subTest(case=case):
                output=subprocess.check_output([sys.executable,'-B','-c',program,json.dumps(case),str(self.path/str(index))],cwd=ROOT.parent.parent,env=env)
                result=json.loads(output.splitlines()[-1])
                if expected.startswith('pr-quality-'):
                    self.assertEqual(result['protocol'],expected)
                    self.assertEqual(result['roots'],['gpt-6.1-sol','medium'])
                    self.assertEqual(result['natural'],expected.endswith('natural-v1'))
                    self.assertEqual(result['env'],None if case.get('archive') or case.get('bundle') else expected)
                    if 'stock_descendant_state' in result:self.assertEqual(result['stock_descendant_state'],'completed' if result['natural'] else 'blocked')
                    self.assertEqual(result['exit'],0)
                else:
                    self.assertIn(expected,result['error'])
                    self.assertEqual(result['calls'],[])

    def test_frozen_source_guard_precedes_preflight_preparation(self):
        import campaign, native_panel
        plan={'name':'legacy','protocol':results.E.PANEL['protocol'],
              'runtime':{'source_sha256':results.E.version_digest()},
              'rubric_sha256':results.E.sha(results.E.HERE/'rubric.md')}
        for field in ('protocol','source','rubric'):
            changed=copy.deepcopy(plan)
            if field=='source':changed['runtime']['source_sha256']='wrong'
            else:changed['protocol' if field=='protocol' else 'rubric_sha256']='wrong'
            with self.subTest(field=field),patch.object(native_panel,'pinned_cli') as cli,patch.object(native_panel.subprocess,'run') as docker:
                with self.assertRaisesRegex(ValueError,'original checkout.*DEVELOP_EVAL_COHORT'):
                    native_panel.preflight(changed)
                cli.assert_not_called()
                docker.assert_not_called()
        campaign.verify_evaluator(plan)

    def test_registered_export_checks_frozen_source_before_projection(self):
        import campaign
        root=self.path/'state';pilot=root/'pilots/source-miss';pilot.mkdir(parents=True)
        plan={'name':'source-miss-candidate','protocol':results.E.PANEL['protocol'],
              'runtime':{'source_sha256':'wrong'},'rubric_sha256':results.E.sha(results.E.HERE/'rubric.md')}
        path=root/'runs/source-miss-candidate/plan.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(plan))
        with patch.object(results.E,'STATE',root):
            reg={'plans':{'candidate':campaign.receipt(path)}}
            registration=pilot/'registration.json';registration.write_text(json.dumps(reg))
            raw={'registration':campaign.receipt(registration)}
            digest=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
            (pilot/('result-'+digest[:12]+'.json')).write_text(json.dumps(raw))
            with patch.object(export_panel,'submission') as project,patch.object(results.E,'save') as write:
                with self.assertRaisesRegex(ValueError,'frozen evaluator mismatch'):
                    export_panel.export_pilot('source-miss',self.path/'result.json')
                project.assert_not_called()
                write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
