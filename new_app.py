import asyncio
from contextlib import asynccontextmanager
import json
import time
import uuid
import os
from pathlib import Path
from datetime import datetime

import requests
import uvicorn
import docker
from dateutil import parser as dateutil_parser

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi import WebSocket, WebSocketDisconnect

# --- Import new core library modules ---
from comfydock_core.environment import Environment, EnvironmentUpdate, EnvironmentManager
from comfydock_core.user_settings import UserSettings, UserSettingsManager
from comfydock_core.comfyui_integration import check_comfyui_path, try_install_comfyui
from utils.connection_manager import ConnectionManager

# --- Constants ---
COMFYUI_ENV_IMAGES_URL = "https://hub.docker.com/v2/namespaces/akatzai/repositories/comfyui-env/tags?page_size=100"
DEFAULT_COMFYUI_PATH = os.getcwd()
FRONTEND_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]

# Instantiate global managers.
env_manager = EnvironmentManager()

user_settings_manager = UserSettingsManager()

connection_manager = ConnectionManager()

env_manager.set_ws_manager(connection_manager)

# --- Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    monitor_task = asyncio.create_task(env_manager.monitor_docker_events())
    yield
    # Shutdown
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

# --- Create FastAPI app ---
app = FastAPI(lifespan=lifespan)

# Add CORS middleware so that our frontend can communicate with the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You could use FRONTEND_ORIGINS instead
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await connection_manager.connect(websocket)
    try:
        while True:
            # Keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)

# --- Environment Endpoints ---

@app.post("/environments")
async def create_environment(env: Environment):
    """
    Create a new environment (Docker container) using the core EnvironmentManager.
    """
    try:
        new_env = env_manager.create_environment(env)
        return {"status": "success", "container_id": new_env.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/environments/{env_id}/duplicate")
async def duplicate_environment(env_id: str, env: Environment):
    """
    Duplicate an environment – note that duplication is only allowed after activation.
    """
    try:
        new_env = env_manager.duplicate_environment(env_id, env)
        return {"status": "success", "container_id": new_env.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/environments")
def list_environments(folderId: str = Query(None, description="Optional folder ID to filter environments")):
    """
    List environments, optionally filtering by folder.
    """
    try:
        envs = env_manager.load_environments(folderId)
        return envs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/environments/{env_id}")
async def delete_environment(env_id: str):
    """
    Delete an environment. If it’s not already soft-deleted (i.e. in the "deleted" folder)
    then it will be soft-deleted; otherwise it will be removed completely.
    """
    try:

        deleted_id = env_manager.delete_environment(env_id)
        return {"status": "success", "id": deleted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/environments/{env_id}/status")
def get_environment_status(env_id: str):
    """
    Get the current status of an environment.
    """
    try:
        env = env_manager.get_environment(env_id)
        return {"status": env.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/environments/{env_id}")
async def update_environment(env_id: str, update: EnvironmentUpdate):
    """
    Update an environment’s name and/or folderIds.
    """
    try:
        env = env_manager.update_environment(env_id, update)
        return {"status": "success", "container_id": env.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/environments/{env_id}/activate")
async def activate_environment(
    env_id: str,
    allow_multiple: bool = Query(
        False, description="Allow multiple environments running concurrently"
    ),
):
    """
    Activate an environment (start its Docker container). By default, this stops any
    other running containers unless allow_multiple is set to True.
    """
    try:
        env = env_manager.activate_environment(env_id, allow_multiple)
        return {"status": "success", "container_id": env.id}
    except Exception as e:
        print(f"Error activating environment {env_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/environments/{env_id}/deactivate")
async def deactivate_environment(env_id: str):
    """
    Deactivate (stop) an environment’s Docker container.
    """
    try:
        env = env_manager.deactivate_environment(env_id)
        return {"status": "success", "container_id": env.id}
    except Exception as e:
        print(f"Error deactivating environment {env_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- User Settings & Folder Endpoints ---

@app.get("/user-settings")
def get_user_settings_endpoint():
    """
    Get user settings.
    """
    try:
        settings = user_settings_manager.load(DEFAULT_COMFYUI_PATH)
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/user-settings")
def update_user_settings_endpoint(settings: UserSettings):
    """
    Update user settings.
    """
    try:
        user_settings_manager.save(settings)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/folders")
def create_folder(folder_data: dict):
    """
    Create a new folder. Expects a JSON payload with a "name" key.
    """
    try:
        folder_name = folder_data["name"]
        settings = user_settings_manager.load(DEFAULT_COMFYUI_PATH)
        updated_settings = user_settings_manager.create_folder(settings, folder_name)
        user_settings_manager.save(updated_settings)
        new_folder = next(f for f in updated_settings.folders if f.name == folder_name)
        return {"id": new_folder.id, "name": new_folder.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.put("/folders/{folder_id}")
def update_folder(folder_id: str, folder_data: dict):
    """
    Update a folder's name.
    """
    try:
        new_name = folder_data["name"]
        settings = user_settings_manager.load(DEFAULT_COMFYUI_PATH)
        updated_settings = user_settings_manager.update_folder(settings, folder_id, new_name)
        user_settings_manager.save(updated_settings)
        updated_folder = next(f for f in updated_settings.folders if f.id == folder_id)
        return {"id": updated_folder.id, "name": updated_folder.name}
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.delete("/folders/{folder_id}")
def delete_folder(folder_id: str):
    """
    Delete a folder. Will fail if any environment is still using this folder.
    """
    try:
        # Check if folder is used by any environments
        envs = env_manager.load_environments()
        for env in envs:
            if folder_id in env.folderIds:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete folder - it contains environments."
                )
        
        settings = user_settings_manager.load(DEFAULT_COMFYUI_PATH)
        updated_settings = user_settings_manager.delete_folder(settings, folder_id)
        user_settings_manager.save(updated_settings)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# --- Image & ComfyUI Endpoints ---

@app.get("/images/tags")
def get_image_tags():
    """
    Retrieve available image tags from Docker Hub.
    """
    try:
        response = requests.get(COMFYUI_ENV_IMAGES_URL)
        response.raise_for_status()
        data = response.json()
        tags = [tag['name'] for tag in data.get('results', [])]
        return {"tags": tags}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail="Error fetching tags from Docker Hub")


@app.get("/images/exists")
def check_image(image: str = Query(..., description="The name of the Docker image to check")):
    """
    Check if a Docker image exists locally.
    """
    try:
        # Using the docker interface from EnvironmentManager
        env_manager.docker_iface.get_image(image)
        return {"status": "found"}
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=404, detail="Image not found locally. Ready to pull.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/images/pull")
def pull_image(image: str = Query(..., description="The name of the Docker image to pull")):
    """
    Pull a Docker image and stream the pull progress.
    """
    def image_pull_stream():
        layers = {}
        total_download_size = 0
        total_downloaded = 0
        try:
            for line in env_manager.docker_iface.pull_image_api(image):
                status = line.get('status')
                layer_id = line.get('id')
                progress_detail = line.get('progressDetail', {})

                if layer_id:
                    if status == "Pull complete":
                        pass  # layer is done
                    elif status == "Already exists":
                        pass
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

                        overall_progress = (total_downloaded / total_download_size) * 100 if total_download_size > 0 else 0
                        yield f"data: {json.dumps({'progress': overall_progress})}\n\n"

            yield f"data: {json.dumps({'progress': 100, 'status': 'completed'})}\n\n"
        except docker.errors.APIError as e:
            yield f"data: {json.dumps({'error': f'Error pulling image {image}: {e}'})}\n\n"

    return StreamingResponse(image_pull_stream(), media_type="text/event-stream")


@app.post("/valid-comfyui-path")
def get_valid_comfyui_path_endpoint(obj: dict):
    """
    Check if the provided path contains a valid ComfyUI installation.
    """
    try:
        valid_path = check_comfyui_path(obj["path"])
        return {"valid_comfyui_path": str(valid_path)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/install-comfyui")
def install_comfyui_endpoint(obj: dict):
    """
    Attempt to install (clone) ComfyUI into the given path if no valid installation exists.
    """
    try:
        path = try_install_comfyui(obj["path"])
        return {"status": "success", "path": path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/environments/{env_id}/logs")
def stream_container_logs(env_id: str):
    """
    Stream logs from a running container.
    """
    try:
        container = env_manager.docker_iface.get_container(env_id)
        if container.status != "running":
            raise HTTPException(status_code=400, detail="Container is not running.")
        container_start_time = dateutil_parser.parse(container.attrs['State']['StartedAt'])

        def log_generator():
            for log in container.logs(stream=True, since=container_start_time):
                yield f"data: {log.decode('utf-8')}\n\n"

        return StreamingResponse(log_generator(), media_type="text/event-stream")
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Run the Server ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5172)
