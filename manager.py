import os
import subprocess
import sys
import json

USERDATA_FILE = "userdata.json"

def check_docker_installed():
    print("Checking if Docker is installed...")
    """Check if Docker is installed and prompt for installation if not."""
    try:
        subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE)
        print("Docker is installed.")
    except FileNotFoundError:
        print("Docker is not installed. Please install Docker from https://www.docker.com/get-started and try again.")
        sys.exit(1)

def save_user_data(data):
    """Save user data to a JSON file."""
    with open(USERDATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print(f"User data saved to {USERDATA_FILE}")

def load_user_data():
    """Load user data from the JSON file."""
    if os.path.exists(USERDATA_FILE):
        with open(USERDATA_FILE, "r") as f:
            return json.load(f)
    return None

def setup_comfyui_path():
    """Set up the ComfyUI path for models, workflows, and settings."""
    user_data = load_user_data()
    if user_data and "comfyui_path" in user_data:
        return user_data["comfyui_path"]

    print("No user data found. Let's set up your ComfyUI environment.")
    comfyui_path = input("Do you have an existing ComfyUI installation? Enter its path or leave blank to set up a new one: ").strip()

    if comfyui_path and os.path.exists(comfyui_path):
        required_dirs = ["models", "user", "input", "output"]
        missing_dirs = [d for d in required_dirs if not os.path.exists(os.path.join(comfyui_path, d))]
        if missing_dirs:
            print(f"The following directories are missing: {', '.join(missing_dirs)}")
            create_dirs = input("Would you like to create the missing directories? (yes/no): ").strip().lower()
            if create_dirs == "yes":
                for d in missing_dirs:
                    os.makedirs(os.path.join(comfyui_path, d), exist_ok=True)
            else:
                print("Missing directories not created. Existing structure will be used.")
    else:
        print("No valid existing ComfyUI installation found.")
        default_path = os.path.join(os.getcwd(), "ComfyUI")
        comfyui_path = input(f"Enter a path to set up a new ComfyUI installation (default: {default_path}): ").strip() or default_path
        if os.path.exists(comfyui_path):
            print("Path already exists. Please provide a new location.")
            return setup_comfyui_path()

        print("Setting up new ComfyUI installation...")
        try:
            subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", comfyui_path], check=True)
            required_dirs = ["models", "user", "input", "output"]
            for d in required_dirs:
                os.makedirs(os.path.join(comfyui_path, d), exist_ok=True)
            print(f"ComfyUI successfully set up at {comfyui_path}")
        except subprocess.CalledProcessError:
            print("Failed to clone ComfyUI repository. Please check your connection and try again.")
            sys.exit(1)

    save_user_data({"comfyui_path": comfyui_path})
    return comfyui_path

def pull_docker_image(image_name):
    """Pull a Docker image from Docker Hub."""
    print(f"Pulling Docker image: {image_name}")
    subprocess.run(["docker", "pull", image_name], check=True)

def create_environment(name, base_image, comfyui_path):
    """Create a new ComfyUI Docker environment."""
    print(f"Creating environment: {name}")
    os.makedirs(f"./envs/{name}", exist_ok=True)
    docker_command = [
        "docker", "run", "-d",
        "--name", name,
        "-v", f"{comfyui_path}/models:/app/ComfyUI/models",
        "-v", f"{comfyui_path}/user:/app/ComfyUI/user",
        "-v", f"{comfyui_path}/input:/app/ComfyUI/input",
        "-v", f"{comfyui_path}/output:/app/ComfyUI/output",
        base_image
    ]
    subprocess.run(docker_command)
    print(f"Environment '{name}' created successfully.")

def list_environments():
    """List all active Docker environments."""
    print("Listing all Docker environments:")
    subprocess.run(["docker", "ps", "-a"])

def run_environment(image_name, container_name, comfyui_path):
    """Run a Docker container with the specified options."""
    print(f"Running Docker container: {container_name}")
    docker_command = [
        "docker", "run", "-d", "--rm",
        "--gpus", "all",  # Enable GPU access
        "--name", container_name,
        "-p", "8188:8188",  # Map port 8188 for ComfyUI
        "-v", f"{comfyui_path}/models:/app/ComfyUI/models",
        "-v", f"{comfyui_path}/user:/app/ComfyUI/user",
        "-v", f"{comfyui_path}/input:/app/ComfyUI/input",
        "-v", f"{comfyui_path}/output:/app/ComfyUI/output",
        image_name
    ]
    subprocess.run(docker_command, check=True)
    print(f"ComfyUI is running at http://localhost:8188")

def delete_environment(name):
    """Remove a specific Docker environment."""
    print(f"Removing environment: {name}")
    subprocess.run(["docker", "rm", "-f", name])
    print(f"Environment '{name}' removed successfully.")

def main():
    check_docker_installed()
    comfyui_path = setup_comfyui_path()

    while True:
        print("\nComfyUI Environment Manager")
        print("1. Create Environment")
        print("2. Pull Environment")
        print("3. List Environments")
        print("4. Run Environment")
        print("5. Delete Environment")
        print("6. Exit")

        choice = input("Choose an option: ")
        if choice == "1":
            env_name = input("Enter a name for the environment: ")
            base_image = input("Enter the base Docker image (e.g., developer/comfyui:tag): ")
            create_environment(env_name, base_image, comfyui_path)
        elif choice == "2":
            image_name = input("Enter the Docker image name to pull (e.g., developer/comfyui:tag): ")
            pull_docker_image(image_name)
        elif choice == "3":
            list_environments()
        elif choice == "4":
            image_name = input("Enter the Docker image name (e.g., developer/comfyui:tag): ")
            container_name = input("Enter a name for the container: ")
            run_environment(image_name, container_name, comfyui_path)
        elif choice == "5":
            env_name = input("Enter the name of the environment to delete: ")
            delete_environment(env_name)
        elif choice == "6":
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
