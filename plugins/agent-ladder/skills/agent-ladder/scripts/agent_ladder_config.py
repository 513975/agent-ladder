#!/usr/bin/env python3
"""Resolve and validate Agent Ladder TOML configuration."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - Python < 3.11
    raise SystemExit("Agent Ladder requires Python 3.11 or newer (tomllib).") from exc


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_DIR / "assets" / "default-config.toml"
ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
ALLOWED_REVIEW_MODES = {"risk_based", "always", "off"}
ALLOWED_MODES = {"auto", "manual", "off"}
ALLOWED_INVOCATIONS = {"implicit", "explicit"}
MINIMUM_CAPABILITY_TIER = 100
HARD_DENIED_MODEL_PATTERNS = (re.compile("luna", re.IGNORECASE),)


class ConfigError(ValueError):
    """Raised when configuration cannot be used safely."""


def load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration root must be a table: {path}")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def config_paths(cwd: Path, explicit: Path | None = None) -> list[Path]:
    codex_home_value = os.environ.get("CODEX_HOME")
    codex_home = Path(codex_home_value).expanduser() if codex_home_value else Path.home() / ".codex"
    paths = [DEFAULT_CONFIG, codex_home / "agent-ladder.toml", cwd / ".codex" / "agent-ladder.toml"]
    if explicit is not None:
        paths.append(explicit.expanduser().resolve())
    return paths


def codex_home() -> Path:
    value = os.environ.get("CODEX_HOME")
    return Path(value).expanduser() if value else Path.home() / ".codex"


def mode_paths(cwd: Path) -> list[Path]:
    return [codex_home() / "agent-ladder.mode", cwd / ".codex" / "agent-ladder.mode"]


def read_mode_file(path: Path) -> str:
    try:
        mode = path.read_text(encoding="utf-8").strip().lower()
    except OSError as exc:
        raise ConfigError(f"Cannot read mode file {path}: {exc}") from exc
    if mode not in ALLOWED_MODES:
        raise ConfigError(f"Mode file {path} must contain one of {sorted(ALLOWED_MODES)}")
    return mode


def effective_mode(config: dict[str, Any], cwd: Path) -> tuple[str, str]:
    mode = config["policy"]["mode"]
    source = "configuration"
    for path in mode_paths(cwd):
        if path.exists():
            mode = read_mode_file(path)
            source = str(path)
    return mode, source


def mode_allows(mode: str, invocation: str) -> bool:
    if invocation not in ALLOWED_INVOCATIONS:
        raise ConfigError(f"invocation must be one of {sorted(ALLOWED_INVOCATIONS)}")
    return mode == "auto" or (mode == "manual" and invocation == "explicit")


def set_mode(cwd: Path, scope: str, mode: str) -> Path:
    if mode not in ALLOWED_MODES:
        raise ConfigError(f"mode must be one of {sorted(ALLOWED_MODES)}")
    if scope == "user":
        path = codex_home() / "agent-ladder.mode"
    elif scope == "project":
        path = cwd / ".codex" / "agent-ladder.mode"
    else:
        raise ConfigError("scope must be 'user' or 'project'")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(f"{mode}\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise ConfigError(f"Cannot write mode file {path}: {exc}") from exc
    return path


def effective_config(cwd: Path, explicit: Path | None = None) -> tuple[dict[str, Any], list[Path]]:
    if explicit is not None and not explicit.expanduser().resolve().is_file():
        raise ConfigError(f"Explicit configuration file does not exist: {explicit.expanduser().resolve()}")
    merged: dict[str, Any] = {}
    loaded: list[Path] = []
    for path in config_paths(cwd, explicit):
        if path == DEFAULT_CONFIG or path.exists():
            merged = deep_merge(merged, load_toml(path))
            loaded.append(path)
    validate_config(merged)
    return merged, loaded


def _require_int(value: Any, field: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{field} must be an integer >= {minimum}")
    return value


def _patterns(config: dict[str, Any]) -> list[re.Pattern[str]]:
    raw_patterns = config.get("denied_model_patterns", [])
    if not isinstance(raw_patterns, list) or not all(isinstance(item, str) and item for item in raw_patterns):
        raise ConfigError("denied_model_patterns must be an array of non-empty regular expressions")
    compiled: list[re.Pattern[str]] = []
    for pattern in raw_patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            raise ConfigError(f"Invalid denied model pattern {pattern!r}: {exc}") from exc
    return compiled


def _is_denied(alias: str, model_id: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(
        pattern.search(alias) or pattern.search(model_id)
        for pattern in [*HARD_DENIED_MODEL_PATTERNS, *patterns]
    )


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != 1:
        raise ConfigError("version must be 1")

    global_floor = _require_int(config.get("minimum_tier"), "minimum_tier", MINIMUM_CAPABILITY_TIER)
    patterns = _patterns(config)

    policy = config.get("policy")
    if not isinstance(policy, dict):
        raise ConfigError("policy must be a table")
    if policy.get("mode") not in ALLOWED_MODES:
        raise ConfigError(f"policy.mode must be one of {sorted(ALLOWED_MODES)}")
    if not isinstance(policy.get("auto_upgrade"), bool):
        raise ConfigError("policy.auto_upgrade must be true or false")
    if policy.get("review_mode") not in ALLOWED_REVIEW_MODES:
        raise ConfigError(f"policy.review_mode must be one of {sorted(ALLOWED_REVIEW_MODES)}")
    if policy.get("reserve_required_review_call") is not True:
        raise ConfigError(
            "policy.reserve_required_review_call must be true; waive a critical review only for the current task"
        )
    max_parallel = _require_int(policy.get("max_parallel_agents"), "policy.max_parallel_agents", 1)
    max_calls = _require_int(policy.get("max_child_calls"), "policy.max_child_calls", 1)
    if max_parallel > max_calls:
        raise ConfigError("policy.max_parallel_agents cannot exceed policy.max_child_calls")
    if policy.get("max_depth") != 1:
        raise ConfigError("policy.max_depth must be 1; Agent Ladder forbids recursive child delegation")
    _require_int(policy.get("max_retries"), "policy.max_retries", 0)

    models = config.get("models")
    if not isinstance(models, dict) or not models:
        raise ConfigError("models must be a non-empty table")

    normalized_models: dict[str, tuple[str, int, bool]] = {}
    for alias, model in models.items():
        if not isinstance(alias, str) or not alias or not isinstance(model, dict):
            raise ConfigError("each model must be a named table")
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ConfigError(f"models.{alias}.id must be a non-empty string")
        tier = _require_int(model.get("tier"), f"models.{alias}.tier", 0)
        enabled = model.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"models.{alias}.enabled must be true or false")
        if _is_denied(alias, model_id, patterns):
            raise ConfigError(f"models.{alias} is denied by denied_model_patterns")
        normalized_models[alias] = (model_id, tier, enabled)

    routes = config.get("routes")
    if not isinstance(routes, dict) or not routes:
        raise ConfigError("routes must be a non-empty table")

    for route_name, route in routes.items():
        if not isinstance(route, dict):
            raise ConfigError(f"routes.{route_name} must be a table")
        aliases = route.get("models")
        if not isinstance(aliases, list) or not aliases or not all(isinstance(alias, str) for alias in aliases):
            raise ConfigError(f"routes.{route_name}.models must be a non-empty string array")
        unknown = [alias for alias in aliases if alias not in normalized_models]
        if unknown:
            raise ConfigError(f"routes.{route_name} references unknown models: {unknown}")
        effort = route.get("reasoning_effort")
        if effort not in ALLOWED_EFFORTS:
            raise ConfigError(f"routes.{route_name}.reasoning_effort must be one of {sorted(ALLOWED_EFFORTS)}")
        route_floor = route.get("minimum_tier", global_floor)
        route_floor = _require_int(route_floor, f"routes.{route_name}.minimum_tier", global_floor)
        eligible = [
            alias
            for alias in aliases
            if normalized_models[alias][2] and normalized_models[alias][1] >= route_floor
        ]
        if not eligible:
            raise ConfigError(f"routes.{route_name} has no enabled model at tier {route_floor} or above")


def resolve_route(config: dict[str, Any], route_name: str) -> dict[str, Any]:
    routes = config["routes"]
    if route_name not in routes:
        raise ConfigError(f"Unknown route {route_name!r}; choose one of {sorted(routes)}")

    route = routes[route_name]
    floor = max(config["minimum_tier"], route.get("minimum_tier", config["minimum_tier"]))
    patterns = _patterns(config)
    candidates: list[dict[str, Any]] = []
    for alias in route["models"]:
        model = config["models"][alias]
        if not model.get("enabled", True) or model["tier"] < floor:
            continue
        if _is_denied(alias, model["id"], patterns):
            continue
        candidates.append(
            {
                "alias": alias,
                "id": model["id"],
                "tier": model["tier"],
                "reasoning_effort": route["reasoning_effort"],
            }
        )

    if not candidates:
        raise ConfigError(f"Route {route_name!r} has no eligible candidates at tier {floor} or above")
    return {"route": route_name, "minimum_tier": floor, "candidates": candidates}


def _json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project directory used for override discovery")
    parser.add_argument("--config", type=Path, help="Explicit final override file")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("effective", help="Print the merged, validated configuration")
    resolve = subparsers.add_parser("resolve", help="Resolve an ordered candidate list for one route")
    resolve.add_argument("route")
    resolve.add_argument("--invocation", choices=sorted(ALLOWED_INVOCATIONS), default="implicit")
    validate = subparsers.add_parser("validate", help="Validate a TOML override after merging it with defaults")
    validate.add_argument("path", type=Path)
    subparsers.add_parser("paths", help="Print configuration search paths")
    subparsers.add_parser("status", help="Print the effective mode and whether routing is active")
    set_mode_parser = subparsers.add_parser("set-mode", help="Set auto, manual, or off mode")
    set_mode_parser.add_argument("mode", choices=sorted(ALLOWED_MODES))
    set_mode_parser.add_argument("--scope", choices=["user", "project"], default="project")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = args.cwd.expanduser().resolve()
    try:
        if args.command == "paths":
            _json(
                {
                    "config_paths": [str(path) for path in config_paths(cwd, args.config)],
                    "mode_paths": [str(path) for path in mode_paths(cwd)],
                }
            )
            return 0

        if args.command == "set-mode":
            config, loaded = effective_config(cwd, args.config)
            path = set_mode(cwd, args.scope, args.mode)
            mode, source = effective_mode(config, cwd)
            _json(
                {
                    "updated": str(path),
                    "mode": mode,
                    "mode_source": source,
                    "sources": [str(item) for item in loaded],
                }
            )
            return 0

        explicit = args.path if args.command == "validate" else args.config
        config, loaded = effective_config(cwd, explicit)
        if args.command == "validate":
            _json({"valid": True, "sources": [str(path) for path in loaded]})
            return 0
        mode, mode_source = effective_mode(config, cwd)
        if args.command == "effective":
            _json(
                {
                    "sources": [str(path) for path in loaded],
                    "mode": mode,
                    "mode_source": mode_source,
                    "config": config,
                }
            )
        elif args.command == "resolve":
            if not mode_allows(mode, args.invocation):
                reason = "manual mode requires explicit invocation" if mode == "manual" else "Agent Ladder is off"
                raise ConfigError(f"Routing disabled: {reason}")
            result = resolve_route(config, args.route)
            result["sources"] = [str(path) for path in loaded]
            result["mode"] = mode
            result["mode_source"] = mode_source
            result["invocation"] = args.invocation
            _json(result)
        elif args.command == "status":
            _json(
                {
                    "mode": mode,
                    "mode_source": mode_source,
                    "implicit_routing": mode_allows(mode, "implicit"),
                    "explicit_routing": mode_allows(mode, "explicit"),
                    "plugin_hard_disable": "Use the Codex plugin toggle",
                    "sources": [str(path) for path in loaded],
                }
            )
        return 0
    except ConfigError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
