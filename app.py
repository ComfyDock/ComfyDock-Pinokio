import json
import time
import uuid
from fastapi import FastAPI, HTTPException, Query
import docker
from docker.types import DeviceRequest
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import StreamingResponse
import argparse
import requests
import os

from utils.comfyui_utils import check_comfyui_path, try_install_comfyui
from utils.docker_utils import copy_directories_to_container, create_container, create_mounts, get_container, get_image, pull_image_api, remove_image, restart_container, try_pull_image
from utils.environment_manager import Environment, EnvironmentUpdate, check_environment_name, hard_delete_environment, load_environments, prune_deleted_environments, save_environment_to_db, save_environments
from utils.user_settings_manager import Folder, UserSettings, load_user_settings, update_user_settings
from utils.utils import generate_id

# Constants
FRONTEND_ORIGIN = "http://localhost:8000"
FRONTEND_ORIGIN_2 = "http://127.0.0.1:8000"
SIGNAL_TIMEOUT = 2
COMFYUI_PORT = 8188
DEFAULT_COMFYUI_PATH = os.getcwd()
DELETED_FOLDER_ID = "deleted"

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Run the FastAPI app with optional ComfyUI path.")
parser.add_argument("--allow_running_multiple_containers", type=str, help="Allow running multiple containers", default="False")
args = parser.parse_args()

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, FRONTEND_ORIGIN_2],  # Frontend's origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Routes
@app.post("/environments")
def create_environment(env: Environment):
    """Create a new Docker container and save to local database."""
    environments = load_environments()
    
    try:
        # Check environment name is valid
        check_environment_name(environments, env)
        
        # Check ComfyUI path is valid
        valid_comfyui_path = check_comfyui_path(env.comfyui_path)
        
        # Check if the image is available locally, if not, pull it from Docker Hub
        try_pull_image(env.image)
        
        # Create mounts
        mounts = create_mounts(env.name, env.options.get("mount_config", {}), valid_comfyui_path)
        print(f"Mounts: {mounts}")
        
        # Get port and command
        port = env.options.get("port", COMFYUI_PORT)
        combined_cmd = " --port " + str(port) + " " + env.command
        
        # Get runtime and device requests
        runtime = "nvidia" if env.options.get("runtime", "") == "nvidia" else None
        device_requests = [DeviceRequest(count=-1, capabilities=[["gpu"]])] if runtime else None
        
        # Create unique container name
        container_name = f"comfy-env-{generate_id()}"
        env.container_name = container_name

        # Create container
        container = create_container(
            image=env.image,
            name=container_name,
            command=combined_cmd,
            # runtime=runtime,
            device_requests=device_requests,
            ports={f"{port}": port},
            mounts=mounts,
        )
        
        env.metadata = {
            "base_image": env.image,
            "created_at": time.time(),
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
    environments = load_environments()

    try:
        # Check environment name is valid
        check_environment_name(environments, env)
        
        # Check if environment exists
        prev_env = next((e for e in environments if e["id"] == id), None)
        if prev_env is None:
            print(f"Environment not found: {id}")
            raise HTTPException(status_code=404, detail="Environment not found.")
        
        # Check if environment has been activated at least once
        if prev_env.get("status") == "created":
            print(f"Environment can only be duplicated after it has been activated at least once. Please activate the environment first.")
            raise HTTPException(status_code=400, detail="An environment can only be duplicated after it has been activated at least once. Please activate the environment first.")
        
        # Check comfyui path is valid
        check_comfyui_path(prev_env.get("comfyui_path"))
        
        # Create mounts
        mounts = create_mounts(env.name, env.options.get("mount_config", {}), Path(env.comfyui_path))
        print(f"Mounts: {mounts}")
        
        # Get port and command
        port = env.options.get("port", COMFYUI_PORT)
        combined_cmd = " --port " + str(port) + " " + env.command
        
        # Get runtime and device requests
        runtime = "nvidia" if env.options.get("runtime", "") == "nvidia" else None
        device_requests = [DeviceRequest(count=-1, capabilities=[["gpu"]])] if runtime else None
        
        # Create unique container name
        container_name = f"comfy-env-{generate_id()}"
        env.container_name = container_name

        # Get existing container and create a unique image
        container = get_container(id)
        image_repo = "comfy-env-clone"
        unique_image = f"{image_repo}:{container_name}"
        
        # Create unique image
        try:
            new_image = container.commit(repository=image_repo, tag=container_name)
            print(f"New image created with tag '{unique_image}': {new_image.id}")
        except docker.errors.APIError as e:
            print(f"An error occurred: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        # Create new container
        new_container = create_container(
            image=unique_image,
            name=container_name,
            command=combined_cmd,
            # runtime=runtime,
            device_requests=device_requests,
            ports={f"{port}": port},
            mounts=mounts,
        )
        print(f"New container '{container_name}' with id '{new_container.id}' created from the image.")
        
        env.metadata = prev_env.get("metadata", {})
        env.metadata["created_at"] = time.time()

        save_environment_to_db(environments, env, new_container.id, unique_image, is_duplicate=True)
        return {"status": "success", "container_id": new_container.id}

    except HTTPException:
        # Re-raise HTTPExceptions to ensure they are not caught by the generic exception handler
        raise
    except docker.errors.ImageNotFound:
        print("Image not found. Please check the image name and try again.")
        raise HTTPException(status_code=404, detail="Image not found. Please check the image name and try again.")
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except docker.errors.APIError as e:
        print(f"An error occurred: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/environments")
def list_environments(folderId: str = Query(None, description="The ID of the folder to filter environments")):
    """List environments from the local database."""
    print(folderId)
    if folderId:
        environments = load_environments(folder_id=folderId)
    else:
        environments = load_environments()
    return environments


@app.delete("/environments/{id}")
def delete_environment(id: str):
    """Soft delete or hard delete a Docker environment.

    Steps:
    1. If the environment is not in the deleted folder:
       - Add it to the deleted folder
       - Set deleted_at timestamp in metadata
       - Do not remove container or environment from DB permanently
       - Prune older deleted environments if needed

    2. If the environment is already in the deleted folder:
       - Stop and remove container
       - Remove environment from DB
    """
    environments = load_environments()

    # Find the environment
    env = next((e for e in environments if e["id"] == id), None)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found.")

    # Load user settings for max_deleted_environments
    user_settings = load_user_settings(DEFAULT_COMFYUI_PATH)
    max_deleted = user_settings.max_deleted_environments

    # Check if environment is already in the "deleted" folder
    if DELETED_FOLDER_ID in env.get("folderIds", []):
        # Hard delete environment, throws HTTPException if error, modifies environments in place
        hard_delete_environment(env, environments, timeout=SIGNAL_TIMEOUT)
        save_environments(environments)
        return {"status": "success (permanently deleted)", "id": id}
    else:
        # Environment is not in the deleted folder, so we soft-delete it
        # Add the "deleted" folder to its folderIds
        # folder_ids = env.get("folderIds", [])
        # if DELETED_FOLDER_ID not in folder_ids:
        #     folder_ids.append(DELETED_FOLDER_ID)
        env["folderIds"] = [DELETED_FOLDER_ID,]

        # Set deleted_at timestamp in metadata
        if "metadata" not in env:
            env["metadata"] = {}
        env["metadata"]["deleted_at"] = time.time()

        # Update the environment in the database
        # Since we modify env in place, we just save all
        save_environments(environments)

        # Now prune deleted environments if we exceed max limit
        prune_deleted_environments(environments, max_deleted)

        return {"status": "success (moved to deleted folder)", "id": id}


@app.get("/environments/{name}/status")
def get_environment_status(name: str):
    """Get the status of a Docker container."""
    environments = load_environments()
    env = next((e for e in environments if e["name"] == name), None)
    return {"status": env["status"]}

@app.put("/environments/{id}")
def update_environment(id: str, env: EnvironmentUpdate):
    """Update an environment in the local database."""
    environments = load_environments()
    
    # Get existing environment
    existing_env = next((e for e in environments if e["id"] == id), None)
    if existing_env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    
    # Update folderIds
    if env.folderIds is not None:
        existing_env["folderIds"] = env.folderIds
    
    # Update the environment name
    if env.name is not None:
        # Check if the new name already exists
        # if any(e["name"] == env.name and e["id"] != id for e in environments):
        #     raise HTTPException(status_code=400, detail="Environment name already exists.")
        
        if existing_env.get("container_name") is None:
            existing_env["container_name"] = existing_env["name"]
            
        existing_env["name"] = env.name
        
    
    save_environments(environments)
    return {"status": "success", "container_id": id}


@app.post("/environments/{id}/activate")
def activate_environment(id: str, options: dict = {}):
    print(options)
    """Activate a Docker container."""
    environments = load_environments()
    
    try:
        # Get environment
        env = next((e for e in environments if e["id"] == id), None)
        if env is None:
            raise HTTPException(status_code=404, detail="Environment not found.")
        
        # Load env into Environment object
        env = Environment(**env)
        
        # Get container
        container = get_container(env.id)
        
        # Stop all other running containers if they exist:
        print(args.allow_running_multiple_containers)
        if args.allow_running_multiple_containers != "True":
            for e in environments:
                if e["id"] != id and e["status"] == "running":
                    try:
                        temp_container = get_container(e["id"])
                        temp_container.stop(timeout=SIGNAL_TIMEOUT)
                    except docker.errors.NotFound:
                        pass
                    except docker.errors.APIError as e:
                        raise HTTPException(status_code=400, detail=str(e))
                
        # Start container if it is not running
        if not container.status == "running":
            container.start()
        
        # Get comfyui path
        comfyui_path = Path(env.comfyui_path)
        
        # Check mount_config for directories to copy
        mount_config = env.options.get("mount_config", "{}")

        if env.status == "created":
            installed_custom_nodes = copy_directories_to_container(id, comfyui_path, mount_config)
            if installed_custom_nodes:
                restart_container(id)

        env.status = "running"
        save_environments(environments)
        return {"status": "success", "container_id": id}
    except HTTPException:
        # Re-raise HTTPExceptions to ensure they are not caught by the generic exception handler
        raise
    except docker.errors.APIError as e:
        print(f"An API error occurred: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/environments/{id}/deactivate")
def deactivate_environment(id: str):
    """Deactivate a Docker container."""
    environments = load_environments()
    try:
        # Get environment
        env = next((e for e in environments if e["id"] == id), None)
        if env is None:
            raise HTTPException(status_code=404, detail="Environment not found.")
        
        # Get container
        container = get_container(env["id"])

        # Return success if container is not running
        if container.status == "stopped" or container.status == "exited" or container.status == "created" or container.status == "dead":
            return {"status": "success", "container_id": id}

        # Stop container
        container.stop(timeout=SIGNAL_TIMEOUT)

        # Update environment status
        env["status"] = "stopped"
        save_environments(environments)
        return {"status": "success", "container_id": id}
    except HTTPException:
        raise
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user-settings")
def get_user_settings():
    """Get user settings."""
    default_comfyui_path = DEFAULT_COMFYUI_PATH
    print(default_comfyui_path)
    return load_user_settings(default_comfyui_path)

@app.put("/user-settings")
def update_user(settings: UserSettings):
    """Update user settings."""
    print(settings)
    update_user_settings(settings.model_dump())
    return {"status": "success"}

@app.post("/folders")
def create_folder(folder_data: dict):
    # folder_data = {"name": "New Folder Name"}
    folder_id = str(uuid.uuid4())
    settings = load_user_settings(DEFAULT_COMFYUI_PATH)
    settings = settings.model_dump()
    if "folders" not in settings:
        settings["folders"] = []
        
    # Check folder name is not longer than 128 characters
    if len(folder_data["name"]) > 128:
        raise HTTPException(status_code=400, detail="Folder name is too long. Maximum length is 128 characters.")

    # Ensure we don't add duplicates of default folders
    if folder_data["name"] in [f["name"] for f in settings["folders"]]:
        raise HTTPException(status_code=400, detail="Folder name already exists.")
    
    # Convert user input to Folder object
    folder = Folder(id=folder_id, name=folder_data["name"])
    
    settings["folders"].append(folder)
    update_user_settings(settings)
    return {"id": folder_id, "name": folder_data["name"]}

@app.put("/folders/{folder_id}")
def update_folder(folder_id: str, folder_data: dict):
    # folder_data = { "name": "New Folder Name" }
    # Convert user input to Folder object
    folder = Folder(id=folder_id, name=folder_data["name"])
    settings = load_user_settings(DEFAULT_COMFYUI_PATH)
    settings = settings.model_dump()
    folders = settings.get("folders", [])
    for f in folders:
        if f["id"] == folder_id:
            f["name"] = folder.name
            update_user_settings(settings)
            return {"id": folder_id, "name": folder.name}
    raise HTTPException(status_code=404, detail="Folder not found")

@app.delete("/folders/{folder_id}")
def delete_folder(folder_id: str):
    # Check if any environment uses this folder_id
    environments = load_environments()
    for env in environments:
        if folder_id in env.get("folderIds", []):
            raise HTTPException(status_code=400, detail="Cannot delete folder - it contains environments.")

    settings = load_user_settings(DEFAULT_COMFYUI_PATH)
    settings = settings.model_dump()
    folders = settings.get("folders", [])
    for i, f in enumerate(folders):
        if f["id"] == folder_id:
            del folders[i]
            settings["folders"] = folders
            update_user_settings(settings)
            return {"status": "deleted"}

    raise HTTPException(status_code=404, detail="Folder not found")

@app.get("/images/tags")
def get_image_tags():
    """Get all available image tags from Docker Hub."""
    try:
        response = requests.get(
            "https://hub.docker.com/v2/namespaces/akatzai/repositories/comfyui-env/tags?page_size=100"
        )
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        tags = [tag['name'] for tag in data.get('results', [])]
        return {"tags": tags}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching tags from Docker Hub: {e}")
        raise HTTPException(status_code=500, detail="Error fetching tags from Docker Hub")

@app.get("/images/exists")
def check_image(image: str = Query(..., description="The name of the Docker image to check")):
    print(image)
    try:
        get_image(image)
        return {"status": "found"}
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=404, detail="Image not found locally. Ready to pull.")

@app.get("/images/pull")
def pull_image(image: str = Query(..., description="The name of the Docker image to pull")):
    def image_pull_stream():
        layers = {}
        total_download_size = 0
        total_downloaded = 0
        completed_layers = set()
        already_exist_layers = set()

        try:
            # Start pulling the image
            for line in pull_image_api(image):
                # Send raw line for debugging (optional)
                # yield f"data: {json.dumps(line)}\n\n"

                status = line.get('status')
                layer_id = line.get('id')
                progress_detail = line.get('progressDetail', {})

                if layer_id:
                    if status == "Pull complete":
                        completed_layers.add(layer_id)
                    elif status == "Already exists":
                        already_exist_layers.add(layer_id)
                    elif 'current' in progress_detail and 'total' in progress_detail:
                        current = progress_detail.get('current', 0)
                        total = progress_detail.get('total', 0)

                        if total > 0:
                            if layer_id not in layers:
                                layers[layer_id] = {'current': current, 'total': total}
                                total_download_size += total
                                total_downloaded += current
                            else:
                                total_downloaded -= layers[layer_id]['current']
                                layers[layer_id]['current'] = current
                                total_downloaded += current

                        # Compute overall progress
                        if total_download_size > 0:
                            overall_progress = (total_downloaded / total_download_size) * 100
                        else:
                            overall_progress = 0

                        # Send progress update
                        yield f"data: {json.dumps({'progress': overall_progress})}\n\n"

            # When done, send completion status
            yield f"data: {json.dumps({'progress': 100, 'status': 'completed'})}\n\n"

        except docker.errors.APIError as e:
            error_message = f"Error pulling image {image}: {e}"
            yield f"data: {json.dumps({'error': error_message})}\n\n"

    return StreamingResponse(image_pull_stream(), media_type="text/event-stream")

@app.post("/valid-comfyui-path")
def get_valid_comfyui_path(obj: dict):
    """Get the valid ComfyUI path."""
    valid_comfyui_path = check_comfyui_path(obj["path"])
    return {"valid_comfyui_path": str(valid_comfyui_path)}

@app.post("/install-comfyui")
def install_comfyui(obj: dict):
    """Install ComfyUI at given path."""
    print(obj)
    try_install_comfyui(obj["path"], obj["branch"])
    return {"status": "success"}

@app.get("/environments/{id}/logs")
def stream_container_logs(id: str):
    """Stream logs from a running Docker container."""
    try:
        container = get_container(id)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if container.status != "running":
        raise HTTPException(status_code=400, detail="Container is not running.")

    def log_generator():
        for log in container.logs(stream=True):
            decoded_log = log.decode('utf-8')
            yield f"data: {decoded_log}\n\n"

    return StreamingResponse(log_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5172)
