import logging
import argparse
import os
import signal
import sys
import json
from pathlib import Path

from comfydock_server.config import ServerConfig
from comfydock_server.server import ComfyDockServer


def parse_str_with_default(default):
    def inner(value):
        if value.startswith("{{env.") and value.endswith("}}"):
            return default
        return value

    return inner


def parse_int_with_default(default):
    def inner(value):

        try:
            return int(value)
        except ValueError:
            # If the value looks like a templated env variable, return the default.
            if value.startswith("{{env.") and value.endswith("}}"):
                return default
            # Otherwise, let argparse complain.
            raise argparse.ArgumentTypeError(f"Invalid int value: {value}")

    return inner


def parse_bool_with_default(default):
    def inner(value):
        # Allow actual bools (if passed from code) or strings.
        if isinstance(value, bool):
            return value
        val = value.lower()
        if val in ["true", "1", "yes"]:
            return True
        elif val in ["false", "0", "no"]:
            return False
        elif value.startswith("{{env.") and value.endswith("}}"):
            return default
        else:
            raise argparse.ArgumentTypeError(f"Invalid bool value: {value}")

    return inner


def parse_args(config_data):
    parser = argparse.ArgumentParser(
        description="Start ComfyDock Server with custom configuration."
    )
    parser.add_argument(
        "--db-file-path",
        type=parse_str_with_default(config_data["defaults"]["db_file_path"]),
        help="Path to environments database file",
    )

    parser.add_argument(
        "--user-settings-file-path",
        type=parse_str_with_default(config_data["defaults"]["user_settings_file_path"]),
        help="Path to user settings file",
    )
    parser.add_argument(
        "--frontend-host-port",
        type=parse_int_with_default(config_data["frontend"]["default_host_port"]),
        help="Frontend host port",
    )
    parser.add_argument(
        "--allow-multiple-containers",
        type=parse_bool_with_default(config_data["defaults"]["allow_multiple_containers"]),
        help="Allow running multiple containers",
    )
    return parser.parse_args()



def signal_handler(signum, frame):
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    if "server" in globals():
        print("Stopping server...")
        server.stop()
    sys.exit(0)


def load_config():
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Configuration file not found at {config_path}")
        return {}
    
    
def setup_logging(logging_config):
    logging.config.dictConfig(logging_config)

def run():
    config_data = load_config()
    args = parse_args(config_data)
    
    setup_logging(config_data["logging"])

    # Create configuration with default values
    config = ServerConfig(
        comfyui_path=os.getcwd(),
        db_file_path=args.db_file_path or config_data["defaults"]["db_file_path"],
        user_settings_file_path=args.user_settings_file_path
        or config_data["defaults"]["user_settings_file_path"],
        frontend_image=config_data["frontend"]["image"],
        frontend_version=config_data["frontend"]["version"],
        frontend_container_port=config_data["frontend"]["container_port"],
        frontend_host_port=args.frontend_host_port
        or config_data["frontend"]["default_host_port"],
        backend_port=config_data["backend"]["port"],
        backend_host=config_data["backend"]["host"],
        allow_multiple_containers=(
            args.allow_multiple_containers
            if args.allow_multiple_containers is not None
            else config_data["defaults"]["allow_multiple_containers"]
        ),
    )

    # Initialize server
    server = ComfyDockServer(config)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        print("Starting server...")
        server.start()

        # Keep server running
        while True:

            try:
                input("")
            except KeyboardInterrupt:
                signal_handler(signal.SIGINT, None)
    finally:
        print("Stopping server...")
        server.stop()


if __name__ == "__main__":
    run()
