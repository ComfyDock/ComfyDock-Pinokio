module.exports = {
  title: "ComfyDock",
  description: "Manage your ComfyUI environments with Docker",
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
      href: "https://comfydock.com",
      icon: "fa-solid fa-circle-info"
    },
    {
      text: "Install & Update",
      href: "install-and-update.json",
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