import argparse
import time
import subprocess
import signal
import sys

# Import functions from docker_utils instead of creating our own client.
from utils.docker_utils import (
    try_pull_image,
    get_container,
    run_container,
    stop_container as docker_stop_container,
)

# Container and server details
CONTAINER_NAME = "comfy-env-frontend"
IMAGE_NAME = "akatzai/comfy-env-frontend"
FRONTEND_IMAGE_VERSION = "0.5.1"


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the server with optional ComfyUI path."
    )
    parser.add_argument(
        "--allow_running_multiple_containers",
        type=str,
        help="Allow running multiple containers",
        default="False",
    )
    # Assert that the argument is "True" or "False"
    args = parser.parse_args()
    assert args.allow_running_multiple_containers in [
        "True",
        "False",
    ], "Argument allow_running_multiple_containers must be 'True' or 'False'"
    return args


def start_container():
    """Start the Docker container if it's not already running."""
    image_name_with_tag = f"{IMAGE_NAME}:{FRONTEND_IMAGE_VERSION}"

    try:
        # Use docker utils to check for and pull the image if needed.
        try_pull_image(image_name_with_tag)

        # Check if the container exists.
        try:
            container = get_container(CONTAINER_NAME)
            if container.status == "running":
                print(f"Stopping running container: {CONTAINER_NAME}")
                docker_stop_container(container, timeout=0)
            print(f"Starting new container: {CONTAINER_NAME}")
            time.sleep(1)
            run_container(
                image=image_name_with_tag,
                name=CONTAINER_NAME,
                ports={"8000": 8000},
                detach=True,
                remove=True,
            )
        except Exception as e:
            # If the container is not found, then run a new container.
            print(f"Container {CONTAINER_NAME} not found. Running a new container.")
            run_container(
                image=image_name_with_tag,
                name=CONTAINER_NAME,
                ports={"8000": 8000},
                detach=True,
                remove=True,
            )
    except Exception as e:
        print(f"Error starting container: {e}")
        raise


def stop_container():
    """Stop the Docker container if it's running."""
    try:
        container = get_container(CONTAINER_NAME)
        if container.status == "running":
            print(f"Stopping container: {CONTAINER_NAME}")
            docker_stop_container(container)
    except Exception as e:
        print(f"Error stopping container: {e}")


def start_server(allow_running_multiple_containers):
    """Start the Python server."""
    python_interpreter = sys.executable
    server_command = [
        python_interpreter,
        "app.py",
        "--allow_running_multiple_containers",
        str(allow_running_multiple_containers),
    ]
    print("Starting Python server...")
    return subprocess.Popen(server_command)


def shutdown(signal_received, frame):
    """Handle shutdown process."""
    print(f"Received signal: {signal_received}. Shutting down...")
    stop_container()
    sys.exit(0)


if __name__ == "__main__":
    # Parse command-line arguments.
    args = parse_arguments()

    # Register the shutdown handler.
    signal.signal(signal.SIGINT, shutdown)

    # Start the container and server.
    start_container()
    server_process = start_server(args.allow_running_multiple_containers)

    # Wait for the server process to complete.
    try:
        server_process.wait()
    except KeyboardInterrupt:
        shutdown(signal.SIGINT, None)
