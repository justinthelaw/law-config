"""Verify the exposed post-score screen without granting confirmation."""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path.cwd()
OUT = ROOT / 'tmp/pr-quality-panel/condition-scope-measure'
MEASURES = {'observable-red-green-replay', 'condition-scope-body-warnings'}
sys.path[:0] = [str(ROOT / 'docs/evaluations/tools'), str(ROOT / 'docs/evaluations')]
from records import read_json, read_pilot, digest, pilot_quality_signal, verify_cost
import composite


def sha(path):
    return digest(Path(path).read_bytes())


def node(case):
    return case.attrib['classname'].replace('.', '/') + '.py::' + case.attrib['name']


def xml_check(raw, observed, expected):
    cases = list(ET.fromstring(raw).iter('testcase'))
    ids = [node(case) for case in cases]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError('original collection differs')
    if any(case.find('skipped') is not None or case.find('error') is not None for case in cases):
        raise ValueError('skipped or setup cases')
    reconstructed = []
    for case in cases:
        failure = case.find('failure')
        reconstructed.append({
            'name': case.attrib['name'],
            'status': 'failure' if failure is not None else 'passed',
            'message': failure.attrib.get('message', '') if failure is not None else '',
        })
    if reconstructed != observed['cases']:
        raise ValueError('raw XML differs from checked driver receipt')
    green = all(case['status'] == 'passed' for case in reconstructed)
    if observed['exit'] not in (0, 1) or (observed['exit'] == 0) != green:
        raise ValueError('raw XML exit mismatch')
    return green


def identities(record, expected, descriptor_raw):
    if digest(descriptor_raw) != expected['descriptor_sha256']:
        raise ValueError('changed descriptor')
    actual = (record['name'], record['registration_sha256'],
              record['registration']['hypothesis_sha256'])
    wanted = (expected['name'], expected['registration_sha256'], expected['descriptor_sha256'])
    if actual != wanted:
        raise ValueError('wrong registration')
    if record['treatments'] != expected['treatments']:
        raise ValueError('wrong candidate or parent composite')
    descriptor = read_json(descriptor_raw)
    components = record.get('treatment_components', {})
    if 'composite_identities' in descriptor:
        if descriptor['composite_identities'] != expected['treatments']:
            raise ValueError('descriptor composites differ')
        if set(components) != {'prior', 'candidate'}:
            raise ValueError('missing prospective component locks')
    for role, lock in components.items():
        if composite.identity(lock) != expected['treatments'][role]:
            raise ValueError('component lock differs')
    if any(record[key] != expected[key] for key in ('case', 'base', 'merged', 'prompt_sha256')):
        raise ValueError('wrong task')
    rows = [record['submissions']['control'], record['submissions']['develop'], record['prior_develop']]
    complete = all(row['state'] == 'completed' and row['proposal_sha256'] is not None
                   and row['patch_sha256'] is not None for row in rows)
    metered = all(row['effort']['coverage'] == 'complete'
                  and type(row['effort']['estimated_usd']) in (float, int)
                  and math.isfinite(row['effort']['estimated_usd'])
                  and row['effort']['estimated_usd'] >= 0 for row in rows)
    for role, row in zip(('control', 'develop', 'prior'), rows):
        verify_cost(role, row['effort'], record['rates'])
    return complete, metered


def proposal_patches(record):
    return {
        'base': None,
        'gold': record['submissions']['upstream']['patch_sha256'],
        'candidate-control': record['submissions']['control']['patch_sha256'],
        'candidate-develop': record['submissions']['develop']['patch_sha256'],
        'prior-develop': record['prior_develop']['patch_sha256'],
    }


def verify_measurement_sources(policy):
    if set(policy['measurements']) != MEASURES:
        raise ValueError('policy must bind both required measurements')
    source_path = ROOT / policy['source_path']
    if sha(source_path) != policy['source_sha256']:
        raise ValueError('measurement source changed')
    source = read_pilot(source_path)
    supplement_path = OUT / 'warning-supplement.json'
    if sha(supplement_path) != policy['warning_supplement_sha256']:
        raise ValueError('warning source changed')
    supplement = read_json(supplement_path.read_bytes())
    observations = {item['id']: item for item in source['observations']}
    observations[supplement['id']] = supplement
    for measure, spec in policy['measurements'].items():
        item = observations[measure]
        evidence = item['evidence']
        if (item['receipt_sha256'] != spec['source_receipt_sha256']
                or digest(item['probe'].encode()) != spec['probe_sha256']
                or evidence['registration_sha256'] != policy['source_registration_sha256']
                or digest((json.dumps(evidence, indent=2) + '\n').encode()) != item['receipt_sha256']):
            raise ValueError('measure differs from frozen source receipt')
        if set(evidence['roles']) != set(spec['roles']):
            raise ValueError('source calibration roles differ')
        for role in spec['roles']:
            stages = evidence['roles'][role]['stages']
            if set(stages) != set(spec['stages']):
                raise ValueError('source calibration stages differ')
            if any(stage['command'] != spec['command'] for stage in stages.values()):
                raise ValueError('source calibration command differs')
    if sha(ROOT / 'docs/evaluations/tools/replay_caller.py') != policy['replay_helper_sha256']:
        raise ValueError('owning replay helper changed')


def verify_probe_stage(stage, kind):
    if digest(stage['output'].encode()) != stage['log_sha256']:
        raise ValueError('behavior output hash differs')
    observed = read_json(stage['output'])
    if type(stage['exit']) is not int or (stage['exit'], observed.get('outcome')) not in (
            (0, 'green'), (42, 'red-behavior')):
        raise ValueError('behavior setup or inconsistent exit/outcome')
    if kind == 'stream':
        failures = observed['failing_cases']
        if observed['generated_cases'] != 144 or type(failures) is not int or not 0 <= failures <= 144:
            raise ValueError('stream denominator differs')
        passed = failures == 0
    else:
        rows = observed['rows']
        if [row['input'] for row in rows] != ['strings', 'bytes', 'bytes-strings', 'strings-bytes']:
            raise ValueError('warning input partition differs')
        checks = []
        for index, row in enumerate(rows):
            if [operation['operation'] for operation in row['operations']] != ['get_data', 'close']:
                raise ValueError('warning attribution differs')
            classes = [warning['class'] for operation in row['operations']
                       for warning in operation['warnings']]
            in_scope = bool(row['operations'][0]['warnings']) if index > 1 else not classes
            good = (not row.get('error') and row.get('bytes') == [120, 121] and in_scope
                    and all(category == 'builtins.DeprecationWarning' for category in classes))
            if row['pass'] is not good:
                raise ValueError('warning verdict differs')
            checks.append(good)
        passed = all(checks)
    if passed != (stage['exit'] == 0):
        raise ValueError('behavior disagrees with exit')
    return observed['outcome']


def verify_measurements(raw, summary, record, target_sha, patches, policy):
    required = MEASURES
    if set(policy['measurements']) != required:
        raise ValueError('policy must bind both required measurements')
    if set(raw['measurements']) != required or set(summary) != required:
        raise ValueError('required measure omitted or substituted')
    unavailable = {role for role, patch in patches.items() if role != 'base' and patch is None}
    for measure, spec in policy['measurements'].items():
        value = raw['measurements'][measure]
        wanted = {
            'source_sha256': policy['source_sha256'],
            'source_receipt_sha256': spec['source_receipt_sha256'],
            'probe_sha256': spec['probe_sha256'],
            'target_sha256': target_sha,
            'registration_sha256': record['registration_sha256'],
            'case': record['case'],
            'target': record['name'],
            'source': policy['source_name'],
        }
        if any(value[key] != expected for key, expected in wanted.items()):
            raise ValueError('behavior source, probe, target or registration differs')
        if set(value['roles']) != set(spec['roles']) or set(summary[measure]) != set(spec['roles']):
            raise ValueError('required measurement role omitted')
        for role in spec['roles']:
            row = value['roles'][role]
            if role in unavailable:
                if row is not None or summary[measure][role] != 'unavailable':
                    raise ValueError('missing proposal must remain unavailable')
                continue
            if row is None or row['patch_sha256'] != patches[role]:
                raise ValueError('available behavior role or patch differs')
            if set(row['stages']) != set(spec['stages']):
                raise ValueError('required behavior stage omitted')
            for stage in row['stages'].values():
                if verify_probe_stage(stage, spec['kind']) != summary[measure][role]:
                    raise ValueError('behavior summary differs')
    return unavailable


def verify_consumers(v2, modules, v2_path, modules_path, patches, unavailable, policy):
    if set(v2['preserved_consumers']) != set(patches):
        raise ValueError('required named-consumer role omitted')
    available = set(patches) - unavailable
    required_modules = available | {'constructive-positive'}
    if not required_modules <= set(modules['rows']) or set(modules['rows']) - required_modules - unavailable:
        raise ValueError('required full-module role omitted or substituted')
    xml_rows = {}
    for role in unavailable:
        named = v2['preserved_consumers'][role]
        full = modules['rows'].get(role, {'outcome': 'unavailable'})
        if named.get('outcome') != 'unavailable' or full.get('outcome') != 'unavailable':
            raise ValueError('missing proposal consumer must remain unavailable')
        for kind in ('named', 'modules'):
            xml_rows[role + '/' + kind] = {'green': False, 'outcome': 'unavailable'}
    all_patches = dict(patches, **{'constructive-positive': policy['positive_patch_sha256']})
    for role in sorted(required_modules):
        positive = role == 'constructive-positive'
        patch = all_patches[role]
        if modules['rows'][role]['patch_sha256'] != patch:
            raise ValueError('full-module role patch differs')
        if not positive and v2['preserved_consumers'][role]['patch_sha256'] != patch:
            raise ValueError('named-consumer role patch differs')
        work = OUT / 'positive/work' if positive else OUT / Path(v2_path).stem / role / 'tree/work'
        diff = subprocess.check_output(['git', '-C', work, 'diff', '--binary', 'HEAD'])
        if (digest(diff) if diff else None) != patch:
            raise ValueError('work differs from exact role patch')
        operations = [('modules', modules['rows'][role], OUT / Path(modules_path).stem / role,
                       'modules.xml', policy['module_nodeids'])]
        if not positive:
            operations.append(('named', v2['preserved_consumers'][role],
                               OUT / Path(v2_path).stem / role / 'evidence',
                               'consumer.xml', policy['named_nodeids']))
        for kind, receipt, folder, filename, expected_ids in operations:
            driver = folder / 'driver.log'
            raw = (folder / filename).read_bytes()
            if sha(driver) != receipt['driver_log_sha256'] or read_json(driver.read_bytes()) != receipt['observed']:
                raise ValueError('driver receipt differs')
            observed = receipt['observed']
            test_hashes = {path: observed['files'][path] for path in policy['original_test_sha256']}
            if test_hashes != policy['original_test_sha256']:
                raise ValueError('original tests differ')
            production = 'src/werkzeug/wrappers/response.py'
            if observed['files'][production] != sha(work / production):
                raise ValueError('production identity differs')
            if receipt['driver_exit'] != 0:
                raise ValueError('driver setup error')
            green = xml_check(raw, observed, expected_ids)
            if green != (receipt['outcome'] == 'green'):
                raise ValueError('consumer verdict differs')
            xml_rows[role + '/' + kind] = {
                'green': green, 'xml_sha256': digest(raw), 'collected': len(expected_ids),
            }
    return xml_rows


def check(target_path, descriptor_path, expected, v2_path, modules_path, behavior_path, policy):
    target_sha = sha(target_path)
    if target_sha != expected['target_sha256']:
        raise ValueError('wrong target')
    calibration = target_sha in policy['calibration_target_sha256']
    descriptor_raw = Path(descriptor_path).read_bytes()
    descriptor = read_json(descriptor_raw)
    if not calibration:
        wanted = {'registration_sha256': digest((json.dumps(policy, indent=2) + '\n').encode()),
                  'checker_sha256': sha(__file__)}
        if descriptor.get('assessor', {}).get('decision_checker') != wanted:
            raise ValueError('checker not bound before release')
    record = read_pilot(target_path)
    complete, metered = identities(record, expected, descriptor_raw)
    verify_measurement_sources(policy)
    v2 = read_json(Path(v2_path).read_bytes())
    modules = read_json(Path(modules_path).read_bytes())
    if (v2['target_sha256'] != target_sha or modules['target_sha256'] != target_sha
            or modules['v2_receipt_sha256'] != sha(v2_path)):
        raise ValueError('wrong supplemental target')
    if (v2['registration_sha256'] != policy['v2_registration_sha256']
            or modules['registration_sha256'] != policy['modules_registration_sha256']):
        raise ValueError('wrong supplement registration')
    raw = read_json(Path(behavior_path).read_bytes())
    if sha(behavior_path) != v2['behavior_receipt_sha256']:
        raise ValueError('behavior receipt differs')
    patches = proposal_patches(record)
    unavailable = verify_measurements(raw, v2['behavior'], record, target_sha, patches, policy)
    xml_rows = verify_consumers(v2, modules, v2_path, modules_path, patches, unavailable, policy)
    quality = pilot_quality_signal(record)
    candidate, prior = record['submissions']['develop'], record['prior_develop']
    cheaper = metered and candidate['effort']['estimated_usd'] < prior['effort']['estimated_usd']
    times = [row['effort'].get('checkout_to_proposal_seconds') for row in (candidate, prior)]
    faster = (all(type(value) in (float, int) and math.isfinite(value) and value > 0 for value in times)
              and times[0] < times[1])
    behavior_green = all(v2['behavior'][measure]['candidate-develop'] == 'green'
                         for measure in policy['measurements'])
    consumer_green = all(xml_rows['candidate-develop/' + kind]['green'] for kind in ('named', 'modules'))
    controls_green = all(xml_rows[role + '/modules']['green']
                         for role in ('base', 'gold', 'constructive-positive'))
    mechanical = bool(not calibration and not unavailable and complete and metered and cheaper
                      and faster and behavior_green and consumer_green and controls_green
                      and quality['ready_blind_win_at_no_more_cost'] is True)
    decision = 'human-review-required' if mechanical else 'rejected-or-incomplete'
    if unavailable:
        decision = 'unavailable-diagnostic'
    return {
        'scope': 'Exposed mechanical screen only; no confirmation or promotion.',
        'confirmation_allowed': False,
        'historical_calibration_only': calibration,
        'all_three_producers_complete': bool(complete),
        'complete_monetary_metering': metered,
        'unavailable_producers': sorted(unavailable),
        'quality_signal': quality,
        'strictly_cheaper_than_prior': cheaper,
        'strictly_faster_than_prior': faster,
        'candidate_behavior_green': behavior_green,
        'candidate_original_consumers_green': consumer_green,
        'original_consumer_controls_green': controls_green,
        'mechanical_criteria_met': mechanical,
        'decision': decision,
        'human_review_required': [
            'Meaning and correct condition unit; outside-scope preservation intent.',
            'Preproduction intent-review chronology and mechanism difference from matched parent.',
            'Required final artifact review; actual stock and every descendant model/effort inventory.',
        ],
        'target_sha256': target_sha,
        'registration_sha256': record['registration_sha256'],
        'descriptor_sha256': digest(descriptor_raw),
        'raw_xml': xml_rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('target', 'descriptor', 'expect', 'policy', 'v2', 'modules', 'behavior', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--expect-sha256', required=True,
                        help='Trusted allocation/post-score binding receipt hash.')
    args = parser.parse_args()
    try:
        policy = read_json(args.policy.read_bytes())
        if args.policy.read_bytes() != (json.dumps(policy, indent=2) + '\n').encode():
            raise ValueError('policy bytes differ from frozen canonical receipt')
        if sha(args.expect) != args.expect_sha256:
            raise ValueError('trusted expected-binding receipt differs')
        if sha(__file__) != policy['checker_sha256']:
            raise ValueError('checker differs from prerelease policy')
        if sha(ROOT / 'docs/evaluations/tools/records.py') != policy['records_sha256']:
            raise ValueError('owning records changed')
        result = check(args.target, args.descriptor, read_json(args.expect.read_bytes()),
                       args.v2, args.modules, args.behavior, policy)
    except (ValueError, KeyError, TypeError, FileNotFoundError, ET.ParseError,
            subprocess.CalledProcessError) as error:
        result = {'decision': 'setup-error', 'confirmation_allowed': False,
                  'mechanical_criteria_met': False, 'error': str(error)}
    with args.output.open('x') as file:
        file.write(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
