from git import Repo
from fastapi import HTTPException
from pathlib import Path


def try_install_comfyui(path: str, branch: str = "master"):
    try:
        check_comfyui_path(path)
    except HTTPException as e:
        if e.detail != "No valid ComfyUI installation found.":
            raise e
    print(f"Installing ComfyUI from {path} with branch {branch}")
    comfyui_path = Path(path)
    try:
        comfyui_dir = comfyui_path / "ComfyUI"
        comfyui_dir.mkdir(parents=True, exist_ok=True)
        repo = Repo.clone_from(f"https://github.com/comfyanonymous/ComfyUI.git", str(comfyui_dir), branch=branch)
        if not repo or repo.is_dirty():
            raise HTTPException(status_code=400, detail=f"Failed to clone ComfyUI repository to {comfyui_dir}.")
        return str(comfyui_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during ComfyUI installation: {str(e)}")

def check_comfyui_path(path: str):
    """Check if the ComfyUI path is valid and handle installation if needed."""
    comfyui_path = Path(path)
    
    if not comfyui_path.exists():
        raise HTTPException(status_code=400, detail=f"ComfyUI path does not exist: {path}.")
    
    if not comfyui_path.is_dir():
        raise HTTPException(status_code=400, detail=f"ComfyUI path is not a directory: {path}.")
    
    if not comfyui_path.name.endswith("ComfyUI"):
        comfyui_dir = comfyui_path / "ComfyUI"
        if comfyui_dir.exists():
            raise HTTPException(status_code=400, detail=f"Existing ComfyUI directory found at: {comfyui_dir}.")
        
        raise HTTPException(status_code=400, detail="No valid ComfyUI installation found.")