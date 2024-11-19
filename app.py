import gradio as gr
from gradio_modal import Modal
import subprocess
import os
import json

USERDATA_FILE = "gradio_userdata.json"
DEFAULT_BASE_IMAGES = ["base-comfyui:1.0", "base-comfyui:2.0"]

# Helper Functions
def load_user_data():
    if os.path.exists(USERDATA_FILE):
        with open(USERDATA_FILE, "r") as f:
            return json.load(f)
    return {"environments": []}

def save_user_data(data):
    with open(USERDATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def create_new_environment(name, base_image, pull_image):
    data = load_user_data()
    if any(env["name"] == name for env in data["environments"]):
        return f"Environment with name '{name}' already exists."

    # Pull image if required
    if pull_image:
        try:
            subprocess.run(["docker", "pull", base_image], check=True)
        except subprocess.CalledProcessError:
            return f"Failed to pull Docker image: {base_image}"

    # Create environment directory (if needed) and container
    env_path = os.path.join(os.getcwd(), "envs", name)
    os.makedirs(env_path, exist_ok=True)

    # Add environment to user data
    data["environments"].append({"name": name, "image": base_image, "path": env_path})
    save_user_data(data)
    return f"Environment '{name}' created successfully!"

def list_environments():
    data = load_user_data()
    return data["environments"]

def run_environment(name):
    data = load_user_data()

    # Shut down running containers in the user's environments
    for env in data["environments"]:
        try:
            subprocess.run(["docker", "rm", "-f", env["name"]], check=True)
        except subprocess.CalledProcessError:
            pass

    # Start the selected container
    env = next((e for e in data["environments"] if e["name"] == name), None)
    if not env:
        return f"No environment found with name '{name}'."
    
    try:
        subprocess.run([
            "docker", "run", "-d", "--rm", "--name", env["name"], "-v",
            f"{env['path']}:/app/comfyui", "-p", "8188:8188", env["image"]
        ], check=True)
        return f"Environment '{name}' is now running!"
    except subprocess.CalledProcessError:
        return f"Failed to start environment '{name}'."

def delete_environment(name):
    data = load_user_data()
    data["environments"] = [e for e in data["environments"] if e["name"] != name]
    save_user_data(data)
    return f"Environment '{name}' deleted successfully!"

def duplicate_environment(name):
    data = load_user_data()
    env = next((e for e in data["environments"] if e["name"] == name), None)
    if not env:
        return f"No environment found with name '{name}'."

    new_name = f"{name}_copy"
    count = 1
    while any(e["name"] == new_name for e in data["environments"]):
        new_name = f"{name}_copy{count}"
        count += 1

    new_env = {"name": new_name, "image": env["image"], "path": env["path"] + "_copy"}
    os.makedirs(new_env["path"], exist_ok=True)
    data["environments"].append(new_env)
    save_user_data(data)
    return f"Environment '{name}' duplicated as '{new_name}'."

# Gradio UI
def update_ui():
    envs = list_environments()
    cards = []
    for env in envs:
        with gr.Column(scale=1):
            env_name_box = gr.Textbox(value=f"Name: {env['name']}", label="Environment Name", interactive=False)
            gr.Textbox(value=f"Image: {env['image']}", label="Base Image", interactive=False)
            gr.Button(f"Run {env['name']}", variant="primary").click(run_environment, inputs=[env_name_box], outputs=[])
            gr.Button(f"Duplicate {env['name']}", variant="secondary").click(duplicate_environment, inputs=[env_name_box], outputs=[])
            gr.Button(f"Delete {env['name']}", variant="danger").click(delete_environment, inputs=[env_name_box], outputs=[])

    return cards


# Function to toggle form visibility
def toggle_form(show):
    return gr.update(visible=show)

# Function to toggle modal visibility
def show_modal():
    return Modal(visible=True)

# Gradio UI
with gr.Blocks() as app:
    # Main interface
    with gr.Row():
        btn_create = gr.Button("Create New Environment", variant="primary")
        
    with gr.Row():
        update_ui()

    # Modal for creating a new environment
    with Modal(visible=False) as create_modal:
        env_name = gr.Textbox(label="Environment Name", placeholder="Enter a unique name for the environment")
        base_image = gr.Dropdown(choices=["base-comfyui:1.0", "base-comfyui:2.0"], label="Base Image")
        local_image = gr.Textbox(label="Local Image", placeholder="Enter local image name if not in dropdown")
        pull_image = gr.Checkbox(label="Pull Image from DockerHub", value=True)
        submit_button = gr.Button("Create Environment", variant="primary")
        result = gr.Textbox(label="Result", interactive=False)

    # Open modal on button click
    btn_create.click(show_modal, None, create_modal)

    # Handle form submission
    def create_environment_with_local_option(name, base_image, local_image, pull_image):
        # Use local image if provided, otherwise use the selected base image
        image_to_use = local_image if local_image else base_image
        return create_new_environment(name, image_to_use, pull_image)

    submit_button.click(
        create_environment_with_local_option,
        inputs=[env_name, base_image, local_image, pull_image],
        outputs=result
    )

app.launch()
