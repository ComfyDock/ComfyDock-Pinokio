# **ComfyDock**

## Update

***This repo is now ARCHIVED and will not see further development. To access the new version of ComfyDock (v1.0+) please visit the [monorepo](https://github.com/ComfyDock/ComfyDock).***

---

⭐ **If you find this tool helpful, please consider giving this repo a star!** ⭐


For a more in-depth guide see the [Documentation](https://www.comfydock.com)

> Get help instantly using my [Custom GPT!](https://chatgpt.com/g/g-676795064ce48191b20d03bf6d3b3827-comfyui-environment-manager-helper)

<img src="assets/icon.png" alt="Logo" width="400"/>

## 🌟 **Why Use the Environment Manager?**

### **Common Challenges with ComfyUI**

- **Custom Node Installation Issues:** Installing new nodes can break your setup.
- **Workflow Compatibility:** Workflows often depend on specific custom nodes and ComfyUI versions.
- **Security Risks:** Directly installing custom nodes on your machine increases exposure to malicious code.

### **How This Tool Helps**

- **Environment Duplication:** Safely experiment with new setups by duplicating your current environment.
- **Environment Sharing:** Share and download pre-configured environments via DockerHub.
- **Enhanced Security:** Isolate ComfyUI in containers to protect your host machine.

---

https://github.com/user-attachments/assets/7f1e868e-fb0d-4b1b-aaec-a1ef1a9949f3

## 🚀 **Features**

- **🛠️ Create Environments:** Set up isolated ComfyUI instances with specific versions and dependencies.
- **📑 Duplicate Environments:** Safely test changes or updates without affecting your main setup.
- **🌍 Environment Sharing:** Export and share your environment to ensure workflow compatibility.
- **🔧 Custom Node Support:** Easily install and manage custom nodes.
- **⚙️ Advanced Options:** GPU acceleration, runtime settings, and more.

<br>
  
## 🛠️ **Installation**

https://github.com/user-attachments/assets/3b95c4a5-e88b-458e-9933-68856f3b09da

### **Prerequisites**

- **OS:** Windows or Linux (macOS supports CPU only).
- **Docker:** [Docker Desktop](https://www.docker.com/products/docker-desktop) or Docker Engine with NVIDIA Container Toolkit.
- **NVIDIA Drivers:** Ensure they are up-to-date.
- **WSL (Windows Only):** Latest version installed and updated.

### **Steps**

1. Install Docker Desktop:
   - Follow the installation guide for your OS.
   - Verify installation:
     ```bash
     wsl docker --version
     ```

2. Install the Environment Manager using Pinokio:
   - Download Pinokio from [here](https://program.pinokio.computer/#/?id=install).
   - Use **Discover > Download from URL** and paste:
     ```
     https://github.com/ComfyDock/ComfyDock-Pinokio
     ```
   - Follow the installation process.

3. Launch the Environment Manager:
   - Open Pinokio and start the ComfyUI Environment Manager.
   - Ensure Docker is running.


## 📖 **Usage**

### **Manager Layout**

<img src="https://github.com/user-attachments/assets/b445b923-3b7f-4675-9ea1-c57904f65597" alt="Logo" width="60%"/>

- **Settings Panel:** Configure ComfyUI defaults (path, port, runtime, etc.).
- **Environments Grid:** Manage your environments.

### **Creating a New Environment**

https://github.com/user-attachments/assets/50becd6e-5c6a-4018-8ef3-596b17ae6cc1

1. Click **Create Environment**.
2. Fill in the fields:
   - **Name:** Alphanumeric, e.g., `comfy-env-01`.
   - **ComfyUI Release:** Choose a specific version or "latest."
   - **Environment Type:**
     - Default: Mounts input/output directories from your host machine.
     - Custom: Specify mounts and data copying behavior.
3. Click **Create** to finalize setup.

### **Duplicating an Environment**

https://github.com/user-attachments/assets/ac2880f6-55b8-4b03-97e8-8ba0f86de87e

- Use the **Duplicate** button on an existing environment.
- Mounted directories are **not copied**, but installed dependencies and container data are included.

### **Managing Environments**

- **Activate:** Start the environment (status turns green when running).
- **Settings:** Update environment details.
- **Logs:** View the environment's real-time output.
- **Delete:** Remove an environment (mounted host directories are preserved).

<br>

## 🛡️ **Troubleshooting**

### Slow Model Loading

- Speed up loading times by moving model files to a WSL installation.
- Access WSL paths in File Explorer:
  ```
  \\wsl.localhost\<distro>\<path-to-directory>
  ```

### Dependencies:

[https://github.com/ComfyDock/ComfyDock-Core](https://github.com/ComfyDock/ComfyDock-Core)

[https://github.com/ComfyDock/ComfyDock-Server](https://github.com/ComfyDock/ComfyDock-Server)

[https://github.com/ComfyDock/ComfyDock-Frontend](https://github.com/ComfyDock/ComfyDock-Frontend)

[https://github.com/ComfyDock/ComfyDock-Docker](https://github.com/ComfyDock/ComfyDock-Docker)

<br>

## 👨‍💻 **About the Author**

**Akatz AI:**

- Website: [akatz.ai](https://akatz.ai/)
- [Ko-fi](https://ko-fi.com/akatz)
- [Patreon](http://patreon.com/Akatz)
- [Civitai](https://civitai.com/user/akatz)
- [YouTube](https://www.youtube.com/@akatz_ai)
- [Instagram](https://www.instagram.com/akatz.ai/)
- [TikTok](https://www.tiktok.com/@akatz_ai)
- [X (formerly Twitter)](https://x.com/akatz_ai)
- [GitHub](https://github.com/akatz-ai)

**Contacts:**

- Email: **akatzfey@sendysoftware.com**

---

⭐ **Enjoy the tool? Don’t forget to star the repo and share it with your community!**

