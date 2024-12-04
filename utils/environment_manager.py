from pydantic import BaseModel
from fastapi import HTTPException
import json
import os
from pathlib import Path
import docker
import re

from .docker_utils import get_container

DB_FILE = "environments.json"

# Pydantic model for environment creation
class Environment(BaseModel):
    name: str
    image: str
    id: str = ""
    status: str = ""
    command: str = ""
    comfyui_path: str = ""
    duplicate: bool = False
    options: dict = {}
    metadata: dict = {}

class EnvironmentUpdate(BaseModel):
    name: str = None
    
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
            container = get_container(env["id"])
        except docker.errors.NotFound:
            env["status"] = "dead"
        except Exception as e:
            return HTTPException(status_code=500, detail=str(e))
        else:
            env["status"] = container.status
            
    # save the updated statuses
    save_environments(environments)
    
    return environments
  
def save_environment_to_db(environments, env, container_id, image, is_duplicate: bool = False):
    """Save the environment details to the database."""
    new_env = {
        "name": env.name,
        "image": image,
        "status": "created",
        "id": container_id,
        "comfyui_path": env.comfyui_path,
        "command": env.command,
        "duplicate": is_duplicate,
        "options": env.options,
        "metadata": env.metadata,
    }
    environments.append(new_env)
    save_environments(environments)
    
def check_environment_name(environments, env):
    # Validate name only [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed
    if not re.match(r'[a-zA-Z0-9][a-zA-Z0-9_.-]', env.name):
        raise HTTPException(status_code=400, detail="Environment name contains invalid characters. Only alphanumeric characters, dots, underscores, and hyphens are allowed. Minimum length is 2 characters.")

    # Check if name is longer than 128 characters
    if len(env.name) > 128:
        raise HTTPException(status_code=400, detail="Environment name is too long. Maximum length is 128 characters.")

    # Check if name already exists
    if any(e["name"] == env.name for e in environments):
        raise HTTPException(status_code=400, detail="Environment name already exists.")