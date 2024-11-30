import argparse
import docker
import subprocess
import signal
import sys

# Docker client
client = docker.from_env()

# Container and server details
container_name = "comfy-env-frontend"
image_name = "comfy-env-manager-frontend"

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run the server with optional ComfyUI path.")
    parser.add_argument("--comfyui_path", type=str, required=True, help="Default ComfyUI path")
    parser.add_argument("--allow_running_multiple_containers", type=str, help="Allow running multiple containers", default="False")
    # Assert that the argument is "True" or "False"
    assert parser.parse_args().allow_running_multiple_containers in ["True", "False"], "Argument allow_running_multiple_containers must be 'True' or 'False'"
    return parser.parse_args()

def start_container():
    """Start the Docker container if it's not already running."""
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            print(f"Starting container: {container_name}")
            container.start()
        else:
            print(f"Container {container_name} is already running.")
    except docker.errors.NotFound:
        print(f"Container {container_name} not found. Creating and starting a new one.")
        client.containers.run(image_name, name=container_name, ports={"8000": 8000}, detach=True, remove=True)
    except Exception as e:
        print(f"Error starting container: {e}")

def stop_container():
    """Stop the Docker container if it's running."""
    try:
        container = client.containers.get(container_name)
        if container.status == "running":
            print(f"Stopping container: {container_name}")
            container.stop()
    except docker.errors.NotFound:
        print(f"Container {container_name} not found.")
    except Exception as e:
        print(f"Error stopping container: {e}")

def start_server(comfyui_path, allow_running_multiple_containers):
    """Start the Python server."""
    python_interpreter = sys.executable
    server_command = [python_interpreter, "app.py", "--allow_running_multiple_containers", str(allow_running_multiple_containers), "--comfyui_path", comfyui_path]
    print("Starting Python server...")
    return subprocess.Popen(server_command)

def shutdown(signal_received, frame):
    """Handle shutdown process."""
    print(f"Received signal: {signal_received}. Shutting down...")
    stop_container()
    sys.exit(0)

if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_arguments()
    print(args.allow_running_multiple_containers)

    # Register the shutdown handler
    signal.signal(signal.SIGINT, shutdown)

    # Start the container and server
    start_container()
    server_process = start_server(args.comfyui_path, args.allow_running_multiple_containers)

    # Wait for the server process to complete
    try:
        server_process.wait()
    except KeyboardInterrupt:
        shutdown(signal.SIGINT, None)