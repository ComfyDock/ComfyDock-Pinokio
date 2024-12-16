from pydantic import BaseModel
from fastapi import HTTPException
import json
import os
from pathlib import Path
import docker
import re
from filelock import FileLock, Timeout

from .docker_utils import get_container, remove_image

DB_FILE = "environments.json"
LOCK_FILE = f"{DB_FILE}.lock"

# Pydantic model for environment creation
class Environment(BaseModel):
    name: str
    image: str
    container_name: str = ""
    id: str = ""
    status: str = ""
    command: str = ""
    comfyui_path: str = ""
    duplicate: bool = False
    options: dict = {}
    metadata: dict = {}
    folderIds: list[str] = []

class EnvironmentUpdate(BaseModel):
    name: str = None
    folderIds: list[str] = []
    
def save_environments(data):
    lock = FileLock(LOCK_FILE, timeout=10)
    try:
        with lock:
            with open(DB_FILE, "w") as f:
                json.dump(data, f, indent=4)
    except Timeout:
        raise HTTPException(status_code=500, detail="Could not acquire file lock for saving environments.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while saving environments: {str(e)}")

# Helper function to load and save JSON data
def load_environments(folder_id: str = None):
    environments = []
    lock = FileLock(LOCK_FILE, timeout=10)
    try:
        with lock:
            if Path(DB_FILE).exists():
                with open(DB_FILE, "r") as f:
                    environments = json.load(f)
    except Timeout:
        raise HTTPException(status_code=500, detail="Could not acquire file lock for loading environments.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error decoding JSON from environments file.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while loading environments: {str(e)}")

    # Query the database for the status of each container and ensure they match the status in the database
    for env in environments:
        try:
            container = get_container(env["id"])
        except docker.errors.NotFound:
            env["status"] = "dead"
        except Exception as e:
            return HTTPException(status_code=500, detail=str(e))
        else:
            env["status"] = container.status

    # save the updated statuses
    save_environments(environments)
    
    # Filter environments by folder_id if provided
    if folder_id and folder_id != 'all':
        environments = [env for env in environments if folder_id in env.get("folderIds", [])]
    elif folder_id == 'all':
        environments = [env for env in environments if 'deleted' not in env.get("folderIds", [])]

    return environments

def save_environment_to_db(environments, env, container_id, image, is_duplicate: bool = False):
    """Save the environment details to the database."""
    # Convert the Environment instance to a dictionary
    env_dict = env.dict()

    # Update the dictionary with special fields
    env_dict.update({
        "image": image,
        "id": container_id,
        "duplicate": is_duplicate,
        "status": "created"
    })

    # Append the updated environment to the list
    environments.append(env_dict)
    save_environments(environments)
    
def check_environment_name(environments, env):
    # Validate name only [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed
    # if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9 ._/-]*$', env.name):
    #     raise HTTPException(status_code=400, detail="Environment name contains invalid characters. Only alphanumeric characters, spaces, hyphens, dashes, periods, and slashes are allowed. Minimum length is 2 characters.")

    # Check if name is longer than 128 characters
    if len(env.name) > 128:
        raise HTTPException(status_code=400, detail="Environment name is too long. Maximum length is 128 characters.")

    # Check if name already exists
    # if any(e["name"] == env.name for e in environments):
    #     raise HTTPException(status_code=400, detail="Environment name already exists.")
    
def prune_deleted_environments(environments: list, max_deleted: int):
    # Filter environments that have the 'deleted' folder
    deleted_envs = [env for env in environments if "deleted" in env.get("folderIds", [])]
    
    if len(deleted_envs) <= max_deleted:
        # No pruning needed
        return

    # Sort by deleted_at ascending (older first)
    # If deleted_at might not exist, assume 0 or sort them last
    deleted_envs.sort(key=lambda e: e.get("metadata", {}).get("deleted_at", 0))

    # Calculate how many to remove
    to_remove_count = len(deleted_envs) - max_deleted

    # Remove the oldest ones
    for i in range(to_remove_count):
        env_to_remove = deleted_envs[i]
        # Hard delete: stop container, remove container, and remove from DB
        try:
            hard_delete_environment(env_to_remove, environments)
        except HTTPException as e:
            print(f"Error hard deleting environment: {str(e)}, continuing...")

    # After removal, save updates
    save_environments(environments)

def hard_delete_environment(env: dict, environments: list, timeout: int = 0):
    """Actually remove the environment and its container."""
    try:
        container = get_container(env["id"])
        container.stop(timeout=timeout)
        container.remove()
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError as e:
        # If there's an API error here, you might want to log it.
        # Usually, you'd want to handle errors gracefully, but since
        # this is pruning, you might raise or just print an error message.
        print(f"API error removing container {env['id']}: {e}")

    # If the environment is a duplicate, remove backing image
    if env.get("duplicate", False):
        try:
            remove_image(env["image"], force=True)
            print(f"Backing image '{env['image']}' removed.")
        except docker.errors.ImageNotFound:
            print(f"Backing image '{env['image']}' not found.")
        except docker.errors.APIError as e:
            print(f"Error removing image '{env['image']}': {e}")
            raise HTTPException(status_code=400, detail=f"Error removing image: {str(e)}")

    # Remove from environments list
    environments.remove(env)