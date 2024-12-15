from pydantic import BaseModel
import json
from pathlib import Path
from filelock import FileLock

USER_SETTINGS_FILE = "user.settings.json"

class Folder(BaseModel):
    id: str
    name: str

# Pydantic model for user settings
class UserSettings(BaseModel):
    comfyui_path: str
    port: int = 8188
    runtime: str = "nvidia"
    command: str = ""
    folders: list[Folder] = []

def load_user_settings(default_comfyui_path: str) -> UserSettings:
    """Load user settings from a JSON file, or return default settings if the file does not exist."""
    lock = FileLock(f"{USER_SETTINGS_FILE}.lock")
    with lock:
        if Path(USER_SETTINGS_FILE).exists():
            with open(USER_SETTINGS_FILE, "r") as f:
                data = json.load(f)
                return UserSettings(**data)
        else:
            # Return default settings if the file does not exist
            return UserSettings(comfyui_path=default_comfyui_path)

def save_user_settings(settings: UserSettings):
    """Save user settings to a JSON file."""
    lock = FileLock(f"{USER_SETTINGS_FILE}.lock")
    with lock:
        with open(USER_SETTINGS_FILE, "w") as f:
            print(settings.model_dump())
            json.dump(settings.model_dump(), f, indent=4)

def update_user_settings(new_settings: dict):
    """Update user settings with new values."""
    print(new_settings)
    settings = load_user_settings(new_settings.get("comfyui_path", ""))
    print(settings)
    updated_settings = settings.model_copy(update=new_settings)
    print(updated_settings)
    save_user_settings(updated_settings)