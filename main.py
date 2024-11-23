import tarfile
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

app = FastAPI()

# Constants
CONTAINER_COMFYUI_PATH = "/app/ComfyUI"
SIGNAL_TIMEOUT = 2
BLACKLIST_REQUIREMENTS = ['torch']
EXCLUDE_CUSTOM_NODE_DIRS = ['__pycache__', 'ComfyUI-Manager']
INCLUDE_USER_COMFYUI_DIRS = ['models', 'styles', 'input', 'output', 'user']
COMFYUI_PORT = 8188
DB_FILE = "environments.json"
STOP_OTHER_RUNNING_CONTAINERS = True

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
    if os.path.exists(DB_FILE):
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


def copy_to_container(container_id: str, source_path: str, container_path: str, exclude_dirs: list = []):
    container = client.containers.get(container_id)

    # Create a tar archive of the source directory or file
    with tarfile.open("archive.tar", mode="w") as archive:
        # Add each file in the source directory to the archive
        for root, dirs, files in os.walk(source_path):
            # Modify dirs in-place to exclude specified directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                full_path = os.path.join(root, file)
                # Calculate the relative path to maintain the directory structure
                relative_path = os.path.relpath(full_path, start=source_path)
                archive.add(full_path, arcname=relative_path)

    # Send the tar archive to the container
    with open("archive.tar", "rb") as tar_data:
        container.put_archive(container_path, tar_data)

    # Clean up the tar archive
    os.remove("archive.tar")
    print(f"Copied {source_path} to {container_id}:{container_path}")


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
    if not os.path.exists(env.comfyui_path):
        raise HTTPException(status_code=400, detail=f"ComfyUI path does not exist: {env.comfyui_path}.")
    
    if not os.path.isdir(env.comfyui_path):
        raise HTTPException(status_code=400, detail=f"ComfyUI path is not a directory: {env.comfyui_path}.")
    
    if not env.comfyui_path.endswith("ComfyUI"):
        comfyui_dir = os.path.join(env.comfyui_path, "ComfyUI")
        if os.path.exists(comfyui_dir):
            raise HTTPException(status_code=400, detail=f"Existing ComfyUI directory found at: {comfyui_dir}.")
        
        if env.options.get("install_comfyui"):
            try:
                os.makedirs(comfyui_dir, exist_ok=True)
                branch = env.options.get("comfyui_release", "master")
                repo = Repo.clone_from(f"https://github.com/comfyanonymous/ComfyUI.git", comfyui_dir, branch=branch)
                if not repo or repo.is_dirty():
                    raise HTTPException(status_code=400, detail=f"Failed to clone ComfyUI repository to {comfyui_dir}.")
                env.comfyui_path = comfyui_dir
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error during ComfyUI installation: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail="ComfyUI installation is not enabled and no valid installation found.")

def create_mounts(env: Environment):
    """Create bind mounts for the container."""
    mounts = []
    all_dirs_to_include = INCLUDE_USER_COMFYUI_DIRS + env.options.get("mount_additional_dirs", [])
    
    for dir_name in all_dirs_to_include:
        if not os.path.exists(os.path.join(env.comfyui_path, dir_name)):
            print(f"Directory does not exist: {dir_name}")
            all_dirs_to_include.remove(dir_name)

    for dir_name in all_dirs_to_include:
        local_path = os.path.join(env.comfyui_path, dir_name)
        container_path = posixpath.join(CONTAINER_COMFYUI_PATH, dir_name)
        mounts.append(
            Mount(
                target=container_path,
                source=local_path,
                type='bind',
                read_only=False,
            )
        )
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

    if any(e["name"] == env.name for e in environments):
        raise HTTPException(status_code=400, detail="Environment name already exists.")
    
    check_comfyui_path(env)
    mounts = create_mounts(env)
    combined_cmd = " --port " + str(COMFYUI_PORT) + " " + env.command
    
    try:
        container = client.containers.create(
            image=env.image,
            name=env.name,
            command=combined_cmd,
            runtime="nvidia",
            device_requests=[
                DeviceRequest(count=-1, capabilities=[["gpu"]])
            ],
            ports={f"{COMFYUI_PORT}": COMFYUI_PORT},
            mounts=mounts,
        )
        
        if not container:
            raise HTTPException(status_code=500, detail="Failed to create Docker container.")
        
        env.metadata = {
            "comfyui_version": env.options.get("comfyui_release", "master"),
            "base_image": env.image,
        }

        save_environment_to_db(environments, env, container.id, env.image)
        return {"status": "success", "container_id": container.id}
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=400, detail="Image not found. Please check the image name and try again.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/environments/{id}/duplicate")
def duplicate_environment(id: str, env: Environment):
    """Duplicate a container by committing its state to an image and running a new container."""
    
    image_repo = "comfy-environment-clone"
    temp_tag = image_repo + ":temp"
    latest_tag = image_repo + ":latest"
    
    environments = load_environments()

    if any(e["name"] == env.name for e in environments):
        raise HTTPException(status_code=400, detail="Environment name already exists.")
    
    prev_env = next((e for e in environments if e["id"] == id), None)
    if prev_env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    
    if prev_env.get("status") == "created":
        raise HTTPException(status_code=400, detail="An environment can only be duplicated after it has been activated at least once. Please activate the environment first.")
    
    new_container_name = env.name

    try:
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
        combined_cmd = " --port " + str(COMFYUI_PORT) + " " + env.command

        new_container = client.containers.create(
            image=latest_tag,
            name=new_container_name,
            command=combined_cmd,
            runtime="nvidia",
            device_requests=[
                DeviceRequest(count=-1, capabilities=[["gpu"]])
            ],
            ports={f"{COMFYUI_PORT}": COMFYUI_PORT},
            mounts=mounts,
        )
        print(f"New container '{new_container_name}' with id '{new_container.id}' created from the image.")
        
        env.metadata = prev_env.get("metadata", {})

        save_environment_to_db(environments, env, new_container.id, latest_tag)
        return {"status": "success", "container_id": new_container.id}

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
    
    local_custom_nodes_path = os.path.join(env.comfyui_path, "custom_nodes")
    print(local_custom_nodes_path)
    container_custom_nodes_path = CONTAINER_COMFYUI_PATH + "/custom_nodes"
    print(container_custom_nodes_path)
    if env.status == "created" and env.options.get("copy_custom_nodes"):
        print("copying and installing custom nodes")
        copy_to_container(id, local_custom_nodes_path, container_custom_nodes_path, EXCLUDE_CUSTOM_NODE_DIRS)
        install_custom_nodes(id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
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
