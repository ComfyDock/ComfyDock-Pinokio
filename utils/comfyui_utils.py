from fastapi import HTTPException
from pathlib import Path
import subprocess


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
        
        # Use subprocess to run the git clone command
        clone_command = [
            "git", "clone",
            "--branch", branch,
            "https://github.com/comfyanonymous/ComfyUI.git",
            str(comfyui_dir)
        ]
        result = subprocess.run(clone_command, check=True, capture_output=True, text=True)
        print(result.stdout)
        
        return str(comfyui_dir)
    except subprocess.CalledProcessError as e:
        print(f"Error during git clone: {e.stderr}")
        raise HTTPException(status_code=400, detail=f"Failed to clone ComfyUI repository to {comfyui_dir}.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during ComfyUI installation: {str(e)}")

def check_comfyui_path(path: str):
    """Check if the ComfyUI path is valid and handle installation if needed. Returns the Path to the ComfyUI directory."""
    comfyui_path = Path(path)
    
    if not comfyui_path.exists():
        raise HTTPException(status_code=400, detail=f"ComfyUI path does not exist: {path}.")
    
    if not comfyui_path.is_dir():
        raise HTTPException(status_code=400, detail=f"ComfyUI path is not a directory: {path}.")
    
    if not comfyui_path.name.endswith("ComfyUI"):
        comfyui_dir = comfyui_path / "ComfyUI"
        if not comfyui_dir.exists():
            raise HTTPException(status_code=400, detail="No valid ComfyUI installation found.")
        return comfyui_dir
    return comfyui_path