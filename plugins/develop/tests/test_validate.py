"""Exercise release checks against isolated package copies, never installed skills."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[1]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_chunk(kind, payload=b""):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload)))


def png_header(width=64, height=64, depth=8, color=6, compression=0, interlace=0):
    return png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth,
                                         color, compression, 0, interlace))


def png_image(raw=None, color=6):
    if raw is None:
        raw = (b"\x00" + bytes(64 * (4 if color == 6 else 3))) * 64
    return (PNG_SIGNATURE + png_header(color=color)
            + png_chunk(b"IDAT", zlib.compress(raw)) + png_chunk(b"IEND"))


class PackageValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="develop-validation-", dir=ROOT.parent)
        self.assertEqual(Path(self.temp.name).resolve().parent, ROOT.parent.resolve())
        self.addCleanup(self.temp.cleanup)
        self.repository = Path(self.temp.name) / "repository"
        self.package = self.repository / "plugins/develop"
        shutil.copytree(ROOT, self.package, ignore=shutil.ignore_patterns(".git", ".agents", "__pycache__"))
        self.catalog = self.repository / ".agents/plugins/marketplace.json"
        self.catalog.parent.mkdir(parents=True)
        self.catalog.write_text(json.dumps({
            "name": "law-config",
            "plugins": [{
                "name": "develop",
                "source": {"source": "local", "path": "./plugins/develop"},
            }],
        }), encoding="utf-8")

    def validate(self, marketplace=True):
        command = [sys.executable, str(ROOT / "scripts/validate.py"), "--root", str(self.package)]
        if marketplace:
            command.extend(["--marketplace-root", str(self.repository)])
        return subprocess.run(
            command,
            capture_output=True, text=True, check=False,
        )

    def test_valid_package_passes(self):
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_codex_manifest(self, manifest):
        path = self.package / '.codex-plugin/plugin.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(manifest), encoding='utf-8')

    def portable_as_codex(self):
        manifest = json.loads((self.package / 'plugin.json').read_text(encoding='utf-8'))
        interface = manifest.pop('extensions')['com.openai']['interface']
        manifest.pop('$schema')
        return dict(manifest, skills='./skills/', interface=interface)

    def test_missing_codex_ingestion_manifest_fails(self):
        (self.package / '.codex-plugin/plugin.json').unlink(missing_ok=True)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.codex-plugin/plugin.json', result.stdout + result.stderr)

    def test_codex_manifest_rejects_portable_fields(self):
        manifest = json.loads((self.package / 'plugin.json').read_text(encoding='utf-8'))
        self.write_codex_manifest(manifest)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.codex-plugin/plugin.json', result.stdout + result.stderr)

    def test_codex_interface_must_be_top_level(self):
        manifest = self.portable_as_codex()
        manifest['extensions'] = {'com.openai': {'interface': manifest.pop('interface')}}
        self.write_codex_manifest(manifest)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.codex-plugin/plugin.json', result.stdout + result.stderr)

    def test_codex_skills_must_resolve_from_package_root(self):
        manifest = self.portable_as_codex()
        manifest['skills'] = '../skills/'
        self.write_codex_manifest(manifest)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.codex-plugin/plugin.json', result.stdout + result.stderr)

    def test_codex_metadata_must_match_portable_manifest(self):
        manifest = self.portable_as_codex()
        manifest['version'] = '0.0.0'
        self.write_codex_manifest(manifest)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.codex-plugin/plugin.json', result.stdout + result.stderr)

    def test_generator_recreates_codex_manifest(self):
        path = self.package / '.codex-plugin/plugin.json'
        path.unlink(missing_ok=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/generate_codex_manifest.py'),
             '--root', str(self.package)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), self.portable_as_codex())
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_skill_reference_fails(self):
        skill = self.package / "skills/develop/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\n[required](references/missing.md)\n", encoding="utf-8")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing.md", result.stdout + result.stderr)

    def test_catalog_cannot_escape_repository(self):
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["plugins"][0]["source"]["path"] = "../elsewhere"
        self.catalog.write_text(json.dumps(catalog), encoding="utf-8")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("catalog", result.stdout + result.stderr)

    def test_other_plugins_can_share_catalog(self):
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["plugins"].append({"name": "other", "source": "./plugins/other"})
        self.catalog.write_text(json.dumps(catalog), encoding="utf-8")
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nested_package_requires_repository_catalog(self):
        self.catalog.unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("marketplace.json", result.stdout + result.stderr)

    def test_installed_payload_does_not_require_repository_catalog(self):
        installed = Path(self.temp.name) / ".codex/plugins/develop"
        installed.parent.mkdir(parents=True)
        self.package.rename(installed)
        self.package = installed
        result = self.validate(marketplace=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_delivery_dependency_fails(self):
        (self.package / "skills/iterate/scripts/pipeline_review.py").unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pipeline_review", result.stdout + result.stderr)

    def test_invalid_delivery_dependency_fails(self):
        (self.package / "skills/iterate/scripts/pipeline_review.py").write_text(
            "def broken(:\n", encoding="utf-8",
        )
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("delivery helper pipeline_review", result.stdout + result.stderr)

    def test_installed_helpers_load_from_an_unrelated_directory(self):
        environment = {**os.environ, "PYTHONSAFEPATH": "1"}
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        for name in ("repository_inventory.py", "watch_pipelines.py"):
            with self.subTest(helper=name):
                result = subprocess.run(
                    [sys.executable, str(self.package / "skills/iterate/scripts" / name), "--help"],
                    cwd=self.temp.name, env=environment,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("--repo", result.stdout)
        self.assertEqual(list((self.package / "skills/iterate/scripts").rglob("__pycache__")), [])

    def test_skill_name_must_match_directory(self):
        path = self.package / "skills/clean/SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("name: clean", "name: wrong"), encoding="utf-8")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("name", result.stdout + result.stderr)

    def test_missing_kaizen_entrypoint_fails(self):
        (self.package / "skills/kaizen/SKILL.md").unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("eight entry points", result.stdout + result.stderr)

    def test_missing_upgrade_codex_entrypoint_fails(self):
        (self.package / "skills/upgrade-codex/SKILL.md").unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("eight entry points", result.stdout + result.stderr)

    def test_unregistered_skill_directory_fails(self):
        (self.package / "skills/unregistered").mkdir()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("eight entry points", result.stdout + result.stderr)

    def write_upgrade_codex_policy(self, policy):
        path = self.package / "skills/upgrade-codex/agents/openai.yaml"
        # Keep the real interface and replace the policy with hand-written
        # fixtures, so each case exercises the packaged CLI validator.
        original = path.read_text(encoding="utf-8")
        prefix, separator, suffix = original.partition("\npolicy:")
        self.assertTrue(separator, "upgrade-codex must ship an explicit invocation policy")
        remaining = suffix.splitlines(keepends=True)
        while remaining and (not remaining[0].strip() or remaining[0].startswith(" ")):
            remaining.pop(0)
        path.write_text(prefix + "\n" + policy + "".join(remaining), encoding="utf-8")

    def test_upgrade_codex_explicit_policy_passes(self):
        self.write_upgrade_codex_policy("policy:\n  allow_implicit_invocation: false\n")
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_upgrade_codex_implicit_policy_fails(self):
        self.write_upgrade_codex_policy("policy:\n  allow_implicit_invocation: true\n")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("allow_implicit_invocation", result.stdout + result.stderr)

    def test_upgrade_codex_missing_policy_fails(self):
        self.write_upgrade_codex_policy("")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("allow_implicit_invocation", result.stdout + result.stderr)

    def test_upgrade_codex_malformed_policy_fails(self):
        fixtures = (
            'policy:\n  allow_implicit_invocation: "false"\n',
            "policy:\n  allow_implicit_invocation: null\n",
            "policy:\n  allow_implicit_invocation: [false]\n",
            "policy:\n  allow_implicit_invocation: {value: false}\n",
            "policy:\nallow_implicit_invocation: false\n",
            "policy:\n  allow_implicit_invocation: false\n  allow_implicit_invocation: true\n",
            "policy:\n  allow_implicit_invocation: false\npolicy: true\n",
            "policy:\n  allow_implicit_invocation: false\npolicy : {allow_implicit_invocation: true}\n",
            'policy:\n  allow_implicit_invocation: false\n"policy": {allow_implicit_invocation: true}\n',
            "policy:\n  nested:\n    allow_implicit_invocation: false\n",
        )
        path = self.package / "skills/upgrade-codex/agents/openai.yaml"
        original = path.read_text(encoding="utf-8")
        for policy in fixtures:
            with self.subTest(policy=policy):
                path.write_text(original, encoding="utf-8")
                self.write_upgrade_codex_policy(policy)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("allow_implicit_invocation", result.stdout + result.stderr)

    def test_deep_clean_requires_explicit_policy(self):
        path = self.package / "skills/deep-clean/agents/openai.yaml"
        original = path.read_text(encoding="utf-8")
        for replacement in ("true", '"false"', "null"):
            with self.subTest(replacement=replacement):
                path.write_text(original.replace("allow_implicit_invocation: false",
                                                "allow_implicit_invocation: " + replacement), encoding="utf-8")
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("allow_implicit_invocation", result.stdout + result.stderr)
        path.write_text(original.split("policy:")[0], encoding="utf-8")
        self.assertNotEqual(self.validate().returncode, 0)

    def test_missing_deep_clean_entrypoint_fails(self):
        (self.package / "skills/deep-clean/SKILL.md").unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("eight entry points", result.stdout + result.stderr)

    def test_missing_icon_fails(self):
        (self.package / "skills/clean/assets/icon.png").unlink()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("icon", result.stdout + result.stderr)

    def test_icon_cannot_escape_skill(self):
        path = self.package / "skills/clean/agents/openai.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "./assets/icon.png", "./../iterate/assets/icon.png"), encoding="utf-8")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("asset", result.stdout + result.stderr)


    def test_metadata_rejects_wrong_duplicate_and_malformed_mappings(self):
        path = self.package / "skills/clean/agents/openai.yaml"
        original = path.read_text(encoding="utf-8")
        fixtures = {
            "wrong mapping": original.replace("interface:", "dependencies:"),
            "duplicate interface": original + original.removeprefix("---\n"),
            "duplicate value": original + '  display_name: "Duplicate"\n',
            "extra section": original + "unknown:\n  nested: true\n",
            "extra field": original + '  surprise: "Unknown"\n',
            "wrong indentation": original.replace("interface:", " interface:"),
            "unexpected scalar": original + "not a mapping\n",
            "second document": original + "---\npolicy:\n  allow_implicit_invocation: false\n",
        }
        for name, content in fixtures.items():
            with self.subTest(case=name):
                path.write_text(content, encoding="utf-8")
                result = self.validate()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("openai.yaml", result.stderr)

    def test_metadata_comments_and_json_quoted_values_pass(self):
        path = self.package / "skills/clean/agents/openai.yaml"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("interface:", "# UI metadata\ninterface:").replace(
            '"Develop: Clean"', '"Develop: Clean #1 \\"quoted\\""'), encoding="utf-8")
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_external_metadata_symlinks_are_rejected_before_read(self):
        spec = importlib.util.spec_from_file_location("develop_validator", ROOT / "scripts/validate.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        read_text = Path.read_text
        fixtures = ("plugin.json", ".codex-plugin/plugin.json", "skills/clean/SKILL.md",
                    "skills/clean/agents/openai.yaml", "skills/clean/agents")
        for relative in fixtures:
            with self.subTest(path=relative):
                path = self.package / relative
                external = Path(self.temp.name) / "external-metadata"
                path.rename(external)
                try:
                    path.symlink_to(external, target_is_directory=external.is_dir())
                except OSError as exc:
                    external.rename(path)
                    self.skipTest(f"symlink creation unavailable: {exc}")
                escaped_reads = []

                def guarded_read(candidate, *args, **kwargs):
                    if candidate.resolve().is_relative_to(external.resolve()):
                        escaped_reads.append(candidate)
                    return read_text(candidate, *args, **kwargs)

                try:
                    with mock.patch.object(Path, "read_text", guarded_read):
                        errors = validator.validate(self.package, self.repository)
                    self.assertEqual(escaped_reads, [], "metadata containment must precede reading")
                    self.assertTrue(any("escapes" in error and relative in error.replace("\\", "/")
                                        for error in errors), errors)
                finally:
                    path.unlink()
                    external.rename(path)

    def test_internal_metadata_symlink_passes(self):
        path = self.package / "skills/clean/agents/openai.yaml"
        target = path.with_name("ui.yaml")
        path.rename(target)
        try:
            path.symlink_to(target.name)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_portable_mcp_discovery_violates_skills_only_policy(self):
        (self.package / "mcp.json").write_text('{"mcpServers": {"extra": {"command": "unused"}}}',
                                               encoding="utf-8")
        result = self.validate()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("mcp.json", result.stderr)
        self.assertIn("skills-only", result.stderr)

    def test_legacy_components_violate_skills_only_policy(self):
        # These are legacy declarations. Rejection of hooks is package policy,
        # not evidence that a portable loader executes them.
        for relative in (".mcp.json", "hooks/hooks.json"):
            with self.subTest(path=relative):
                path = self.package / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
                try:
                    result = self.validate()
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(relative, result.stderr)
                    self.assertIn("skills-only", result.stderr)
                finally:
                    path.unlink()

    def test_portable_component_fields_violate_skills_only_policy(self):
        path = self.package / "plugin.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for key in ("dependencies", "mcpServers", "hooks"):
            with self.subTest(field=key):
                path.write_text(json.dumps(dict(original, **{key: {}})), encoding="utf-8")
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("skills-only", result.stderr)

    def test_legacy_manifest_component_fields_fail(self):
        original = self.portable_as_codex()
        for key in ("mcpServers", "hooks"):
            with self.subTest(field=key):
                self.write_codex_manifest(dict(original, **{key: {}}))
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(".codex-plugin/plugin.json", result.stderr)

    def test_component_reference_outside_discovery_paths_passes(self):
        path = self.package / "skills/clean/references/mcp.json"
        path.write_text("{}", encoding="utf-8")
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_png_accepts_rgb_rgba_and_all_scanline_filters(self):
        path = self.package / "skills/clean/assets/icon.png"
        for color, channels in ((2, 3), (6, 4)):
            with self.subTest(color=color):
                raw = b"".join(bytes([row % 5]) + bytes(64 * channels) for row in range(64))
                path.write_bytes(png_image(raw, color=color))
                result = self.validate()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_png_accepts_consecutive_idat_and_optional_palette(self):
        compressed = zlib.compress((b"\x00" + bytes(256)) * 64)
        path = self.package / "skills/clean/assets/icon.png"
        path.write_bytes(PNG_SIGNATURE + png_header() + png_chunk(b"PLTE", b"\x00\x00\x00")
                         + png_chunk(b"IDAT", compressed[:3]) + png_chunk(b"IDAT", compressed[3:])
                         + png_chunk(b"IEND"))
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_png_rejects_broken_chunk_structure_and_crc(self):
        path = self.package / "skills/clean/assets/icon.png"
        valid = png_image()
        compressed = zlib.compress((b"\x00" + bytes(256)) * 64)
        idat = png_chunk(b"IDAT", compressed)
        ihdr = png_header()
        end = png_chunk(b"IEND")
        fixtures = {
            "header only": valid[:24],
            "truncated chunk": valid[:-1],
            "bad IHDR crc": valid[:29] + bytes([valid[29] ^ 1]) + valid[30:],
            "bad IDAT crc": valid[:-13] + bytes([valid[-13] ^ 1]) + valid[-12:],
            "missing IEND": valid[:-12],
            "trailing bytes": valid + b"extra",
            "duplicate IHDR": PNG_SIGNATURE + ihdr + ihdr + idat + end,
            "missing IDAT": PNG_SIGNATURE + ihdr + end,
            "unknown critical chunk": PNG_SIGNATURE + ihdr + png_chunk(b"WHAT") + idat + end,
            "nonconsecutive IDAT": (PNG_SIGNATURE + ihdr + png_chunk(b"IDAT", compressed[:3])
                                    + png_chunk(b"tEXt", b"key\x00value")
                                    + png_chunk(b"IDAT", compressed[3:]) + end),
            "nonempty IEND": PNG_SIGNATURE + ihdr + idat + png_chunk(b"IEND", b"x"),
            "bad chunk name": PNG_SIGNATURE + ihdr + png_chunk(b"0aBX") + idat + end,
            "invalid reserved bit": PNG_SIGNATURE + ihdr + png_chunk(b"cabX") + idat + end,
            "bad palette size": PNG_SIGNATURE + ihdr + png_chunk(b"PLTE", b"x") + idat + end,
            "late palette": PNG_SIGNATURE + ihdr + idat + png_chunk(b"PLTE", b"rgb") + end,
            "duplicate palette": (PNG_SIGNATURE + ihdr + png_chunk(b"PLTE", b"rgb")
                                  + png_chunk(b"PLTE", b"rgb") + idat + end),
        }
        for name, content in fixtures.items():
            with self.subTest(case=name):
                path.write_bytes(content)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("icon", result.stderr)
                self.assertIn("FAIL:", result.stderr)

    def test_png_rejects_invalid_or_unbounded_decoded_scanlines(self):
        path = self.package / "skills/clean/assets/icon.png"
        raw = (b"\x00" + bytes(256)) * 64
        compressed = zlib.compress(raw)
        fixtures = {
            "invalid deflate": b"not deflate",
            "truncated deflate": compressed[:-1],
            "trailing deflate bytes": compressed + b"extra",
            "second deflate stream": compressed + compressed,
            "short scanline data": zlib.compress(raw[:-1]),
            "extra scanline data": zlib.compress(raw + b"x"),
            "invalid scanline filter": zlib.compress(b"\x05" + raw[1:]),
            "expands past declared image": zlib.compress(bytes(2 * 1024 * 1024)),
        }
        for name, payload in fixtures.items():
            with self.subTest(case=name):
                path.write_bytes(PNG_SIGNATURE + png_header() + png_chunk(b"IDAT", payload)
                                 + png_chunk(b"IEND"))
                result = self.validate()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("icon", result.stderr)
                self.assertIn("FAIL:", result.stderr)

    def test_png_rejects_unsupported_ancillary_chunks(self):
        path = self.package / "skills/clean/assets/icon.png"
        tail = png_chunk(b"IDAT", zlib.compress((b"\x00" + bytes(256)) * 64)) + png_chunk(b"IEND")
        fixtures = {
            "truncated pHYs": (b"pHYs", b"x"),
            "truncated sRGB": (b"sRGB", b""),
            "truncated gAMA": (b"gAMA", b"x"),
            "valid but unsupported metadata": (b"pHYs", struct.pack(">IIB", 1000, 1000, 1)),
        }
        for name, (kind, payload) in fixtures.items():
            with self.subTest(case=name):
                # Correct CRCs alone do not establish that a decoder accepts metadata.
                path.write_bytes(PNG_SIGNATURE + png_header() + png_chunk(kind, payload) + tail)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("unsupported PNG chunk", result.stderr)

    def test_png_rejects_unsupported_header_formats_and_extreme_dimensions(self):
        path = self.package / "skills/clean/assets/icon.png"
        tail = png_chunk(b"IDAT", zlib.compress(bytes(64 * 257))) + png_chunk(b"IEND")
        fixtures = {
            "huge dimensions": png_header(width=2 ** 31 - 1, height=2 ** 31 - 1),
            "16 bit": png_header(depth=16),
            "indexed": png_header(color=3),
            "unknown color": png_header(color=99),
            "interlaced": png_header(interlace=1),
            "invalid compression": png_header(compression=1),
        }
        for name, header in fixtures.items():
            with self.subTest(case=name):
                path.write_bytes(PNG_SIGNATURE + header + tail)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("icon", result.stderr)
                self.assertIn("FAIL:", result.stderr)


if __name__ == "__main__":
    unittest.main()
