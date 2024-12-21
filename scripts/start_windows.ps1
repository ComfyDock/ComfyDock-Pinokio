<#
.SYNOPSIS
  Bootstrap script to set up Python 3.12, Git, update repo, create
  a virtual environment, install dependencies, and run start_server.py.

.DESCRIPTION
  1. Checks if python is available, if not installs Python 3.12.
  2. Checks if git is available, if not installs git.
  3. Update local repo if not already
  4. Installs uv for package management.
  5. Creates/activates a Python 3.12 virtual env (idempotent).
  6. Installs required packages
  7. runs start_server.py.

#>

# Get the script's directory and set the working directory to the project directory
$scriptPath = $MyInvocation.MyCommand.Path
$scriptDir = Split-Path -Parent $scriptPath
$projectDir = Split-Path -Parent $scriptDir
Set-Location -Path $projectDir

# -----------------------------
# 0. Define some variables
# -----------------------------
$PythonInstallerUrl = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe" 
# Adjust the Python version/URL above as needed

$GitInstallerUrl = "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.2/Git-2.44.0-64-bit.exe"
# Adjust Git version/URL above as needed

$VenvName = "venv"                                         # Name for the Python virtual env
$ReqFile  = "requirements.txt"                             # Path to your requirements file
$ServerScript = "start_server.py"                          # Server start script

# -----------------------------
# 1. Check if Python is installed
# -----------------------------
Write-Host "`nChecking for Python..."
$pythonCheck = (Get-Command python -ErrorAction SilentlyContinue)

if (!$pythonCheck) {
    Write-Host "Python not found. Installing Python..."

    # Download Python installer
    Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile "python-installer.exe"

    # Silent install (requires admin privileges)
    Start-Process -FilePath ".\python-installer.exe" -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait

    # Optional: remove installer after install
    # Remove-Item ".\python-installer.exe"

    # Let the user know they might need to open a new PowerShell for the PATH to update
    Write-Host "`nPython installation finished. You may need to open a new PowerShell session if 'python' isn't recognized."
}
else {
    Write-Host "Python is already installed."
}

# -----------------------------
# 2. Check if Git is installed
# -----------------------------
Write-Host "`nChecking for Git..."
$gitCheck = (Get-Command git -ErrorAction SilentlyContinue)

if (!$gitCheck) {
    Write-Host "Git not found. Installing Git..."

    # Download Git installer
    Invoke-WebRequest -Uri $GitInstallerUrl -OutFile "git-installer.exe"

    # Silent install
    Start-Process -FilePath ".\git-installer.exe" -ArgumentList "/VERYSILENT" -Wait

    # Optional: remove installer after install
    # Remove-Item ".\git-installer.exe"

    Write-Host "`nGit installation finished. You may need to open a new PowerShell session if 'git' isn't recognized."
}
else {
    Write-Host "Git is already installed."
}

# -----------------------------
# 3. Update local repo
# -----------------------------
Write-Host "`nPulling latest changes..."
git pull

# -----------------------------
# 4. Install uv
# -----------------------------
Write-Host "`nInstalling uv package manager..."
python -m pip install --upgrade pip
python -m pip install uv

# ------------------------------------
# 5. Create a Python 3.12 venv (idempotent)
# ------------------------------------
Write-Host "`nCreating or re-using a Python 3.12 venv..."

# create venv if doesn't exist
if (!(Test-Path $VenvName)) {
    uv venv --python 3.12.0
}

# Activate the environment
# Note: For PowerShell, you typically do: .\venv\Scripts\Activate.ps1
#       For cmd.exe, do: .\venv\Scripts\activate.bat
Write-Host "Activating virtual environment..."
. ".\$VenvName\Scripts\Activate.ps1"

Write-Host "Using Python version:"
uv run python --version

# -----------------------------
# 6. Install requirements
# -----------------------------
if (Test-Path $ReqFile) {
    Write-Host "`nInstalling requirements from $ReqFile..."
    uv pip install -r $ReqFile
}
else {
    Write-Host "`nNo $ReqFile file found; skipping 'pip install -r $ReqFile'."
}

# -----------------------------
# 7. Run start_server.py
# -----------------------------
if (Test-Path $ServerScript) {
    Write-Host "`nStarting server..."

    # Use cmd.exe to run "uv run python start_server.py"
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c uv run python $ServerScript" `
        -NoNewWindow `
        -PassThru | Out-Null

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

    # Notify the user with a bordered link
    $link = "http://localhost:8000"
    $borderLength = $link.Length + 8
    $border = '*' * $borderLength

    Write-Host "`n$border" -ForegroundColor Green
    Write-Host "*   $link   *" -ForegroundColor Green
    Write-Host "$border" -ForegroundColor Green

    Write-Host "`nComfyUI Environment Manager is running! Open the above link in your browser."
}
else {
    Write-Host "`nCould not find $ServerScript. Make sure you're in the correct repo directory."
}