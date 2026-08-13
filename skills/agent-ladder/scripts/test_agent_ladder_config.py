from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("agent_ladder_config.py")
SPEC = importlib.util.spec_from_file_location("agent_ladder_config", SCRIPT_PATH)
assert SPEC and SPEC.loader
router = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router)


class AgentLadderConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.codex_home = self.root / "codex-home"
        self.codex_home.mkdir()
        self.previous_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)

    def tearDown(self) -> None:
        if self.previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self.previous_codex_home
        self.temporary.cleanup()

    def config(self):
        return router.effective_config(self.project)

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--cwd", str(self.project), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
        )

    def test_defaults_resolve_terra_for_ordinary_implementation(self) -> None:
        config, _ = self.config()
        result = router.resolve_route(config, "implementation")
        self.assertEqual(result["candidates"][0]["id"], "gpt-5.6-terra")
        self.assertEqual(result["candidates"][0]["reasoning_effort"], "medium")

    def test_complex_route_requires_sol_tier(self) -> None:
        config, _ = self.config()
        result = router.resolve_route(config, "complex_implementation")
        self.assertEqual([item["alias"] for item in result["candidates"]], ["sol"])
        self.assertEqual(result["minimum_tier"], 200)

    def test_project_override_can_register_future_model(self) -> None:
        override = self.project / ".codex" / "agent-ladder.toml"
        override.parent.mkdir()
        override.write_text(
            """
[models.next]
id = "future-model-id"
tier = 300
enabled = true

[routes.critical]
models = ["next", "sol"]
reasoning_effort = "high"
minimum_tier = 200
""".strip(),
            encoding="utf-8",
        )
        config, loaded = self.config()
        result = router.resolve_route(config, "critical")
        self.assertIn(override, loaded)
        self.assertEqual(result["candidates"][0]["id"], "future-model-id")

    def test_denied_model_is_rejected(self) -> None:
        config, _ = self.config()
        config["models"]["forbidden"] = {"id": "gpt-luna", "tier": 999, "enabled": True}
        with self.assertRaisesRegex(router.ConfigError, "denied"):
            router.validate_config(config)

    def test_luna_remains_denied_when_configurable_patterns_are_empty(self) -> None:
        config, _ = self.config()
        config["denied_model_patterns"] = []
        config["models"]["forbidden"] = {"id": "gpt-luna", "tier": 999, "enabled": True}
        with self.assertRaisesRegex(router.ConfigError, "denied"):
            router.validate_config(config)

    def test_route_cannot_lower_global_floor(self) -> None:
        config, _ = self.config()
        config["models"]["tiny"] = {"id": "tiny-model", "tier": 50, "enabled": True}
        config["routes"]["tiny"] = {
            "models": ["tiny"],
            "reasoning_effort": "low",
            "minimum_tier": 50,
        }
        with self.assertRaisesRegex(router.ConfigError, "integer >= 100"):
            router.validate_config(config)

    def test_global_floor_cannot_be_lowered_below_terra_tier(self) -> None:
        config, _ = self.config()
        config["minimum_tier"] = 50
        with self.assertRaisesRegex(router.ConfigError, "integer >= 100"):
            router.validate_config(config)

    def test_critical_route_does_not_fall_back_below_route_floor(self) -> None:
        config, _ = self.config()
        config["models"]["sol"]["enabled"] = False
        with self.assertRaisesRegex(router.ConfigError, "no enabled model"):
            router.validate_config(config)

    def test_recursive_delegation_is_rejected(self) -> None:
        config, _ = self.config()
        config["policy"]["max_depth"] = 2
        with self.assertRaisesRegex(router.ConfigError, "must be 1"):
            router.validate_config(config)

    def test_parallel_limit_cannot_exceed_total_call_limit(self) -> None:
        config, _ = self.config()
        config["policy"]["max_parallel_agents"] = 4
        config["policy"]["max_child_calls"] = 3
        with self.assertRaisesRegex(router.ConfigError, "cannot exceed"):
            router.validate_config(config)

    def test_missing_explicit_override_is_rejected(self) -> None:
        missing = self.root / "missing-agent-ladder.toml"
        with self.assertRaisesRegex(router.ConfigError, "does not exist"):
            router.effective_config(self.project, missing)

    def test_required_review_reservation_cannot_be_disabled_persistently(self) -> None:
        config, _ = self.config()
        config["policy"]["reserve_required_review_call"] = False
        with self.assertRaisesRegex(router.ConfigError, "must be true"):
            router.validate_config(config)

    def test_manual_mode_allows_only_explicit_invocation(self) -> None:
        self.assertFalse(router.mode_allows("manual", "implicit"))
        self.assertTrue(router.mode_allows("manual", "explicit"))

    def test_off_mode_disables_all_routing(self) -> None:
        self.assertFalse(router.mode_allows("off", "implicit"))
        self.assertFalse(router.mode_allows("off", "explicit"))

    def test_project_mode_overrides_user_mode(self) -> None:
        (self.codex_home / "agent-ladder.mode").write_text("manual\n", encoding="utf-8")
        project_mode = self.project / ".codex" / "agent-ladder.mode"
        project_mode.parent.mkdir()
        project_mode.write_text("off\n", encoding="utf-8")
        config, _ = self.config()
        mode, source = router.effective_mode(config, self.project)
        self.assertEqual(mode, "off")
        self.assertEqual(source, str(project_mode))

    def test_set_mode_writes_only_requested_scope(self) -> None:
        path = router.set_mode(self.project, "project", "manual")
        self.assertEqual(path, self.project / ".codex" / "agent-ladder.mode")
        self.assertEqual(path.read_text(encoding="utf-8"), "manual\n")
        self.assertFalse((self.codex_home / "agent-ladder.mode").exists())

    def test_invalid_mode_file_is_rejected(self) -> None:
        path = self.project / ".codex" / "agent-ladder.mode"
        path.parent.mkdir()
        path.write_text("sometimes\n", encoding="utf-8")
        with self.assertRaisesRegex(router.ConfigError, "must contain"):
            router.read_mode_file(path)

    def test_resolve_cli_defaults_to_implicit_invocation(self) -> None:
        parser = router.build_parser()
        args = parser.parse_args(["resolve", "implementation"])
        self.assertEqual(args.invocation, "implicit")

    def test_manual_mode_blocks_implicit_cli_and_allows_explicit_cli(self) -> None:
        router.set_mode(self.project, "project", "manual")
        implicit = self.run_cli("resolve", "implementation")
        explicit = self.run_cli("resolve", "implementation", "--invocation", "explicit")
        self.assertEqual(implicit.returncode, 2)
        self.assertIn("manual mode requires explicit invocation", json.loads(implicit.stderr)["error"])
        self.assertEqual(explicit.returncode, 0)
        self.assertEqual(json.loads(explicit.stdout)["invocation"], "explicit")

    def test_off_mode_blocks_explicit_cli(self) -> None:
        router.set_mode(self.project, "project", "off")
        result = self.run_cli("resolve", "implementation", "--invocation", "explicit")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Agent Ladder is off", json.loads(result.stderr)["error"])

    def test_set_mode_does_not_write_when_effective_config_is_invalid(self) -> None:
        config_path = self.project / ".codex" / "agent-ladder.toml"
        config_path.parent.mkdir()
        config_path.write_text("minimum_tier = 50\n", encoding="utf-8")
        result = self.run_cli("set-mode", "off", "--scope", "project")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.project / ".codex" / "agent-ladder.mode").exists())

    def test_status_reports_project_mode_as_final_source(self) -> None:
        router.set_mode(self.project, "user", "manual")
        project_mode = router.set_mode(self.project, "project", "off")
        result = self.run_cli("status")
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["mode"], "off")
        self.assertEqual(payload["mode_source"], str(project_mode))

    def test_validate_toml_is_independent_of_invalid_mode_file(self) -> None:
        mode_path = self.project / ".codex" / "agent-ladder.mode"
        mode_path.parent.mkdir()
        mode_path.write_text("invalid\n", encoding="utf-8")
        override = self.root / "valid.toml"
        override.write_text("[policy]\nauto_upgrade = false\n", encoding="utf-8")
        result = self.run_cli("validate", str(override))
        self.assertEqual(result.returncode, 0)
        self.assertTrue(json.loads(result.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
