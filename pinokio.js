module.exports = {
  title: "Comfy Environment Manager",
  description: "Manage your ComfyUI environments",
  icon: "assets/icon.png",
  version: "2.0",
  pre: [
    {
      icon: "assets/icon-docker-square.svg",
      title: "Docker Desktop",
      description: "Get up and running with Docker Desktop.",
      href: "https://www.docker.com/products/docker-desktop/"
    }
  ],
  menu: [
    {
      text: "Help",
      href: "https://cyber-damselfly-b6c.notion.site/ComfyUI-Environment-Manager-14ffd5b1ca3b804abafbdb4bd6b8068e",
      icon: "fa-solid fa-circle-info"
    },
    {
      text: "Install",
      href: "install.json",
      icon: "fa-solid fa-screwdriver-wrench"
    },
    {
      text: "Start",
      href: "start.json",
      icon: "fa-solid fa-play"
    },
    {
      text: "Show Environments",
      href: "http://localhost:8000",
      icon: "fa-solid fa-eye"
    }
  ]
}