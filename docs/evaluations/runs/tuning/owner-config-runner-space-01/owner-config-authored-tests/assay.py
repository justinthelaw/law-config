"""Assessor-only postscore assay. No evaluator/profile/provider imports or activation."""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
HISTORY = HERE.parent / 'runner-pin-sensitivity'
DESCRIPTOR = REPO / 'docs/evaluations/treatments/46e71b22bec6/hypothesis.json'
DESCRIPTOR_SHA = 'd433a8249108ee4a727f1a5dbee266cdb8cc8a48d8fc4e918583a6e63bfb8d67'
SUBJECTS = {'pure', 'prior', 'candidate', 'base', 'merged'}
OLD = '5fda3b95a4ea91299a34e894583c3862153e4b97'
NEW = '6d4fd22b20465ccc0f7354476588e8df7c9ca0e0'
NORMAL = 'npm run clean && tsc --project tsconfig.json && node --test "build/test/*.test.js"'
IMAGE = 'node@sha256:de636e50060a9908cf40a20a50d027ed74a99b2e31d2635f3b13e9e4e5e97e74'
CASES = ('requested', 'old-active-no-decoy', 'wrong-inactive-decoy', 'harmless-empty-env', 'old-markdownlint')
EXCLUDED = {'.git', 'build', 'node_modules'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def identity(root, excluded=()):
    """Never follow symlinks; bind file bytes, full modes, paths and link targets."""
    root = Path(root)
    rows = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) == root and d in excluded))
        for name in sorted(dirs + files):
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            if Path(directory) == root and name in excluded:
                continue
            mode = path.lstat().st_mode
            row = {'mode': oct(stat.S_IMODE(mode))}
            if stat.S_ISLNK(mode):
                row.update(kind='symlink', target=os.readlink(path))
            elif stat.S_ISREG(mode):
                row.update(kind='file', sha256=sha(path.read_bytes()), size=path.stat().st_size)
            elif stat.S_ISDIR(mode):
                row.update(kind='directory')
            else:
                raise ValueError('unsupported special source entry: ' + rel)
            rows[rel] = row
    return {'sha256': sha(json.dumps(rows, sort_keys=True).encode()), 'entries': rows}


def historical_dependency_digest(root):
    """Exact exposed environment.dependency_digest algorithm; no environment import."""
    root = Path(root)
    digest = hashlib.sha256()
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files + [d for d in dirs if (Path(base) / d).is_symlink()]):
            path = Path(base) / name
            if path == root / 'preparation.log':
                continue
            digest.update(str(path.relative_to(root)).encode() + b'\0' + str(path.lstat().st_mode).encode() + b'\0')
            digest.update(os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes())
            digest.update(b'\0')
    return digest.hexdigest()


def safe_owned(path):
    path = Path(path).resolve()
    if HERE not in path.parents or path == HERE:
        raise ValueError('destination must be a new child of assessor task directory')
    return path


def regular_input(root, path):
    """Host reads/writes must never traverse a source-provided symlink."""
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = Path(root)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    return path.is_file()


def release_guard(plan, seal_path=None, expected_seal_sha=None):
    """Authenticate seal before reading even a single subject path."""
    if sha(DESCRIPTOR.read_bytes()) != DESCRIPTOR_SHA:
        raise ValueError('descriptor changed')
    if plan.get('mode') == 'historical':
        for subject in plan['subjects']:
            source = Path(subject['source']).resolve()
            if source not in [(HISTORY / r / 'work').resolve() for r in ('control', 'develop', 'legacy-tests', 'constructive')]:
                raise ValueError('historical source outside explicit allowlist')
            if subject.get('patch'):
                raise ValueError('historical prep accepts exposed copies only, no patch source')
        return
    if plan.get('mode') != 'prospective' or not seal_path or not expected_seal_sha:
        raise ValueError('prospective assay locked: parent seal and explicit seal SHA required')
    raw = Path(seal_path).read_bytes()
    if sha(raw) != expected_seal_sha:
        raise ValueError('parent seal hash mismatch')
    seal = json.loads(raw)
    if seal.get('release') != 'postscore-authored-test-assay' or seal.get('descriptor_sha256') != DESCRIPTOR_SHA:
        raise ValueError('wrong seal scope')
    if seal.get('plan_sha256') != sha(json.dumps(plan, sort_keys=True).encode()):
        raise ValueError('seal does not bind exact assay plan')
    for kind in ('proposals', 'blind_scores'):
        values = seal.get(kind, {})
        keys = {'pure', 'prior', 'candidate'} if kind == 'proposals' else {'0', '1', '2'}
        if set(values) != keys or any(not re.fullmatch('[0-9a-f]{64}', str(x)) for x in values.values()):
            raise ValueError('three proposals and three blind scores must seal')
    if {s['name'] for s in plan['subjects']} != SUBJECTS or len(plan['subjects']) != 5:
        raise ValueError('all five exact sources required')


def reconstruct(subject, destination):
    """Verified base plus optional sealed patch; never patch participant trees."""
    source = Path(subject['source'])
    before = identity(source, EXCLUDED)
    if before['sha256'] != subject['source_sha256']:
        raise ValueError('source identity mismatch')
    destination = safe_owned(destination)
    if destination.exists():
        raise ValueError('refusing to overwrite existing owned tree')
    shutil.copytree(source, destination, symlinks=True,
                    ignore=lambda directory, names: [n for n in names if n in EXCLUDED] if Path(directory) == source else [])
    patch_identity = None
    if subject.get('patch'):
        patch = Path(subject['patch']).read_bytes()
        patch_identity = sha(patch)
        if patch_identity != subject['patch_sha256']:
            raise ValueError('patch identity mismatch')
        # git apply enforces traversal/symlink safety; no host configuration or hooks.
        subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'apply', '--no-index', '--whitespace=nowarn', '-'], cwd=destination, input=patch, check=True, env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1'))
    resulting = identity(destination)
    if resulting['sha256'] != subject['tree_sha256']:
        raise ValueError('reconstructed tree identity mismatch')
    if identity(source, EXCLUDED) != before:
        raise ValueError('original source changed during copy')
    return {'source': before, 'patch_sha256': patch_identity, 'tree': resulting}


def discover(root):
    """Source-driven candidates, not a fixed metadata filename. Unverified routes stay unknown."""
    package = root / 'package.json'
    if not package.is_file() or package.is_symlink():
        return {'status': 'unknown', 'reason': 'missing regular package.json'}
    scripts = read_json(package).get('scripts', {})
    candidates = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.is_file() or path.relative_to(root).parts[0] in EXCLUDED:
            continue
        if not re.search(r'(?:test|spec)\.(?:ts|js|mjs|cjs)$', path.name):
            continue
        text = path.read_text(errors='replace')
        lines = [i for i, line in enumerate(text.splitlines(), 1) if re.search(r'setup.python|markdownlint|lint\.ya?ml|pre.commit.config', line)]
        if lines:
            rel = path.relative_to(root).as_posix()
            compiled = 'build/' + rel[:-3] + '.js' if rel.endswith('.ts') else rel
            call = r'(?<![.\w])test(?:\s*\.\s*(?:skip|todo|only))?\s*\('
            names = re.findall(call + r'\s*[\"\']([^\"\']+)[\"\']', text)
            candidates.append({'source': rel, 'compiled': compiled, 'source_sha256': sha(path.read_bytes()), 'relevance_lines': lines,
                               'test_names': names, 'unresolved_test_calls': len(re.findall(call, text)) - len(names),
                               'git_reference_lines': [i for i, line in enumerate(text.splitlines(), 1) if re.search(r'[\"\']git[\"\']|\.git[/\"\']|\bGIT_', line)]})
    config = {}
    try:
        if regular_input(root, root / 'tsconfig.json'):
            config = read_json(root / 'tsconfig.json')
    except (OSError, ValueError):
        pass
    options = config.get('compilerOptions', {})
    supported = scripts.get('test') == NORMAL and options.get('rootDir') == '.' and options.get('outDir') == 'build' and not config.get('extends')
    included_sources = set()
    for pattern in config.get('include', []):
        if not isinstance(pattern, str) or pattern.startswith('/') or '..' in Path(pattern).parts:
            supported = False
            continue
        included_sources.update(p.relative_to(root).as_posix() for p in root.glob(pattern) if p.is_file())
    supported = supported and all(x['source'] in included_sources and not x['unresolved_test_calls'] and not x['git_reference_lines'] for x in candidates)
    included = all(fnmatch.fnmatch(x['compiled'], 'build/test/*.test.js') and '/' not in x['compiled'][len('build/test/'):] for x in candidates)
    return {'status': 'supported' if supported and candidates and included else 'unknown',
            'reason': None if supported and candidates and included else 'route/relevance/discovery requires assessor verification',
            'package_sha256': sha(package.read_bytes()), 'scripts': scripts, 'candidates': candidates,
            'tsconfig_sha256': sha((root / 'tsconfig.json').read_bytes()) if regular_input(root, root / 'tsconfig.json') else None,
            'compiler_options': options, 'source_inclusion': {x['source']: x['source'] in included_sources for x in candidates},
            'configured_node_argv': ['node', '--test', 'build/test/*.test.js'], 'normal_discovery_inclusion': included,
            'scope': 'candidate relevant modules, including inherited tests; no assertion-level authorship inferred'}


def variants(workflow, hooks):
    newline = '\r\n' if '\r\n' in workflow else '\n'
    if '\r' in workflow.replace('\r\n', ''):
        raise ValueError('unsupported mixed/carriage-return workflow layout')
    marker = 'uses: actions/setup-python@' + NEW + ' # v7.1.0'
    # Base keeps its original test source; controls upgrade only these two pins.
    if marker not in workflow:
        workflow = workflow.replace('uses: actions/setup-python@' + OLD + ' # v7.0.0', marker, 1)
    if 'rev: v0.24.0' not in hooks:
        hooks = hooks.replace('rev: v0.23.3', 'rev: v0.24.0', 1)
    if workflow.count(marker) != 1 or hooks.count('rev: v0.24.0') != 1:
        raise ValueError('requested anchors missing/ambiguous; no synthetic base positive')
    wrong = workflow.replace(marker, 'uses: actions/setup-python@' + OLD + ' # v7.0.0', 1)
    neutral = workflow.replace(marker + newline + '        with:', marker + newline + '        env: {}' + newline + '        with:', 1)
    if neutral == workflow:
        raise ValueError('neutral owner layout unverified')
    return {'requested': (workflow, hooks), 'old-active-no-decoy': (wrong, hooks),
            'wrong-inactive-decoy': (wrong + ('\n      - name: Unrelated disabled Python pin\n        if: ${{ false }}\n        uses: actions/setup-python@' + NEW + ' # v7.1.0\n        with:\n          python-version: "3.15"\n').replace('\n', newline), hooks),
            'harmless-empty-env': (neutral, hooks),
            'old-markdownlint': (workflow, hooks.replace('rev: v0.24.0', 'rev: v0.23.3', 1))}


class Docker:
    def __init__(self, dependencies, expected_identity):
        self.dependencies = Path(dependencies).resolve()
        self.identity = identity(self.dependencies)
        if self.identity['sha256'] != expected_identity:
            raise ValueError('offline dependency tree mismatch')
        inspected = subprocess.run(['taskset', '-c', '0,1', 'docker', 'image', 'inspect', IMAGE], capture_output=True, check=True)
        self.image_inspect_sha256 = sha(inspected.stdout)
        self.image_id = json.loads(inspected.stdout)[0]['Id']

    def run(self, root, argv, evidence, timeout=180):
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / 'tmp').mkdir(exist_ok=True)
        cmd = ['taskset', '-c', '0,1', 'docker', 'run', '--pull=never', '--rm', '--init', '--platform', 'linux/amd64', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '512', '--cpus', '2', '--memory', '4g',
               '--user', f'{os.getuid()}:{os.getgid()}', '--network=none', '--cpuset-cpus=0,1', '--entrypoint=', '-w', '/work',
               '--mount', f'type=bind,src={root},dst=/work', '--mount', f'type=bind,src={self.dependencies},dst=/deps,readonly',
               '--mount', f'type=bind,src={evidence},dst=/evidence', '--mount', f'type=bind,src={evidence / "tmp"},dst=/tmp']
        for key, value in {'TMPDIR': '/evidence/tmp', 'TMP': '/evidence/tmp', 'TEMP': '/evidence/tmp', 'HOME': '/evidence', 'XDG_CACHE_HOME': '/evidence/cache', 'npm_config_cache': '/evidence/npm-cache', 'npm_config_offline': 'true', 'npm_config_audit': 'false', 'npm_config_fund': 'false', 'npm_config_update_notifier': 'false', 'PATH': '/work/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}.items():
            cmd += ['-e', key + '=' + value]
        cmd += [IMAGE, *argv]
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        begin = time.monotonic()
        try:
            run = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            output, code, timedout = run.stdout, run.returncode, False
        except subprocess.TimeoutExpired as error:
            output, code, timedout = error.stdout or b'', None, True
        log = evidence / 'terminal.log'
        log.write_bytes(output)
        text = output.decode(errors='replace')
        tests = re.search(r'^# tests (\d+)$', text, re.M)
        failures = re.findall(r'^not ok \d+ - (.*)$', text, re.M)
        # A nonzero infrastructure exit without executed tests is never discrimination.
        assertion_only = len(re.findall(r"code: ['\"]ERR_ASSERTION['\"]", text)) == len(failures) and bool(failures)
        passes = re.search(r'^# pass (\d+)$', text, re.M)
        skipped = re.search(r'^# skipped (\d+)$', text, re.M)
        cancelled = re.search(r'^# cancelled (\d+)$', text, re.M)
        incomplete = not passes or (code == 0 and int(passes[1]) == 0) or (cancelled and int(cancelled[1]))
        executed_names = [line for line in re.findall(r'^(?:ok|not ok) \d+ - (.*)$', text, re.M) if not re.search(r' # (?:SKIP|TODO)\b', line, re.I)]
        status = 'unknown' if timedout or incomplete or not tests or int(tests[1]) == 0 or code not in (0, 1) or (code == 1 and not assertion_only) else ('accept' if code == 0 else 'reject')
        return {'argv': argv, 'host_command': cmd, 'cwd': '/work', 'image': IMAGE,
                'start_utc': started, 'end_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'wall_seconds': time.monotonic() - begin, 'exit': code, 'timeout': timedout,
                'log_sha256': sha(output), 'status': status, 'tests': int(tests[1]) if tests else None,
                'failed_tests': failures, 'assertion_only': assertion_only, 'image_id': self.image_id,
                'executed_test_names': executed_names, 'skipped_count': int(skipped[1]) if skipped else None,
                'image_inspect_sha256': self.image_inspect_sha256, 'dependency_tree_sha256': self.identity['sha256']}


def bind_relevant_execution(result, candidates):
    relevant_names = {n for x in candidates for n in x['test_names']}
    result['relevant_test_names'] = sorted(relevant_names)
    result['relevant_executed_inclusion'] = bool(relevant_names) and relevant_names <= set(result['executed_test_names'])
    if not result['relevant_executed_inclusion']:
        result.update(status='unknown', reason='relevant tests absent/skipped or names unverified')
    if result['status'] == 'reject' and not set(result['failed_tests']) <= relevant_names:
        result.update(status='unknown', reason='failure outside candidate relevant modules')
    return result


def assess(subject, output, runtime, selected_cases=CASES):
    output = safe_owned(output)
    output.mkdir(parents=True)
    root = output / 'work'
    try:
        reconstructed = reconstruct(subject, root)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        record = {'name': subject['name'], 'status': 'unknown', 'stage': 'source reconstruction', 'reason': str(error), 'routes': {}}
        write_json(output / 'receipt.json', record)
        return record
    record = {'name': subject['name'], 'identities': reconstructed, 'routes': {}}
    original_source = identity(Path(subject['source']), EXCLUDED)
    record['source_full_tree_before'] = identity(Path(subject['source']))
    baseline = identity(root)
    record['discovery'] = discover(root)
    workflow = root / '.github/workflows/lint.yml'
    hooks = root / '.pre-commit-config.yaml'
    if not regular_input(root, workflow) or not regular_input(root, hooks):
        record.update(status='unknown', reason='mutation input missing or symlinked')
        write_json(output / 'receipt.json', record)
        return record
    if record['discovery']['status'] != 'supported':
        record.update(status='unknown', reason=record['discovery']['reason'])
        write_json(output / 'receipt.json', record)
        return record
    try:
        controls = variants(workflow.read_bytes().decode('utf-8'), hooks.read_bytes().decode('utf-8'))
    except (ValueError, OSError) as error:
        record.update(status='unknown', reason=str(error), expected_source_status='base may lack requested upgrades')
        write_json(output / 'receipt.json', record)
        return record
    (root / 'node_modules').symlink_to('/deps/node_modules', target_is_directory=True)
    try:
        semantics = output / 'control-semantics'
        semantics.mkdir()
        write_json(semantics / 'controls.json', {'original': [workflow.read_bytes().decode('utf-8'), hooks.read_bytes().decode('utf-8')], 'controls': controls})
        parser = HERE / 'validate-controls.mjs'
        shutil.copyfile(parser, semantics / parser.name)
        record['control_semantics'] = runtime.run(root, ['node', '/evidence/validate-controls.mjs'], semantics)
        record['control_semantics']['assessor_script_sha256'] = sha(parser.read_bytes())
        record['control_semantics']['input_sha256'] = sha((semantics / 'controls.json').read_bytes())
        if record['control_semantics']['exit'] != 0:
            record.update(status='unknown', reason='controlled mutations do not prove intended owner semantics')
            return record
        record['control_semantics']['status'] = 'verified'
        compile_inputs = identity(root, {'build', 'node_modules'})
        record['toolchain'] = runtime.run(root, ['sh', '-ec', 'node --version && npm --version && node -e "const f=require(\'fs\'),c=require(\'crypto\');for(const p of [process.execPath,\'/deps/node_modules/typescript/bin/tsc\',\'/deps/node_modules/typescript/lib/tsc.js\'])console.log(p,c.createHash(\'sha256\').update(f.readFileSync(p)).digest(\'hex\'))"'], output / 'toolchain')
        if record['toolchain']['exit'] != 0:
            record.update(status='unknown', reason='pinned binary identities unavailable')
            return record
        compile_result = runtime.run(root, ['sh', '-ec', 'npm run clean && tsc --project tsconfig.json'], output / 'compile')
        record['compile'] = compile_result
        # Compile has no TAP summary: use exact exit, then require every relevant emitted output.
        candidates = record['discovery']['candidates']
        missing = [x['compiled'] for x in candidates if not regular_input(root, root / x['compiled'])]
        if compile_result['exit'] != 0 or missing:
            record.update(status='unknown', reason='configured compile failed or outputs absent', missing=missing)
            return record
        compile_result['status'] = 'compiled'
        record['compiled_tree'] = identity(root / 'build')
        record['compile_inputs'] = compile_inputs
        record['node_phase_only'] = True
        record['npm_test_rerun'] = False
        originals = (workflow.read_bytes(), hooks.read_bytes())
        try:
            for name in selected_cases:
                wf, hk = controls[name]
                workflow.write_bytes(wf.encode('utf-8'))
                hooks.write_bytes(hk.encode('utf-8'))
                row = {'tree_before': identity(root), 'routes': {}}
                # Only workflow/hook inputs change; compilation inputs otherwise stay identical.
                expected = dict(compile_inputs['entries'])
                actual = identity(root, {'build', 'node_modules'})['entries']
                for changed in ('.github/workflows/lint.yml', '.pre-commit-config.yaml'):
                    expected.pop(changed, None)
                    actual.pop(changed, None)
                if expected != actual or identity(root / 'build') != record['compiled_tree']:
                    raise ValueError('compile reuse identity changed')
                direct = ['node', '--test', *[x['compiled'] for x in candidates]]
                for route, argv in (('direct', direct), ('configured-node-discovery', record['discovery']['configured_node_argv'])):
                    if identity(root / 'build') != record['compiled_tree']:
                        raise ValueError('compiled outputs changed before route')
                    route_inputs = identity(root, {'build', 'node_modules'})['entries']
                    for changed in ('.github/workflows/lint.yml', '.pre-commit-config.yaml'):
                        route_inputs.pop(changed, None)
                    if route_inputs != expected:
                        raise ValueError('compile inputs changed before route')
                    before_route = identity(root)
                    result = runtime.run(root, argv, output / name / route)
                    result['tree_before_sha256'] = before_route['sha256']
                    result['tree_after_sha256'] = identity(root)['sha256']
                    if result['tree_after_sha256'] != result['tree_before_sha256']:
                        result.update(status='unknown', reason='test mutated owned tree')
                    bind_relevant_execution(result, candidates)
                    row['routes'][route] = result
                row['tree_after'] = identity(root)
                row['interpretation'] = 'decoy rejection can be inherited topology; not owner-pin evidence' if name == 'wrong-inactive-decoy' else 'module-level result; inspect failing assertions before attributing authored discrimination'
                record['routes'][name] = row
        finally:
            workflow.write_bytes(originals[0])
            hooks.write_bytes(originals[1])
        record['status'] = 'recorded'
        return record
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        record.update(status='unknown', reason=str(error))
        return record
    finally:
        record['owned_restored'] = identity(root, {'build', 'node_modules'}) == baseline
        record['source_unchanged'] = identity(Path(subject['source']), EXCLUDED) == original_source
        record['source_full_tree_after'] = identity(Path(subject['source']))
        record['source_full_tree_unchanged'] = record['source_full_tree_after'] == record['source_full_tree_before']
        record['owned_full_tree_after'] = identity(root)
        if not record['owned_restored'] or not record['source_full_tree_unchanged']:
            record.update(status='unknown', reason='source changed or controlled inputs not restored')
        write_json(output / 'receipt.json', record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--seal', type=Path)
    parser.add_argument('--parent-seal-sha256')
    args = parser.parse_args()
    plan = read_json(args.plan)
    release_guard(plan, args.seal, args.parent_seal_sha256)
    assessor_artifacts = {name: sha((HERE / name).read_bytes()) for name in ('assay.py', 'validate-controls.mjs')}
    # Required state/dependencies are explicit operator inputs, never discovered from live roles.
    os.environ['PANEL_CPUSET'] = '0,1'
    taskenv = HERE / 'environment'
    taskenv.mkdir(exist_ok=True)
    for key in ('TMPDIR', 'TMP', 'TEMP', 'HOME', 'XDG_CACHE_HOME'):
        os.environ[key] = str(taskenv)
    sys.path[:0] = [str(REPO / 'docs/evaluations'), str(REPO / 'docs/evaluations/tools')]
    from cpu_leases import lease
    with lease(Path(plan['state']), [0, 1]):
        os.sched_setaffinity(0, {0, 1})
        try:
            runtime = Docker(plan['dependencies'], plan['dependencies_tree_sha256'])
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            output = safe_owned(HERE / plan['output'])
            output.mkdir(parents=True, exist_ok=False)
            write_json(output / 'receipt.json', {'status': 'unknown', 'stage': 'offline runtime setup', 'error': str(error)})
            return
        results = [assess(s, HERE / plan['output'] / s['name'], runtime, plan.get('cases', CASES)) for s in plan['subjects']]
        if identity(runtime.dependencies) != runtime.identity:
            raise ValueError('shared dependency cache changed')
    write_json(HERE / plan['output'] / 'receipt.json', {'descriptor_sha256': DESCRIPTOR_SHA, 'plan_sha256': sha(args.plan.read_bytes()),
        'assessor_artifacts': assessor_artifacts, 'requested_cases': list(plan.get('cases', CASES)),
        'assay_sha256': assessor_artifacts['assay.py'], 'validator_sha256': assessor_artifacts['validate-controls.mjs'],
        'subjects': results, 'cpus': [0, 1], 'runner_native_provider_calls': 0, 'preparation_model_cost': None,
        'scope': 'assessor only; original scores untouched; delegated implementation cost unmetered; only recorded commands executed, no inferred full matrix'})


if __name__ == '__main__':
    main()
