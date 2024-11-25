import tarfile
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import docker
from docker.types import Mount, DeviceRequest
import json
import os
import uvicorn
from git import Repo
import posixpath
import re
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import tempfile

# Constants
FRONTEND_ORIGIN = "http://localhost:8000"
CONTAINER_COMFYUI_PATH = "/app/ComfyUI"
SIGNAL_TIMEOUT = 2
BLACKLIST_REQUIREMENTS = ['torch']
EXCLUDE_CUSTOM_NODE_DIRS = ['__pycache__', 'ComfyUI-Manager']
INCLUDE_USER_COMFYUI_DIRS = ['models', 'input', 'output', 'user']
COMFYUI_PORT = 8188
DB_FILE = "environments.json"
STOP_OTHER_RUNNING_CONTAINERS = True

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],  # Frontend's origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

try: 
    client = docker.from_env()
except docker.errors.DockerException:
    raise HTTPException(status_code=500, detail="Failed to connect to Docker. Please ensure your Docker client is running.")


def save_environments(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Helper function to load and save JSON data
def load_environments():
    environments = []
    if Path(DB_FILE).exists():
        with open(DB_FILE, "r") as f:
            environments = json.load(f)
    
    # Query the database for the status of each container and ensure they match the status in the database
    for env in environments:
        try:
            container = client.containers.get(env["id"])
        except docker.errors.NotFound:
            env["status"] = "dead"
        except Exception as e:
            return HTTPException(status_code=500, detail=str(e))
        else:
            env["status"] = container.status
            
    # save the updated statuses
    save_environments(environments)
    
    return environments



# Pydantic model for environment creation
class Environment(BaseModel):
    name: str
    image: str
    id: str = ""
    status: str = ""
    command: str = ""
    comfyui_path: str = ""
    options: dict = {}
    metadata: dict = {}


def ensure_directory_exists(container, path):
    """Ensure that a directory exists in the container."""
    try:
        # Execute a command to create the directory if it doesn't exist
        container.exec_run(f"mkdir -p {path}")
    except docker.errors.APIError as e:
        print(f"Error creating directory {path} in container: {e}")
        raise

def copy_to_container(container_id: str, source_path: str, container_path: str, exclude_dirs: list = []):
    try:
        container = client.containers.get(container_id)

        # Ensure the target directory exists in the container
        ensure_directory_exists(container, container_path)

        # Use a temporary directory for the tar file
        with tempfile.TemporaryDirectory() as temp_dir:
            tar_path = Path(temp_dir) / "archive.tar"

            # Create a tar archive of the source directory or file
            with tarfile.open(tar_path, mode="w") as archive:
                # Add each file in the source directory to the archive
                for root, dirs, files in os.walk(source_path):
                    # Modify dirs in-place to exclude specified directories
                    dirs[:] = [d for d in dirs if d not in exclude_dirs]
                    for file in files:
                        full_path = Path(root) / file
                        # Calculate the relative path to maintain the directory structure
                        relative_path = full_path.relative_to(source_path)
                        archive.add(str(full_path), arcname=str(relative_path))

            # Send the tar archive to the container
            with open(tar_path, "rb") as tar_data:
                print(f"Sending {source_path} to {container_id}:{container_path}")
                try:
                    container.put_archive(container_path, tar_data)
                    print(f"Copied {source_path} to {container_id}:{container_path}")
                except Exception as e:
                    print(f"Error sending {source_path} to {container_id}:{container_path}: {e}")
                    raise

    except docker.errors.NotFound:
        print(f"Container {container_id} not found.")
    except docker.errors.APIError as e:
        print(f"Docker API error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def copy_directories_to_container(container_id: str, comfyui_path: Path, mount_config: dict):
    """Copy specified directories from the host to the container based on the mount configuration."""
    path_mapping = {
        "custom_nodes": "custom_nodes",
        "user": "user",
        "models": "models",
        "output": "output",
        "input": "input"
    }
    installed_custom_nodes = False
    
    print(f'mount_config: {mount_config}')

    for key, action in mount_config.items():
        if action == "copy":
            dir_name = path_mapping.get(key, key)
            local_path = comfyui_path / Path(dir_name)
            container_path = (Path(CONTAINER_COMFYUI_PATH) / Path(dir_name)).as_posix()
            print(f"dirname: {dir_name}, copying {local_path} to {container_path}")

            if local_path.exists():
                print(f"Copying {local_path} to container at {container_path}")
                copy_to_container(container_id, str(local_path), str(container_path), EXCLUDE_CUSTOM_NODE_DIRS)
                if key == "custom_nodes":
                    install_custom_nodes(container_id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
                    installed_custom_nodes = True
            else:
                print(f"Local path does not exist: {local_path}")
        if action == "mount":
            if key == "custom_nodes":
                install_custom_nodes(container_id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
                installed_custom_nodes = True

    return installed_custom_nodes

def install_custom_nodes(container_id: str, blacklist: list = [], exclude_dirs: list = []):
    """Install custom nodes by executing pip install for each requirements.txt in the container."""

    container_custom_nodes_path = CONTAINER_COMFYUI_PATH + "/custom_nodes"
    container = client.containers.get(container_id)

    # Construct the find command with exclusions
    exclude_conditions = ' '.join(f"-not -name '{dir_name}'" for dir_name in exclude_dirs)
    exec_command = f"sh -c 'find {container_custom_nodes_path} -mindepth 1 -maxdepth 1 -type d {exclude_conditions}'"
    exec_id = container.exec_run(exec_command, stdout=True, stderr=True, stream=True)

    # Collect output from the stream
    output = []
    print("Listing directories in custom_nodes path:")
    for line in exec_id.output:
        decoded_line = line.decode('utf-8').strip()
        print(decoded_line)  # Print each directory name
        output.append(decoded_line)
    output = '\n'.join(output).split('\n') if output else []
    print(output)

    for custom_node in output:
        print(f"Checking {custom_node}")
        requirements_path = posixpath.join(container_custom_nodes_path, custom_node, "requirements.txt")
        
        # Check if requirements.txt exists in the custom node directory
        check_command = f"sh -c '[ -f {requirements_path} ] && echo exists || echo not_exists'"
        check_exec_id = container.exec_run(check_command, stdout=True, stderr=True)
        if check_exec_id.output.decode('utf-8').strip() == "exists":
            print(f"Found requirements.txt in {custom_node}, checking for blacklisted dependencies...")

            # Read the requirements.txt file content
            read_command = f"sh -c 'cat {requirements_path}'"
            read_exec_id = container.exec_run(read_command, stdout=True, stderr=True)
            requirements_content = read_exec_id.output.decode('utf-8').strip().split('\n')

            # Filter out blacklisted dependencies
            filtered_requirements = []
            for line in requirements_content:
                # Extract the package name using regex
                match = re.match(r'^\s*([a-zA-Z0-9\-_]+)', line)
                if match:
                    package_name = match.group(1)
                    if package_name in blacklist:
                        print(f"Skipping blacklisted dependency: {line}")
                        continue
                filtered_requirements.append(line)

            # If there are any non-blacklisted dependencies, create a temporary requirements file
            if filtered_requirements:
                temp_requirements_path = posixpath.join(container_custom_nodes_path, custom_node, "temp_requirements.txt")
                create_temp_command = f"sh -c 'echo \"{chr(10).join(filtered_requirements)}\" > {temp_requirements_path}'"
                container.exec_run(create_temp_command, stdout=True, stderr=True)

                # Run pip install for the filtered requirements
                print(f"Installing non-blacklisted dependencies for {custom_node}...")
                install_command = f"sh -c 'pip install -r {temp_requirements_path}'"
                install_exec_id = container.exec_run(install_command, stdout=True, stderr=True, stream=True)
                for line in install_exec_id.output:
                    print(line.decode('utf-8').strip())  # Print the output of the pip install command

                # Remove the temporary requirements file
                remove_temp_command = f"sh -c 'rm {temp_requirements_path}'"
                container.exec_run(remove_temp_command, stdout=True, stderr=True)
        else:
            print(f"No requirements.txt found in {custom_node}.")

def restart_container(container_id: str):
    container = client.containers.get(container_id)
    try:
        container.restart(timeout=SIGNAL_TIMEOUT)
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))

def check_comfyui_path(env: Environment):
    """Check if the ComfyUI path is valid and handle installation if needed."""
    comfyui_path = Path(env.comfyui_path)
    
    if not comfyui_path.exists():
        raise HTTPException(status_code=400, detail=f"ComfyUI path does not exist: {env.comfyui_path}.")
    
    if not comfyui_path.is_dir():
        raise HTTPException(status_code=400, detail=f"ComfyUI path is not a directory: {env.comfyui_path}.")
    
    if not comfyui_path.name.endswith("ComfyUI"):
        comfyui_dir = comfyui_path / "ComfyUI"
        if comfyui_dir.exists():
            raise HTTPException(status_code=400, detail=f"Existing ComfyUI directory found at: {comfyui_dir}.")
        
        if env.options.get("install_comfyui"):
            try:
                comfyui_dir.mkdir(parents=True, exist_ok=True)
                branch = env.options.get("comfyui_release", "master")
                repo = Repo.clone_from(f"https://github.com/comfyanonymous/ComfyUI.git", str(comfyui_dir), branch=branch)
                if not repo or repo.is_dirty():
                    raise HTTPException(status_code=400, detail=f"Failed to clone ComfyUI repository to {comfyui_dir}.")
                env.comfyui_path = str(comfyui_dir)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error during ComfyUI installation: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail="ComfyUI installation is not enabled and no valid installation found.")

def create_mounts(env: Environment):
    """Create bind mounts for the container based on the mount configuration."""
    mounts = []

    # Mapping from config keywords to actual path names
    path_mapping = {
        "custom_nodes": "custom_nodes",
        "user": "user",
        "models": "models",
        "output": "output",
        "input": "input"
    }

    # Retrieve the mount configuration from the environment options
    try:
        mount_config = json.loads(env.options.get("mount_config", "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid mount configuration. Please ensure it is valid JSON.")
    
    print(f'mount_config: {mount_config}')
    print(f'type of mount_config: {type(mount_config)}')

    comfyui_path = Path(env.comfyui_path)
    for key, action in mount_config.items():
        # Translate the config keyword to the actual path name
        dir_name = path_mapping.get(key)
        if not dir_name:
            print(f"Unknown directory key: {key}")
            dir_name = key

        # Convert dir_name to a Path object
        dir_path = comfyui_path / Path(dir_name)
        if not dir_path.exists():
            print(f"Directory does not exist: {dir_name}")
            continue

        # Only create a bind mount if the action is "mount"
        if action == "mount":
            container_path = (Path(CONTAINER_COMFYUI_PATH) / Path(dir_name)).as_posix()
            mounts.append(
                Mount(
                    target=str(container_path),
                    source=str(dir_path),
                    type='bind',
                    read_only=False,
                )
            )
        else:
            print(f"Skipping mount for {dir_name} with action: {action}")

    return mounts

def save_environment_to_db(environments, env, container_id, image):
    """Save the environment details to the database."""
    new_env = {
        "name": env.name,
        "image": image,
        "status": "created",
        "id": container_id,
        "comfyui_path": env.comfyui_path,
        "command": env.command,
        "options": env.options,
        "metadata": env.metadata,
    }
    environments.append(new_env)
    save_environments(environments)

@app.post("/environments")
def create_environment(env: Environment):
    """Create a new Docker container and save to local database."""
    environments = load_environments()
    
    try:
        # Validate name only [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed
        if not re.match(r'[a-zA-Z0-9][a-zA-Z0-9_.-]', env.name):
            raise HTTPException(status_code=400, detail="Environment name contains invalid characters. Only alphanumeric characters, dots, underscores, and hyphens are allowed. Minimum length is 2 characters.")

        # Check if name is longer than 128 characters
        if len(env.name) > 128:
            raise HTTPException(status_code=400, detail="Environment name is too long. Maximum length is 128 characters.")

        # Check if name already exists
        if any(e["name"] == env.name for e in environments):
            raise HTTPException(status_code=400, detail="Environment name already exists.")
        
        check_comfyui_path(env)
        mounts = create_mounts(env)
        
        port = env.options.get("port", COMFYUI_PORT)
        combined_cmd = " --port " + str(port) + " " + env.command
        
        container = client.containers.create(
            image=env.image,
            name=env.name,
            command=combined_cmd,
            runtime="nvidia",
            device_requests=[
                DeviceRequest(count=-1, capabilities=[["gpu"]])
            ],
            ports={f"{port}": port},
            mounts=mounts,
        )
        
        if not container:
            raise HTTPException(status_code=500, detail="Failed to create Docker container.")
        
        env.metadata = {
            "base_image": env.image,
            "port": port,
        }

        save_environment_to_db(environments, env, container.id, env.image)
        return {"status": "success", "container_id": container.id}

    except HTTPException:
        # Re-raise HTTPExceptions to ensure they are not caught by the generic exception handler
        raise
    except docker.errors.APIError as e:
        print(f"An API error occurred: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except docker.errors.ImageNotFound:
        print("Image not found. Please check the image name and try again.")
        raise HTTPException(status_code=404, detail="Image not found. Please check the image name and try again.")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/environments/{id}/duplicate")
def duplicate_environment(id: str, env: Environment):
    """Duplicate a container by committing its state to an image and running a new container."""
    
    image_repo = "comfy-environment-clone"
    temp_tag = image_repo + ":temp"
    latest_tag = image_repo + ":latest"
    
    environments = load_environments()

    try:
        # Validate name only [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed
        if not re.match(r'[a-zA-Z0-9][a-zA-Z0-9_.-]', env.name):
            raise HTTPException(status_code=400, detail="Environment name contains invalid characters. Only alphanumeric characters, dots, underscores, and hyphens are allowed. Minimum length is 2 characters.")

        # Check if name is longer than 128 characters
        if len(env.name) > 128:
            raise HTTPException(status_code=400, detail="Environment name is too long. Maximum length is 128 characters.")
        
        # Check if name already exists
        if any(e["name"] == env.name for e in environments):
            print(f"Environment name already exists: {env.name}")
            raise HTTPException(status_code=400, detail="Environment name already exists.")
        
        prev_env = next((e for e in environments if e["id"] == id), None)
        if prev_env is None:
            print(f"Environment not found: {id}")
            raise HTTPException(status_code=404, detail="Environment not found.")
        
        if prev_env.get("status") == "created":
            print(f"Environment can only be duplicated after it has been activated at least once. Please activate the environment first.")
            raise HTTPException(status_code=400, detail="An environment can only be duplicated after it has been activated at least once. Please activate the environment first.")
        
        new_container_name = env.name

        container = client.containers.get(id)

        try:
            image = client.images.get(latest_tag)
            image.tag(temp_tag)
            print(f"Existing latest image tagged as '{temp_tag}'.")
        except docker.errors.ImageNotFound:
            print("No previous latest image found. Proceeding without backup.")

        new_image = container.commit(repository=image_repo, tag="latest")
        print(f"New image created: {new_image.id}")

        try:
            client.images.remove(temp_tag, force=True)
            print(f"Temporary backup image '{temp_tag}' removed.")
        except docker.errors.ImageNotFound:
            print("No temporary backup image to remove.")

        mounts = create_mounts(env)
        port = env.options.get("port", COMFYUI_PORT)
        combined_cmd = " --port " + str(port) + " " + env.command

        new_container = client.containers.create(
            image=latest_tag,
            name=new_container_name,
            command=combined_cmd,
            runtime="nvidia",
            device_requests=[
                DeviceRequest(count=-1, capabilities=[["gpu"]])
            ],
            ports={f"{port}": port},
            mounts=mounts,
        )
        print(f"New container '{new_container_name}' with id '{new_container.id}' created from the image.")
        
        env.metadata = prev_env.get("metadata", {})
        env.metadata["port"] = port

        save_environment_to_db(environments, env, new_container.id, latest_tag)
        return {"status": "success", "container_id": new_container.id}

    except HTTPException:
        # Re-raise HTTPExceptions to ensure they are not caught by the generic exception handler
        raise
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except docker.errors.APIError as e:
        print(f"An error occurred: {e}")
        try:
            print("Restoring from backup...")
            client.images.remove(latest_tag, force=True)
            client.images.get(temp_tag).tag(latest_tag)
            client.images.remove(temp_tag, force=True)
            print(f"Restored 'comfy-environment-clone:latest' from backup.")
        except docker.errors.ImageNotFound:
            print("No backup available to restore.")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/environments")
def list_environments():
    """List environments from the local database."""
    environments = load_environments()
    return environments


@app.delete("/environments/{id}")
def delete_environment(id: str):
    """Stop and remove a Docker container and update local database."""
    environments = load_environments()

    # Find the environment
    env = next((e for e in environments if e["id"] == id), None)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found.")

    try:
        # Stop and remove the Docker container
        container = client.containers.get(env["id"])
        container.stop(timeout=SIGNAL_TIMEOUT)
        container.remove()

        # Update the database
        environments = [e for e in environments if e["id"] != id]
        save_environments(environments)
        return {"status": "success", "id": id}
    except docker.errors.NotFound:
        # If container is not found, just update the database
        environments = [e for e in environments if e["id"] != id]
        save_environments(environments)
        return {"status": "success (container not found)", "id": id}
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/environments/{name}/status")
def get_environment_status(name: str):
    """Get the status of a Docker container."""
    environments = load_environments()
    env = next((e for e in environments if e["name"] == name), None)
    return {"status": env["status"]}


@app.post("/environments/{id}/activate")
def activate_environment(id: str, options: dict = {}):
    print(options)
    """Activate a Docker container."""
    environments = load_environments()
    env = next((e for e in environments if e["id"] == id), None)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    # Load env into Environment object
    env = Environment(**env)
    container = client.containers.get(env.id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found.")
    
    # Stop all other running containers if they exist:
    if STOP_OTHER_RUNNING_CONTAINERS:
        for e in environments:
            if e["id"] != id and e["status"] == "running":
                try:
                    temp_container = client.containers.get(e["id"])
                    temp_container.stop(timeout=SIGNAL_TIMEOUT)
                except docker.errors.NotFound:
                    pass
                except docker.errors.APIError as e:
                    raise HTTPException(status_code=400, detail=str(e))
            
    print(f"stopping other running containers: {STOP_OTHER_RUNNING_CONTAINERS}")
    print(container.status)
    if not container.status == "running":
        try:
            container.start()
        except docker.errors.APIError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    comfyui_path = Path(env.comfyui_path)
    
    # Check mount_config for directories to copy
    try:
        mount_config = json.loads(env.options.get("mount_config", "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid mount configuration. Please ensure it is valid JSON.")

    if env.status == "created":
        installed_custom_nodes = copy_directories_to_container(id, comfyui_path, mount_config)
        if installed_custom_nodes:
            restart_container(id)

    env.status = "running"
    save_environments(environments)
    return {"status": "success", "container_id": id}


@app.post("/environments/{id}/deactivate")
def deactivate_environment(id: str):
    """Deactivate a Docker container."""
    environments = load_environments()
    env = next((e for e in environments if e["id"] == id), None)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    container = client.containers.get(env["id"])
    if not container:
        raise HTTPException(status_code=404, detail="Container not found.")
    if container.status == "stopped" or container.status == "exited" or container.status == "created" or container.status == "dead":
        return {"status": "success", "container_id": id}
    try:
        container.stop(timeout=SIGNAL_TIMEOUT)
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))

    env["status"] = "stopped"
    save_environments(environments)
    return {"status": "success", "container_id": id}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5172)
