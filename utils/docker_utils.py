from pathlib import Path
import posixpath
import tarfile
import docker
from docker.types import Mount
from docker.errors import APIError, NotFound
from fastapi import HTTPException
import tempfile
import re
import os


# Constants
CONTAINER_COMFYUI_PATH = "/app/ComfyUI"
SIGNAL_TIMEOUT = 2
BLACKLIST_REQUIREMENTS = ['torch']
EXCLUDE_CUSTOM_NODE_DIRS = ['__pycache__', 'ComfyUI-Manager']

try: 
    client = docker.from_env(timeout=360) # 5 minutes timeout
except docker.errors.DockerException:
    raise HTTPException(status_code=500, detail="Failed to connect to Docker. Please ensure your Docker client is running.")
  
def create_container(image, name, command, runtime=None, device_requests=None, ports=None, mounts=None):
    try:
        container = client.containers.create(
            image=image,
            name=name,
            command=command,
            runtime=runtime,
            device_requests=device_requests,
            ports=ports,
            mounts=mounts,
        )
        return container
    except APIError as e:
        raise e

def get_container(container_id):
    try:
        return client.containers.get(container_id)
    except NotFound:
        raise
    except APIError as e:
        raise e

def commit_container(container, repository, tag):
    try:
        return container.commit(repository=repository, tag=tag)
    except APIError as e:
        raise e

def remove_image(image, force=False):
    try:
        client.images.remove(image, force=force)
    except NotFound:
        pass
    except APIError as e:
        raise e

def get_image(image):
    try:
        return client.images.get(image)
    except NotFound:
        raise
    except APIError as e:
        raise e

def start_container(container):
    try:
        if container.status != "running":
            container.start()
    except APIError as e:
        raise e

def stop_container(container, timeout=2):
    try:
        container.stop(timeout=timeout)
    except APIError as e:
        raise e

def remove_container(container):
    try:
        container.remove()
    except APIError as e:
        raise e

def pull_image_api(image):
    try:
        # Use the Docker API to pull the image and stream the response
        pull_stream = client.api.pull(image, stream=True, decode=True)
        for line in pull_stream:
            yield line
    except APIError as e:
        raise e

def try_pull_image(image):
    # Check if the image is available locally, if not, pull it from Docker Hub
    try:
        client.images.get(image)
        print(f"Image {image} found locally.")
    except docker.errors.ImageNotFound:
        print(f"Image {image} not found locally. Pulling from Docker Hub...")
        client.images.pull(image)
        print(f"Image {image} successfully pulled from Docker Hub.")
    except APIError as e:
        print(f"Error pulling image {image}: {e}")
        raise e

def ensure_directory_exists(container, path):
    """Ensure that a directory exists in the container."""
    try:
        # Execute a command to create the directory if it doesn't exist
        container.exec_run(f"mkdir -p {path}")
    except docker.errors.APIError as e:
        print(f"Error creating directory {path} in container: {e}")
        raise

def copy_to_container(container_id: str, source_path: str, container_path: str, exclude_dirs: list = []):
    try:
        container = client.containers.get(container_id)

        # Ensure the target directory exists in the container
        ensure_directory_exists(container, container_path)

        # Use a temporary directory for the tar file
        with tempfile.TemporaryDirectory() as temp_dir:
            tar_path = Path(temp_dir) / "archive.tar"

            # Create a tar archive of the source directory or file
            with tarfile.open(tar_path, mode="w") as archive:
                # Use Pathlib to iterate over the source directory
                for path in Path(source_path).rglob('*'):
                    # Check if the path is a directory and if it should be excluded
                    if path.is_dir() and path.name in exclude_dirs:
                        continue
                    # Calculate the relative path to maintain the directory structure
                    relative_path = path.relative_to(source_path)
                    # Add the file or directory to the archive
                    archive.add(str(path), arcname=str(relative_path))

            # Send the tar archive to the container
            with open(tar_path, "rb") as tar_data:
                print(f"Sending {source_path} to {container_id}:{container_path}")
                try:
                    container.put_archive(container_path, tar_data)
                    print(f"Copied {source_path} to {container_id}:{container_path}")
                except Exception as e:
                    print(f"Error sending {source_path} to {container_id}:{container_path}: {e}")
                    raise

    except docker.errors.NotFound:
        print(f"Container {container_id} not found.")
    except docker.errors.APIError as e:
        print(f"Docker API error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        
        
def convert_old_to_new_style(old_config: dict, comfyui_path: Path) -> dict:
    """
    Convert old style config like:
    {
      "user": "mount",
      "models": "mount",
      "output": "mount",
      "input": "mount"
    }
    into new style:
    {
      "mounts": [
        {
          "container_path": "/app/ComfyUI/user",
          "host_path": "/path/to/comfyui/user",
          "type": "mount",
          "read_only": false
        },
        ...
      ]
    }

    Note: This function interprets each key as a subdirectory of comfyui_path,
    with the same subdirectory name inside the container. Feel free to customize
    how you decide the container_path.
    """

    new_config = {"mounts": []}

    for key, action in old_config.items():
        # only convert if action == "mount" or "copy"
        if action != "mount" and action != "copy":
            continue

        # for old style, assume local directory is comfyui_path / key
        host_subdir = (comfyui_path / key).resolve()

        # container directory is /app/ComfyUI/key
        container_subdir = Path(CONTAINER_COMFYUI_PATH) / key

        # build a new style record
        mount_entry = {
            "container_path": container_subdir.as_posix(),
            "host_path": host_subdir.as_posix(),
            "type": "mount",
            "read_only": False
        }
        new_config["mounts"].append(mount_entry)

    return new_config


def _process_copy_mount(mount: dict, comfyui_path: Path, container_id: str):
    """
    Processes a single mount entry with type 'copy'.
    Creates the source directory if needed (if relative) and copies data into the container.
    """
    host_path_str = mount.get("host_path")
    container_path = mount.get("container_path")
    if not host_path_str or not container_path:
        print(f"Skipping mount entry because host_path or container_path is missing: {mount}")
        return False

    source_path = Path(host_path_str)
    if not source_path.is_absolute():
        source_path = (comfyui_path / source_path).resolve()

    if source_path.exists():
        print(f"Copying {source_path} to container at {container_path}")
        copy_to_container(container_id, str(source_path), container_path, EXCLUDE_CUSTOM_NODE_DIRS)
        # If copying custom_nodes, run additional installation
        if "custom_nodes" in container_path:
            install_custom_nodes(container_id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
            return True
    else:
        print(f"Local path does not exist: {source_path}")
    return False

def _process_mount_mount(mount: dict, comfyui_path: Path, container_id: str):
    """
    For backward compatibility:
    If the type is "mount" and it's "custom_nodes", call install_custom_nodes.
    This function can be extended if more mount-specific processing is needed.
    """
    if mount.get("type") == "mount" and "custom_nodes" in mount.get("container_path", ""):
        install_custom_nodes(container_id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
        return True
    return False

def copy_directories_to_container(container_id: str, comfyui_path: Path, mount_config: dict):
    """
    Copy specified directories from the host to the container based on the mount configuration.
    
    Supports:
      - New style: {"mounts": [ { "host_path": ..., "container_path": ..., "type": "copy" or "mount", ... }, ... ]}
      - Old style: { "models": "copy", "user": "mount", ... }
    
    For old style, known keys are mapped to subdirectories of comfyui_path and /app/ComfyUI.
    """
    installed_custom_nodes = False

    print(f'copy_directories_to_container: mount_config: {mount_config}')

    # Determine config style. If "mounts" key exists and is a list, assume new style.
    if "mounts" in mount_config and isinstance(mount_config["mounts"], list):
        config = mount_config
    else:
        print("Detected old style mount config. Converting to new style.")
        config = convert_old_to_new_style(mount_config, comfyui_path)

    print(f"Using mount config: {config}")

    for mount in config.get("mounts", []):
        action = mount.get("type", "").lower()
        if action == "copy":
            if _process_copy_mount(mount, comfyui_path, container_id):
                # If the mount relates to custom_nodes, flag it as installed
                if "custom_nodes" in mount.get("container_path", ""):
                    installed_custom_nodes = True
        elif action == "mount":
            # For mount actions, if it's custom_nodes and you want to run install_custom_nodes,
            # handle it here.
            if _process_mount_mount(mount, comfyui_path, container_id):
                installed_custom_nodes = True

    return installed_custom_nodes


# def copy_directories_to_container(container_id: str, comfyui_path: Path, mount_config: dict):
#     """Copy specified directories from the host to the container based on the mount configuration."""
#     path_mapping = {
#         "custom_nodes": "custom_nodes",
#         "user": "user",
#         "models": "models",
#         "output": "output",
#         "input": "input"
#     }
#     installed_custom_nodes = False
    
#     print(f'mount_config: {mount_config}')

#     for key, action in mount_config.items():
#         if action == "copy":
#             dir_name = path_mapping.get(key, key)
#             local_path = comfyui_path / Path(dir_name)
#             container_path = (Path(CONTAINER_COMFYUI_PATH) / Path(dir_name)).as_posix()
#             print(f"dirname: {dir_name}, copying {local_path} to {container_path}")

#             if local_path.exists():
#                 print(f"Copying {local_path} to container at {container_path}")
#                 copy_to_container(container_id, str(local_path), str(container_path), EXCLUDE_CUSTOM_NODE_DIRS)
#                 if key == "custom_nodes":
#                     install_custom_nodes(container_id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
#                     installed_custom_nodes = True
#             else:
#                 print(f"Local path does not exist: {local_path}")
#         if action == "mount":
#             if key == "custom_nodes":
#                 install_custom_nodes(container_id, BLACKLIST_REQUIREMENTS, EXCLUDE_CUSTOM_NODE_DIRS)
#                 installed_custom_nodes = True

#     return installed_custom_nodes

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


def _create_mounts_from_new_config(mount_config: dict, comfyui_path: Path):
    """
    The 'new-style' function that expects:
    {
      "mounts": [
        {
          "container_path": "/app/ComfyUI/models",
          "host_path": "C:\\path\\to\\my\\shared\\models\\drive\\directory",
          "type": "mount",
          "read_only": false,
          "override": false
        },
        ...
      ]
    }
    """

    print(f"Creating mounts for environment")
    mounts = []

    user_mounts = mount_config.get("mounts", [])
    for m in user_mounts:
        print(f"Mount: {m}")
        action = m.get("type", "").lower()
        if action != "mount" and action != "copy":
            print(f"Skipping mount for {m} because type is '{action}' (not 'mount' or 'copy').")
            continue

        container_path = m.get("container_path")
        host_path = m.get("host_path")

        if not container_path or not host_path:
            print(f"Skipping entry {m} because container_path or host_path is missing.")
            continue

        # If host_path is relative, interpret it as relative to comfyui_path
        source_path = Path(host_path)
        print(f"source_path: {source_path}")
        if not source_path.is_absolute():
            source_path = comfyui_path / source_path
            print(f"source_path: {source_path}")

        # Ensure the source directory exists (create if needed)
        if not source_path.exists():
            print(f"Host directory does not exist: {source_path}. Creating directory.")
            source_path.mkdir(parents=True, exist_ok=True)

        # Convert paths to posix-style strings for Docker
        source_str = str(source_path.resolve())
        print(f"source_str: {source_str}")
        target_str = str(Path(container_path).as_posix())
        print(f"target_str: {target_str}")
        read_only = m.get("read_only", False)

        print(f"Mounting host '{source_str}' to container '{target_str}' (read_only={read_only})")

        mounts.append(
            Mount(
                target=target_str,
                source=source_str,
                type='bind',
                read_only=read_only
            )
        )

    # Optionally add /usr/lib/wsl -> /usr/lib/wsl mount if it exists
    wsl_path = Path("/usr/lib/wsl")
    if wsl_path.exists():
        mounts.append(
            Mount(
                target="/usr/lib/wsl",
                source=str(wsl_path),
                type='bind',
                read_only=True,
            )
        )

    return mounts

def create_mounts(mount_config: dict, comfyui_path: Path):
    """
    Main function that is backwards-compatible with old style config, and also supports new style.

    For old style, e.g.:
    {
      "user": "mount",
      "models": "mount",
      "output": "mount",
      "input": "mount"
    }

    For new style, e.g.:
    {
      "mounts": [
        {
          "container_path": "/app/ComfyUI/models",
          "host_path": "C:\\path\\to\\my\\shared\\models\\drive\\directory",
          "type": "mount",
          "read_only": false
        },
        ...
      ] 
    }
    """

    config = mount_config
    if "mounts" not in config or not isinstance(config["mounts"], list):
        # We'll assume it's old style and convert
        print("Detected old style mount config. Converting to new style.")
        config = convert_old_to_new_style(mount_config, comfyui_path)
        
    return _create_mounts_from_new_config(config, comfyui_path)