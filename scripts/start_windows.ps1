<#
.SYNOPSIS
  Bootstrap script to set up Git, update the repo, install 'uv',
  create a virtual environment, install dependencies, and run start_server.py.

.DESCRIPTION
  1. Checks if git is available; if not, tries to silently install Git for Windows.
  2. Update local repo (git pull) if it's a valid Git repository.
  3. Checks if 'uv' is installed; if not, downloads and installs it via PowerShell script.
  4. Creates/activates a '.venv' environment using 'uv'.
  5. Installs dependencies from 'requirements.txt' using 'uv pip' if present.
  6. Runs 'start_server.py' in the background, displays an ASCII banner and link, 
     and attempts to open the link in the default browser.
#>

###############################################################################
# 0. Define Variables
###############################################################################

$scriptPath     = $MyInvocation.MyCommand.Path
$scriptDir      = Split-Path -Parent $scriptPath
$projectDir     = Split-Path -Parent $scriptDir
Set-Location -Path $projectDir

$GitInstallerUrl = "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.2/Git-2.44.0-64-bit.exe"
$UvInstallScriptUrl = "https://astral.sh/uv/install.ps1" # Official UV Windows script URL

$VenvName     = ".venv"
$ReqFile      = "requirements.txt"
$ServerScript = "start_server.py"


###############################################################################
# 1. Check if Git is installed
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 1. Check if Git is installed"
Write-Host "============================="

$gitCheck = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCheck) {
    Write-Host "Git not found on your system."

    # Try silent install from GitInstallerUrl
    try {
        Write-Host "Downloading Git installer from $GitInstallerUrl ..."
        Invoke-WebRequest -Uri $GitInstallerUrl -OutFile "git-installer.exe" -UseBasicParsing
        Write-Host "Git installer downloaded."

        Write-Host "Installing Git silently..."
        Start-Process -FilePath ".\git-installer.exe" -ArgumentList "/VERYSILENT" -Wait -NoNewWindow
        Remove-Item ".\git-installer.exe" -ErrorAction SilentlyContinue

        Write-Host "Git installed successfully. You may need to open a new PowerShell session if 'git' isn't recognized."
    }
    catch {
        Write-Host "Failed to install Git silently. Error: $_"
        exit 1
    }
}
else {
    Write-Host "Git is already installed."
}

###############################################################################
# 2. Update local repo (git pull)
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 2. Update local repo (git pull)"
Write-Host "============================="

try {
    git rev-parse --is-inside-work-tree | Out-Null
    Write-Host "Pulling latest changes from the repository..."
    git pull
    Write-Host "Repository updated successfully."
}
catch {
    Write-Host "Current directory is not a Git repository. Skipping git pull."
}

###############################################################################
# 3. Install uv (Package manager)
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 3. Install uv"
Write-Host "============================="

$uvCheck = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCheck) {
    Write-Host "'uv' not found. Installing 'uv' using the official PowerShell install script..."

    try {
        Write-Host "Downloading uv install script from $UvInstallScriptUrl ..."
        # Grab the script, then invoke it
        $uvScriptContent = Invoke-WebRequest -Uri $UvInstallScriptUrl -UseBasicParsing
        Write-Host "UV install script downloaded. Executing..."
        Invoke-Expression $uvScriptContent.Content
        Write-Host "'uv' installed successfully."
    }
    catch {
        Write-Host "Failed to install 'uv'. Visit https://uv.sh/docs/ for manual installation instructions."
        exit 1
    }
}
else {
    Write-Host "'uv' is already installed."
}

###############################################################################
# 4. Create (or reuse) a uv-based virtual environment
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 4. Create (or reuse) uv-based venv"
Write-Host "============================="

if (-not (Test-Path $VenvName)) {
    Write-Host "Creating the virtual environment with 'uv'..."
    try {
        uv venv "$VenvName"
        Write-Host "Virtual environment created."
    }
    catch {
        Write-Host "Failed to create virtual environment with 'uv'. Ensure 'uv' is installed correctly."
        exit 1
    }
}
else {
    Write-Host "Virtual environment '$VenvName' already exists; reusing it..."
}

###############################################################################
# 5. Install requirements (if present)
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 5. Install requirements"
Write-Host "============================="

if (Test-Path $ReqFile) {
    Write-Host "Installing dependencies from $ReqFile..."
    try {
        uv pip install -r $ReqFile
        Write-Host "Dependencies installed successfully."
    }
    catch {
        Write-Host "Failed to install dependencies from '$ReqFile'."
        exit 1
    }
}
else {
    Write-Host "No $ReqFile file found; skipping 'uv pip install -r $ReqFile'."
}

###############################################################################
# 6. Print ASCII Art and Link Banner, Attempt to Open Browser
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 6. Prepare to Run start_server.py"
Write-Host "============================="

if (-not (Test-Path $ServerScript)) {
    Write-Host "Could not find '$ServerScript'. Make sure you're in the correct repository directory."
    exit 0
}

Write-Host "Server script '$ServerScript' found. Preparing to start..."

# ASCII art banner
$asciiArt = @"
      ___  __   _  _  ____  _  _  _  _  __    ____  __ _  _  _  __  ____   __   __ _  _  _  ____  __ _  ____ 
     / __)/  \ ( \/ )(  __)( \/ )/ )( \(  )  (  __)(  ( \/ )( \(  )(  _ \ /  \ (  ( \( \/ )(  __)(  ( \(_  _)
    ( (__(  O )/ \/ \ ) _)  )  / ) \/ ( )(    ) _) /    /\ \/ / )(  )   /(  O )/    // \/ \ ) _) /    /  )(  
     \___)\__/ \_)(_/(__)  (__/  \____/(__)  (____)\_)__) \__/ (__)(__\_) \__/ \_)__)\_)(_/(____)\_)__) (__)
     _  _   __   __ _   __    ___  ____  ____                                                                
    ( \/ ) / _\ (  ( \ / _\  / __)(  __)(  _ \                                                               
    / \/ \/    \/    //    \( (_ \ ) _)  )   /                                                               
    \_)(_/\_/\_/\_)__)\_/\_/ \___/(____)(__\_)
    
    By Akatz
"@

Write-Host "`n$asciiArt" -ForegroundColor Yellow

# Link banner
$link = "http://localhost:8000"
$borderLen = $link.Length + 8
$border = '*' * $borderLen

Write-Host ""
Write-Host $border
Write-Host "*   $link   *"
Write-Host $border

Write-Host ""
Write-Host "ComfyUI Environment Manager is ready! Open the link above in your browser."
Write-Host "When you run the server below, you can press Ctrl + C to terminate it."

Write-Host ""
Write-Host "============================="
Write-Host "== 7. Open the URL in Browser"
Write-Host "============================="

function Open-Browser {
    param(
        [string]$Url
    )
    try {
        Start-Process -FilePath $Url
        Write-Host "Attempted to open '$Url' in default browser."
    }
    catch {
        Write-Host "Failed to open the browser automatically. Please open '$Url' manually."
    }
}

Open-Browser -Url $link

###############################################################################
# 7. Run start_server.py in the Same PowerShell Window
###############################################################################

Write-Host ""
Write-Host "============================="
Write-Host "== 8. Run start_server.py"
Write-Host "============================="

Write-Host "Starting server in the current PowerShell window. Logs will appear below."
Write-Host "Press Ctrl + C to terminate the server at any time."

try {
    # This call blocks until the server script finishes or Ctrl + C is pressed
    uv run python $ServerScript
}
catch {
    Write-Host "The server has stopped or was interrupted."
}

Write-Host ""
Write-Host "Server script has exited. Goodbye!"