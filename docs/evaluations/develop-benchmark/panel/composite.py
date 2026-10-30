"""Verify the optional second package and identify the complete treatment."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

COMMIT = '0722921d5542fc593105c27bd52630babd8b8c2a'
MANIFEST_SHA256 = '18eb497a5c3c5aade93fe1982db0fbd2ab23d4a428fc552da6ee3cc520c9706d'
PACKAGE_SHA256 = '819308376b259ec99111ff44593b7196d9bf08666be5bc6b6f8124b100a5642c'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def package_hash(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('companion package contains a symlink')
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode()+b'\0'+bytes.fromhex(digest(p)))
    return h.hexdigest()

def identity(lock):
    if 'companion' not in lock:
        return lock['package_sha256']
    return hashlib.sha256(json.dumps(lock,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_component(root, pin):
    root = Path(root)
    if pin['package_sha256'] != PACKAGE_SHA256 or package_hash(root) != PACKAGE_SHA256:
        raise ValueError('companion package differs from lock')
    if (pin.get('source') != 'https://github.com/openai/plugins' or pin.get('source_path') != 'plugins/superpowers' or pin.get('version') != '6.3.0' or pin.get('source_commit') != COMMIT or pin.get('manifest_sha256') != MANIFEST_SHA256 or digest(root/'.codex-plugin/plugin.json') != MANIFEST_SHA256):
        raise ValueError('companion source or manifest differs')
    manifest=json.loads((root/'.codex-plugin/plugin.json').read_text())
    if (manifest['name'],manifest['version'],manifest.get('hooks')) != ('superpowers','6.3.0',{}):
        raise ValueError('unexpected companion manifest or hook boundary')
    skills={p.parent.name:digest(p) for p in sorted((root/'skills').glob('*/SKILL.md'))}
    if skills != pin['skills']:
        raise ValueError('companion skill inventory differs')
    return skills

def expected_plugins(arm, companion):
    if arm != 'develop':
        return []
    return sorted(['develop@law-config'] + (['superpowers@superpowers-local'] if companion else []))


def verify_inventory(arm, active_plugins, skill_paths, develop, companion, expected_skills):
    active_plugins = sorted(active_plugins)
    if active_plugins != expected_plugins(arm, True):
        raise ValueError('unexpected plugin inventory')
    superpowers = {name.removeprefix('superpowers:'): Path(path) for name, path in skill_paths.items() if name.startswith('superpowers:')}
    if arm == 'develop':
        develop_skills = {p.parent.name for p in (develop / 'skills').glob('*/SKILL.md')}
        expected_names = {'imagegen','openai-docs','review-agent','skill-creator','skill-installer'} | {'develop:'+n for n in develop_skills} | {'superpowers:'+n for n in expected_skills}
        if set(skill_paths) != expected_names:
            raise ValueError('unexpected full skill inventory')
        if set(superpowers) != set(expected_skills):
            raise ValueError('unexpected companion skill inventory')
        for name,path in superpowers.items():
            if path != companion / 'skills' / name / 'SKILL.md' or digest(path) != expected_skills[name]:
                raise ValueError('companion skill path or content differs')
    elif superpowers:
        raise ValueError('companion leaked to control')


def verify_marketplace(root):
    descriptor = Path(root) / '.agents/plugins/marketplace.json'
    if descriptor.is_symlink():
        raise ValueError('marketplace descriptor is a symlink')
    market = json.loads(descriptor.read_text())
    plugins = market.get('plugins', [])
    if (market.get('name') != 'superpowers-local' or len(plugins) != 1 or
            plugins[0].get('name') != 'superpowers' or
            plugins[0].get('source') != {'source': 'local', 'path': './plugins/superpowers'}):
        raise ValueError('unexpected companion marketplace')


def qualification_matches(qualification, lock):
    expected = identity(lock)
    actual = qualification.get('treatment_identity', qualification.get('package_sha256'))
    return qualification.get('package_sha256') == lock['package_sha256'] and actual == expected


def prepare_source(cache, volatile, pin=None):
    cache = Path(cache)
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git','init','--bare',str(cache)],check=True,stdout=subprocess.DEVNULL)
    exists = subprocess.run(['git','--git-dir',str(cache),'cat-file','-e',COMMIT+'^{commit}'],stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        subprocess.run(['git','--git-dir',str(cache),'fetch','--no-tags','https://github.com/openai/plugins.git',COMMIT],check=True)
    dest = Path(tempfile.mkdtemp(prefix='companion-source-',dir=volatile))
    subprocess.run(['git','clone','--quiet','--no-checkout',str(cache),str(dest)],check=True)
    subprocess.run(['git','-C',str(dest),'checkout','--quiet','--detach',COMMIT],check=True)
    package = dest/'plugins/superpowers'
    if pin is None:
        pin = component_pin(package)
    verify_component(package,pin)
    path = dest/'.agents/plugins/marketplace.json'
    original = json.loads(path.read_text())
    entries = [x for x in original['plugins'] if x['name']=='superpowers']
    if len(entries)!=1 or entries[0].get('source') != {'source':'local','path':'./plugins/superpowers'}:
        raise ValueError('pinned marketplace entry differs')
    path.write_text(json.dumps({'name':'superpowers-local','interface':{'displayName':'Codex official'},'plugins':entries},indent=2)+'\n')
    verify_marketplace(dest)
    return dest


def component_pin(root):
    root = Path(root)
    if package_hash(root) != PACKAGE_SHA256:
        raise ValueError('official companion package differs')
    return {'source':'https://github.com/openai/plugins','source_commit':COMMIT,
            'source_path':'plugins/superpowers','version':'6.3.0',
            'manifest_sha256':MANIFEST_SHA256,'package_sha256':PACKAGE_SHA256,
            'skills':{p.parent.name:digest(p) for p in sorted((root/'skills').glob('*/SKILL.md'))}}


def validate_common_component(spec, prior, candidate):
    expected = spec.get('common_companion')
    if expected is None:
        return
    if expected != {'source_commit': COMMIT, 'package_sha256': PACKAGE_SHA256}:
        raise ValueError('hypothesis has an unsupported common companion')
    a, b = prior.get('companion'), candidate.get('companion')
    if not a or a != b or any(a.get(k) != v for k,v in expected.items()):
        raise ValueError('hypothesis requires the same pinned companion in both treatments')


def component_set(lock):
    companion = lock.get('companion')
    return lock['package_sha256'], companion.get('package_sha256') if companion else None
