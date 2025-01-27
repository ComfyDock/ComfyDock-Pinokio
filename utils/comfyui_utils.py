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
        raise HTTPException(status_code=400, detail=f"Failed to clone ComfyUI repository to {comfyui_dir}. Error: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during ComfyUI installation: {str(e)}")
    

def is_comfyui_repo(path: str) -> bool:
    """
    Returns True if `path` points to a directory that appears
    to be a valid ComfyUI repo.
    """
    repo_path = Path(path)
    
    print(repo_path)

    # Ensure the path is a directory
    if not repo_path.is_dir():
        return False

    # Check for required files and directories
    required_files = ["main.py"]
    required_dirs = ["models", "comfy", "comfy_execution", "web"]

    for file_name in required_files:
        print(file_name)
        if not (repo_path / file_name).is_file():
            print("file not found")
            return False

    for dir_name in required_dirs:
        print(dir_name)
        if not (repo_path / dir_name).is_dir():
            print("dir not found")
            return False

    return True


def check_comfyui_path(path: str):
    """Check if the ComfyUI path is valid and handle installation if needed. Returns the Path to the ComfyUI directory."""
    comfyui_path = Path(path)
    
    if not comfyui_path.exists():
        raise HTTPException(status_code=400, detail=f"ComfyUI path does not exist: {path}.")
    
    if not comfyui_path.is_dir():
        raise HTTPException(status_code=400, detail=f"ComfyUI path is not a directory: {path}.")
    
    if not is_comfyui_repo(path):
        raise HTTPException(status_code=400, detail="No valid ComfyUI installation found.")
    return comfyui_path