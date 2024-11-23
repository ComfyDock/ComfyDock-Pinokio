import docker
from docker.types import DeviceRequest, Mount

# Initialize the Docker client
client = docker.from_env()

# Define variables
local_comfyui_path = 'C:\\Users\\akatz\\Documents\\ComfyUI'  # Use raw string for Windows path
container_comfyui_path = '/app/ComfyUI'
image_name = 'comfyui-base-cuda12.6.2-pytorch2.5.1:latest'
container_name = 'comfyui_test_container'

# Create device request for GPU access
device_request = DeviceRequest(
    count=-1,  # Access all GPUs
    capabilities=[['gpu']]
)

# Define the mounts
mounts = [
    # Mount the local ComfyUI directory to the container's /app/ComfyUI directory
    Mount(
        target=container_comfyui_path,
        source=local_comfyui_path,
        type='bind',
        read_only=False,
    ),
    # Override the /app/ComfyUI/custom_nodes directory to use the container's internal version
    Mount(
        source='',  
        target=f'{container_comfyui_path}/custom_nodes',
        type='volume',  # Creates an anonymous volume
    ),
]

# Run the container
try:
    container = client.containers.run(
        image=image_name,
        name=container_name,
        runtime='nvidia',  # Use NVIDIA runtime for GPU access
        device_requests=[device_request],
        ports={'8188/tcp': 8188},  # Map container port 8188 to host port 8188
        mounts=mounts,
        detach=True,  # Run container in the background
    )
    print(f"Container '{container.name}' is running.")

except docker.errors.APIError as e:
    print(f"Error: {e.explanation}")