# pinokio_app/start_server.py  (patched)

from __future__ import annotations

import argparse
import json
import logging.config
import os
import re
import signal
import sys
from pathlib import Path

from comfydock_server.config import load_config, AppConfig
from comfydock_server.server import ComfyDockServer

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
_PLACEHOLDER_RE = re.compile(r"^\{\{env\.[^}]+}}$")


def is_placeholder(v: str | None) -> bool:
    return isinstance(v, str) and _PLACEHOLDER_RE.match(v) is not None


def to_int(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None  # keep old default if conversion fails


def to_bool(v: str | None) -> bool | None:
    if v is None:
        return None
    s = str(v).lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


# ────────────────────────────────────────────────────────────────────────────
# 1. Parse CLI – every value stays a string so placeholders survive.
# ────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Start ComfyDock Server (Pinokio)")
    p.add_argument("--db-file-path", type=str)
    p.add_argument("--user-settings-file-path", type=str)
    p.add_argument("--frontend-host-port", type=str)
    p.add_argument("--allow-multiple-containers", type=str,
                   help="true / false  (Pinokio passes {{env.*}} when unset)")
    p.add_argument("--config", type=Path,
                   help="Optional user config (default: ~/.comfydock/config.json)")
    return p.parse_args()


# ────────────────────────────────────────────────────────────────────────────
# 2. Translate CLI → overrides dict (skip placeholders).
# ────────────────────────────────────────────────────────────────────────────
def build_cli_overrides(ns: argparse.Namespace) -> dict:
    o: dict = {}

    if ns.db_file_path and not is_placeholder(ns.db_file_path):
        o.setdefault("defaults", {})["db_file_path"] = ns.db_file_path

    if ns.user_settings_file_path and not is_placeholder(ns.user_settings_file_path):
        o.setdefault("defaults", {})["user_settings_file_path"] = (
            ns.user_settings_file_path
        )

    allow_multi = to_bool(ns.allow_multiple_containers)
    if allow_multi is not None:            # None ⇒ placeholder or invalid
        o.setdefault("defaults", {})["allow_multiple_containers"] = allow_multi

    host_port = to_int(ns.frontend_host_port)
    if host_port is not None:
        o.setdefault("frontend", {})["default_host_port"] = host_port

    # Pinokio always launches from the repo root:
    o.setdefault("defaults", {})["comfyui_path"] = os.getcwd()
    return o


# ────────────────────────────────────────────────────────────────────────────
# 3. Load configs once.
# ────────────────────────────────────────────────────────────────────────────
def create_configs(args: argparse.Namespace) -> AppConfig:
    app_cfg = load_config(
        cli_overrides=build_cli_overrides(args),
        user_config_path=Path(__file__).with_name("logging_config.json"),
    )
    return app_cfg


# ────────────────────────────────────────────────────────────────────────────
# 4. Main runtime.
# ────────────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    app_cfg = create_configs(args)

    logging.config.dictConfig(app_cfg.logging.__root__)

    server = ComfyDockServer(app_cfg)

    def _graceful_exit(signum, _frame) -> None:
        print(f"\nReceived signal {signum}. Shutting down gracefully…")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    print("Starting ComfyDock Server …")
    server.start()

    try:
        while True:
            input()
    except (KeyboardInterrupt, EOFError):
        _graceful_exit(signal.SIGINT, None)


if __name__ == "__main__":
    main()
