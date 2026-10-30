"""Exercise capability isolation against an ordinary native profile layout, without a model."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "develop-benchmark/panel"))
import environment as E
import stock


class StockControlTest(unittest.TestCase):
    def setUp(self):
        scratch = E.STATE / "volatile"
        scratch.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="control-check-", dir=scratch))
        work = root / "work"
        subprocess.run(["git", "init", "-q", work], check=True)
        self.home = root / "profile"
        self.home.mkdir()
        self.config = self.home / "config.toml"
        self.config.write_text('model="gpt-6.1-sol"\nmodel_reasoning_effort="medium"\nweb_search="disabled"\n'
                               'approval_policy="never"\nsandbox_mode="workspace-write"\n[features]\n'
                               'apps=false\nmemories=false\nremote_plugin=false\n[plugins._default]\nenabled=false\n')
        self.responses = {"app/list": {"data": []}, "mcpServerStatus/list": {"data": []},
                          "config/read": {"config": {}, "layers": [{"name": {"type": "user"}}]}}
        self.server = SimpleNamespace(work=str(work), home=self.home, rpc=lambda method, params: self.responses[method])
        self.skills = [{"name": s, "path": str(self.home / "skills/.system" / s / "SKILL.md")} for s in stock.SYSTEM_SKILLS]

    def audit(self):
        return stock.inventory(self.server, None, self.skills, [])

    def test_plain_profile_with_stock_skills_passes(self):
        observed = self.audit()
        self.assertEqual(observed["stock_skills"], sorted(stock.SYSTEM_SKILLS))
        self.assertEqual(observed["apps"], [])

    def test_app_or_hidden_second_page_fails(self):
        for method, response in (("app/list", {"data": [{"id": "some-app"}]}),
                                 ("mcpServerStatus/list", {"data": [], "nextCursor": "more"})):
            with self.subTest(method=method):
                self.responses[method] = response
                with self.assertRaisesRegex(ValueError, "apps or MCP"):
                    self.audit()
                self.responses[method] = {"data": []}

    def test_custom_effective_instructions_and_profile_override_fail(self):
        self.responses["config/read"]["config"] = {"developer_instructions": "Use another workflow"}
        with self.assertRaisesRegex(ValueError, "injects instructions"):
            self.audit()
        self.responses["config/read"]["config"] = {}
        with self.config.open("a") as dst:
            dst.write('[plugins."unexpected@test"]\nenabled=true\n')
        with self.assertRaisesRegex(ValueError, "authored profile"):
            self.audit()


    def test_project_layer_must_be_empty_in_effective_config_and_on_disk(self):
        from hashlib import sha256
        folder = Path(self.server.work) / ".codex"
        folder.mkdir()
        layer = {"name": {"type": "project", "dotCodexFolder": str(folder)},
                 "config": {}, "version": "sha256:" + sha256(b"{}").hexdigest()}
        self.responses["config/read"]["layers"].insert(0, layer)
        self.assertIn("project", self.audit()["config_layers"])
        layer["config"] = {"developer_instructions": "Run another workflow"}
        with self.assertRaisesRegex(ValueError, "project configuration"):
            self.audit()
        layer["config"] = {}
        (folder / "config.toml").write_text('personality="custom"\n')
        with self.assertRaisesRegex(ValueError, "project configuration"):
            self.audit()
