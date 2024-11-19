from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import docker
import json
import os
import uvicorn
app = FastAPI()
client = docker.from_env()

DB_FILE = "environments.json"

# Helper function to load and save JSON data
def load_environments():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return []

def save_environments(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Pydantic model for environment creation
class Environment(BaseModel):
    name: str
    image: str
    command: str = ""

@app.post("/environments")
def create_environment(env: Environment):
    """Create a new Docker container and save to local database."""
    environments = load_environments()

    # Check if the environment name already exists
    if any(e["name"] == env.name for e in environments):
        raise HTTPException(status_code=400, detail="Environment name already exists.")

    # Create Docker container
    try:
        container = client.containers.run(
            env.image,
            name=env.name,
            detach=True,
            command=env.command,
        )
        # Save to database
        new_env = {
            "name": env.name,
            "image": env.image,
            "status": "running",
            "id": container.id,
        }
        environments.append(new_env)
        save_environments(environments)
        return {"status": "success", "container_id": container.id}
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/environments")
def list_environments():
    """List environments from the local database."""
    return load_environments()

@app.delete("/environments/{name}")
def delete_environment(name: str):
    """Stop and remove a Docker container and update local database."""
    environments = load_environments()

    # Find the environment
    env = next((e for e in environments if e["name"] == name), None)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found.")

    try:
        # Stop and remove the Docker container
        container = client.containers.get(env["id"])
        container.stop()
        container.remove()

        # Update the database
        environments = [e for e in environments if e["name"] != name]
        save_environments(environments)
        return {"status": "success", "name": name}
    except docker.errors.NotFound:
        # If container is not found, just update the database
        environments = [e for e in environments if e["name"] != name]
        save_environments(environments)
        return {"status": "success (container not found)", "name": name}
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/environments/{name}")
def update_environment(name: str, env: Environment):
    """Update an environment's settings and restart the Docker container."""
    environments = load_environments()

    # Find the environment
    index = next((i for i, e in enumerate(environments) if e["name"] == name), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Environment not found.")

    try:
        # Stop and remove the existing container
        container = client.containers.get(environments[index]["id"])
        container.stop()
        container.remove()

        # Create a new container with updated settings
        new_container = client.containers.run(
            env.image,
            name=env.name,
            detach=True,
            command=env.command,
        )

        # Update the database
        environments[index] = {
            "name": env.name,
            "image": env.image,
            "status": "running",
            "id": new_container.id,
        }
        save_environments(environments)
        return {"status": "success", "container_id": new_container.id}
    except docker.errors.APIError as e:
        raise HTTPException(status_code=400, detail=str(e))
      
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5172)
