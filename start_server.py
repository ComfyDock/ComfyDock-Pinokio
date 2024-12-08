import argparse
import docker
import subprocess
import signal
import sys

# Docker client
client = docker.from_env()

# Container and server details
CONTAINER_NAME = "comfy-env-frontend"
IMAGE_NAME = "akatzai/comfy-env-frontend"
FRONTEND_IMAGE_VERSION = "0.0.2"

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run the server with optional ComfyUI path.")
    parser.add_argument("--allow_running_multiple_containers", type=str, help="Allow running multiple containers", default="False")
    # Assert that the argument is "True" or "False"
    assert parser.parse_args().allow_running_multiple_containers in ["True", "False"], "Argument allow_running_multiple_containers must be 'True' or 'False'"
    return parser.parse_args()

def start_container():
    """Start the Docker container if it's not already running."""
    image_name_with_tag = f"{IMAGE_NAME}:{FRONTEND_IMAGE_VERSION}"
    
    try:
        # Try to pull the image from Docker Hub
        print(f"Pulling image {image_name_with_tag} from Docker Hub.")
        client.images.pull(image_name_with_tag)
        
        # Start the container
        container = client.containers.get(CONTAINER_NAME)
        if container.status != "running":
            print(f"Starting container: {CONTAINER_NAME}")
            container.start()
        else:
            print(f"Container {CONTAINER_NAME} is already running.")
    except docker.errors.NotFound:
        print(f"Container {CONTAINER_NAME} not found. Checking for image {image_name_with_tag}.")
        # Run the container after ensuring the image is available
        client.containers.run(image_name_with_tag, name=CONTAINER_NAME, ports={"8000": 8000}, detach=True, remove=True)
    except docker.errors.APIError as e:
        print(f"Error pulling image {image_name_with_tag}: {e}")
        raise e
    except Exception as e:
        print(f"Error starting container: {e}")
        raise e

def stop_container():
    """Stop the Docker container if it's running."""
    try:
        container = client.containers.get(CONTAINER_NAME)
        if container.status == "running":
            print(f"Stopping container: {CONTAINER_NAME}")
            container.stop()
    except docker.errors.NotFound:
        print(f"Container {CONTAINER_NAME} not found.")
    except Exception as e:
        print(f"Error stopping container: {e}")

def start_server(allow_running_multiple_containers):
    """Start the Python server."""
    python_interpreter = sys.executable
    server_command = [python_interpreter, "app.py", "--allow_running_multiple_containers", str(allow_running_multiple_containers)]
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

    # Register the shutdown handler
    signal.signal(signal.SIGINT, shutdown)

    # Start the container and server
    start_container()
    server_process = start_server(args.allow_running_multiple_containers)

    # Wait for the server process to complete
    try:
        server_process.wait()
    except KeyboardInterrupt:
        shutdown(signal.SIGINT, None)