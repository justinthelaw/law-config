"""Frozen Standard estimates price only coherent authenticated model aggregates."""
import copy
import unittest
import test_natural_protocol as fixtures
import export_panel
import pricing
import records
import results


class WorkerPrices(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.NaturalPricingTests()
        fixture.setUp()
        self.row = fixture.row
        self.terra()

    def terra(self):
        self.row['review_events'][0]['model'] = 'gpt-6.1-terra'
        self.row['turn_contexts']['child']['final']['model'] = 'gpt-6.1-terra'

    def effort(self):
        return export_panel.meter(self.row, results.usage(self.row), 'a'*64)

    def test_mixed_threads_and_frozen_source_reconcile_in_normal_reader(self):
        effort = self.effort()
        self.assertEqual(effort['coverage'], 'complete')
        self.assertAlmostEqual(effort['estimated_usd'], .000148 + .000074)
        self.assertTrue(effort['pricing']['root_default_verified'])
        for model in ('gpt-6.1-sol','gpt-6.1-terra'):
            self.assertEqual(effort['pricing']['model_tokens'][model], dict(threads=1,tokens=self.row['usage']['root']))
        self.assertEqual(effort['pricing']['policy'], 'natural-standard-v2')
        self.assertIn('20001415', effort['pricing']['rate_card']['source'])
        self.assertIn('not invoice', effort['pricing']['rate_card']['basis'])
        records.verify_cost('mixed', effort, records.CONFIRMATION_RATES)

    def test_coherent_multi_turn_terra_counts_aggregate_once(self):
        self.row['turn_meters']['child']['second'] = dict(self.row['turn_meters']['child']['final'],message_seq=10,usage_seq=12,terminal_seq=13)
        self.row['turn_contexts']['child']['second'] = dict(model='gpt-6.1-terra',effort='ultra')
        self.assertAlmostEqual(self.effort()['estimated_usd'], .000222)
        records.verify_cost('multi', self.effort(), records.CONFIRMATION_RATES)
        self.row['turn_contexts']['child']['second']['model'] = 'gpt-6.1-sol'
        self.assertIsNone(self.effort()['estimated_usd'])

    def test_unknown_unbound_and_inconsistent_threads_remain_unpriced(self):
        original = copy.deepcopy(self.row)
        for change in ('unknown','alias','parent','start','trace','meter','terminal'):
            with self.subTest(change=change):
                self.row = copy.deepcopy(original)
                if change in ('unknown','alias'):self.row['turn_contexts']['child']['final']['model'] = 'custom' if change=='unknown' else 'GPT-6.1 Terra'
                if change=='parent':self.row['review_events'][0]['parentThreadId'] = 'missing'
                if change=='start':self.row['review_events'][0]['model'] = 'gpt-6.1-sol'
                if change=='trace':self.row['turn_context_receipts'].pop('child')
                if change=='meter':self.row['turn_meters']['child']['final']['total']['inputTokens'] += 1
                if change=='terminal':self.row['turn_meters']['child']['final']['terminal_seq'] = 0
                effort = self.effort()
                self.assertIsNone(effort['estimated_usd'])
                self.assertAlmostEqual(effort['pricing']['known_usd_lower_bound'], .000148)
                records.verify_cost(change, effort, records.CONFIRMATION_RATES)

    def test_reader_rejects_rate_model_token_and_provenance_tampering(self):
        original = self.effort()
        for change in ('rate','model','tokens','start','parent','total','cost'):
            with self.subTest(change=change):
                effort = copy.deepcopy(original);p=effort['pricing']
                child = next(t for t in p['terminal_proof'] if t['model']=='gpt-6.1-terra')
                if change=='rate':p['rate_card']['rates']['gpt-6.1-terra']['output'] = 1
                if change=='model':child['model'] = 'gpt-6.1-sol'
                if change=='tokens':p['model_tokens']['gpt-6.1-terra']['tokens']['inputTokens'] += 1
                if change=='start':child['start']['model'] = 'gpt-6.1-sol'
                if change=='parent':child['start']['parent'] = child['thread']
                if change=='total':child['turns'][0]['total']['inputTokens'] += 1
                if change=='cost':effort['estimated_usd'] += .000001
                with self.assertRaises(ValueError):records.verify_cost(change, effort, records.CONFIRMATION_RATES)

    def test_partial_malformed_and_nonterminal_counters_round_trip(self):
        original = copy.deepcopy(self.row)
        cases = ['total', 'cached', 'reasoning', 'partial', 'missing', 'nonterminal', 'running',
                 'intermediate_total', 'intermediate_backwards', 'boolean_counter']
        seqs = ('message_seq', 'usage_seq', 'terminal_seq')
        cases += [(key, value) for key in seqs for value in (None, '8', True, 0, 'missing', 'duplicate')]
        cases += ['usage_before_message', 'terminal_before_message']
        for change in cases:
            with self.subTest(change=change):
                self.row = copy.deepcopy(original)
                child = self.row['turn_meters']['child']['final']
                if change in ('total','cached','reasoning'):
                    key = dict(total='totalTokens',cached='cachedInputTokens',reasoning='reasoningOutputTokens')[change]
                    self.row['usage']['child'][key] = child['total'][key] = 500
                if change == 'boolean_counter':self.row['usage']['child']['reasoningOutputTokens'] = False
                if change == 'partial':self.row['usage']['child'].pop('outputTokens')
                if change == 'missing':self.row['usage'].pop('child')
                if change == 'nonterminal':child['status'] = 'inProgress'
                if change == 'running':self.row['state'] = 'running'
                if change in ('intermediate_total','intermediate_backwards') or isinstance(change,tuple):
                    self.row['turn_meters']['child']['second'] = dict(copy.deepcopy(child),message_seq=10,usage_seq=12,terminal_seq=13)
                    self.row['turn_contexts']['child']['second'] = dict(model='gpt-6.1-terra',effort='high')
                    if change == 'intermediate_total':child['total']['totalTokens'] = 500
                    if change == 'intermediate_backwards':
                        child['total'] = {k:2*v for k,v in child['total'].items()}
                if isinstance(change,tuple):
                    key, value = change
                    if value=='duplicate':self.row['turn_meters']['child']['second'][key] = child[key]
                    elif value=='missing':child.pop(key)
                    else:child[key] = value
                if change == 'usage_before_message':child['usage_seq'] = 6
                if change == 'terminal_before_message':child['terminal_seq'] = 6
                effort = self.effort()
                self.assertIsNone(effort['estimated_usd'])
                self.assertAlmostEqual(effort['pricing']['known_usd_lower_bound'], .000222 if change=='running' else .000148)
                records.verify_cost(str(change), effort, records.CONFIRMATION_RATES)
                if change != 'running':
                    forged = copy.deepcopy(effort)
                    next(t for t in forged['pricing']['terminal_proof'] if t['model']=='gpt-6.1-terra')['meter_consistent'] = True
                    with self.assertRaises(ValueError):records.verify_cost('forged', forged, records.CONFIRMATION_RATES)

    def test_negative_counters_stay_missing_and_zero_is_valid(self):
        original = copy.deepcopy(self.row)
        for invalid in (('child',), ('root','child')):
            with self.subTest(invalid=invalid):
                self.row = copy.deepcopy(original)
                for thread in invalid:
                    self.row['usage'][thread]['inputTokens'] = -1
                    self.row['turn_meters'][thread]['final']['total']['inputTokens'] = -1
                effort = self.effort()
                self.assertIsNone(effort['estimated_usd'])
                self.assertEqual(effort['tokens']['inputTokens'], None if len(invalid)==2 else 100)
                records.verify_cost('negative', effort, records.CONFIRMATION_RATES)
        self.row = copy.deepcopy(original)
        for thread in ('root','child'):
            self.row['usage'][thread] = dict.fromkeys(results.TOKENS, 0)
            self.row['turn_meters'][thread]['final']['total'] = dict.fromkeys(results.TOKENS, 0)
        self.assertEqual(self.effort()['estimated_usd'], 0)
        records.verify_cost('zero', self.effort(), records.CONFIRMATION_RATES)

    def test_exact_public_models_and_legacy_output(self):
        token = dict(inputTokens=100,cachedInputTokens=80,outputTokens=10)
        expected = {'gpt-6.1-sol':.000148,'gpt-6.1-terra':.000074,'gpt-6-astra':.00078,
                    'gpt-6-sol':.000156,'gpt-6-luna':.0000078,'gpt-5.6-sol':.000312,
                    'gpt-5.6-terra':.000176,'gpt-5.6-luna':.0000176,'gpt-6-astra-law':.000975}
        for model, cost in expected.items():
            with self.subTest(model=model):self.assertAlmostEqual(pricing.model_cost(model,token),cost)
        for model in ('GPT-6.1 Terra','gpt-6.1-terra-preview','custom','gpt-6.1-terra@private'):
            self.assertIsNone(pricing.model_cost(model,token))
        self.row.pop('pricing_policy')
        self.assertEqual(results.usage(self.row), results._legacy_usage(self.row))
        self.assertAlmostEqual(results.usage(self.row)['usd_estimate'], .000296)
