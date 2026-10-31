"""A retained report binds the receipted source only during the existing stock gate."""
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark
import efficiency_pilot as P
import composite


class ReportReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.old = self.root / "volatile/companion-source-old"
        self.fresh = self.root / "volatile/companion-source-new"
        for source in (self.old, self.fresh):
            catalog = source / ".agents/plugins/marketplace.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_bytes(b"pinned catalog")
        self.home = self.root / "attempts/black/develop/profile"
        self.home.mkdir(parents=True)
        self.config = self.home / "config.toml"
        self.raw = f'[marketplaces.superpowers-local]\nsource_type="local"\nsource="{self.old}"\n'.encode()
        self.config.write_bytes(self.raw)
        self.inv = {"config_sha256":sha256(self.raw).hexdigest(), "plugins":composite.expected_plugins("develop", True),
                    "skills":[], "disabled_repository_skills":[],
                    "stock":{"apps":[], "mcp":[], "repository_instructions_sha256":{}}}
        self.turn = {"threadId":"thread", "effort":P.E.PANEL["effort"], "input":[
            {"type":"text", "text":"$develop:develop prompt"},
            {"type":"skill", "name":P.E.host.SKILL, "path":str(self.root / "installed/skills/develop/SKILL.md")}]}
        server = Mock()
        server.rpc.side_effect = lambda method, params: {"skills/list":{"data":[]}, "plugin/list":{"marketplaces":[
            {"plugins":[{"id":p, "enabled":True, "installed":True} for p in self.inv["plugins"]]}]}}[method]
        for target, attribute, value in ((P.B,"STATE",self.root), (P.E.host,"COMPANION",{"source_commit":"pin"}),
                (P.E.host,"COMPANION_SOURCE",str(self.fresh))):
            self.enterContext(patch.object(target, attribute, value))
        for target, attribute, kwargs in (
                (P.C,"run_dir",dict(return_value=self.root)),
                (P.C,"read_attempt",dict(return_value={"state":"completed", "root":"thread", "thread_start":{"cwd":str(self.root)}})),
                (P.C,"prompt",dict(return_value="prompt")), (P.C,"receipt",dict(return_value={})),
                (P.E,"read",dict(side_effect=lambda path:self.inv if path.name == "inventory.json" else self.turn)),
                (P.C.controller,"STOCK",dict(return_value=server)), (P.C.controller,"verify_hooks",{}),
                (P.N,"git",dict(return_value=b"pin\n")),
                (composite,"verify_component",{}), (composite,"verify_marketplace",{})):
            self.enterContext(patch.object(target, attribute, **kwargs))
        self.enterContext(patch.dict(P.os.environ, BENCHMARK_CODEX="unused"))
        self.gate = self.enterContext(patch.object(P.stock, "inventory", side_effect=self.stock_gate))

    def stock_gate(self, *args):
        self.assertEqual(P.E.host.COMPANION_SOURCE, str(self.old))
        return {"repository_instructions_sha256":{}}

    def test_report_replays_launch_hash_with_terminal_trust_and_restores_source(self):
        self.config.write_bytes(self.raw + f'\n[projects."{self.root}"]\ntrust_level="trusted"\n'.encode())
        _, proof = P.check_input("report", "black", "develop")
        self.gate.assert_called_once()
        self.assertEqual(proof["final_config_sha256"], P.E.sha(self.config))
        self.assertEqual(P.E.host.COMPANION_SOURCE, str(self.fresh))

    def test_tamper_fails_before_gate_and_gate_exception_restores_source(self):
        self.config.write_bytes(self.raw + b"# changed launch bytes\n")
        with self.assertRaisesRegex(ValueError, "receipt"):
            P.check_input("report", "black", "develop")
        self.gate.assert_not_called()
        self.config.write_bytes(self.raw)
        self.gate.side_effect = ValueError("stock gate failed")
        with self.assertRaisesRegex(ValueError, "stock gate failed"):
            P.check_input("report", "black", "develop")
        self.assertEqual(P.E.host.COMPANION_SOURCE, str(self.fresh))
