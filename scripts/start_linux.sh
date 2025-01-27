#!/usr/bin/env bash
set -e

# This script is used to start the server on Linux.

# Get the script's directory and move one level up to the project directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# -----------------------------
# 0. Define some variables
# -----------------------------
VENV_NAME=".venv"
REQ_FILE="requirements.txt"
SERVER_SCRIPT="start_server.py"

echo
echo "-----------------------------"
echo "1. Check if Python 3.12 is installed"
echo "-----------------------------"
if ! command -v python3.12 &> /dev/null
then
    echo "Python 3.12 not found. Installing..."
    sudo apt-get update
    # If python3.12 is not available via your distro's repos, you may need to add a PPA or build from source.
    # For Debian/Ubuntu (22.04+ may have 3.10 or 3.11, so you might need a PPA):
    # sudo add-apt-repository ppa:deadsnakes/ppa -y
    # sudo apt-get update
    sudo apt-get install python3.12 python3.12-venv python3.12-dev -y
else
    echo "Python 3.12 is already installed."
fi

echo
echo "-----------------------------"
echo "2. Check if Git is installed"
echo "-----------------------------"
if ! command -v git &> /dev/null
then
    echo "Git not found. Installing..."
    sudo apt-get update
    sudo apt-get install git -y
else
    echo "Git is already installed."
fi

echo
echo "-----------------------------"
echo "3. Update local repo (git pull)"
echo "-----------------------------"
git pull

echo
echo "-----------------------------"
echo "4. Install uv (Python package manager)"
echo "-----------------------------"
python3.12 -m pip install --upgrade pip
python3.12 -m pip install uv

echo
echo "-----------------------------"
echo "5. Create (or reuse) a Python 3.12 virtual env"
echo "-----------------------------"
if [ ! -d "$VENV_NAME" ]; then
    echo "Creating the venv with uv..."
    uv venv "$VENV_NAME" --python python3.12
else
    echo "Venv $VENV_NAME already exists; reusing it..."
fi

echo "Activating the virtual environment..."
# Activate
# shellcheck disable=SC1091
source "$VENV_NAME/bin/activate"

echo "Using Python version:"
python --version

echo
echo "-----------------------------"
echo "6. Install requirements"
echo "-----------------------------"
if [ -f "$REQ_FILE" ]; then
    echo "Installing from $REQ_FILE..."
    uv pip install -r "$REQ_FILE"
else
    echo "No $REQ_FILE file found; skipping 'pip install -r $REQ_FILE'."
fi

echo
echo "-----------------------------"
echo "7. Run $SERVER_SCRIPT"
echo "-----------------------------"
if [ -f "$SERVER_SCRIPT" ]; then
    echo "Starting server..."
    # We can directly call uv run python here
    uv run python "$SERVER_SCRIPT" &
    SERVER_PID=$!

    # ASCII art banner
    cat << 'EOF'

  ___  __   _  _  ____  _  _  _  _  __    ____  __ _  _  _  __  ____   __   __ _  _  _  ____  __ _  ____ 
 / __)/  \ ( \/ )(  __)( \/ )/ )( \(  )  (  __)(  ( \/ )( \(  )(  _ \ /  \ (  ( \( \/ )(  __)(  ( \(_  _)
( (__(  O )/ \/ \ ) _)  )  / ) \/ ( )(    ) _) /    /\ \/ / )(  )   /(  O )/    // \/ \ ) _) /    /  )(  
 \___)\__/ \_)(_/(__)  (__/  \____/(__)  (____)\_)__) \__/ (__)(__\_) \__/ \_)__)\_)(_/(____)\_)__) (__) 
 _  _   __   __ _   __    ___  ____  ____                                                                
( \/ ) / _\ (  ( \ / _\  / __)(  __)(  _ \                                                               
/ \/ \/    \/    //    \( (_ \ ) _)  )   /                                                               
\_)(_/\_/\_/\_)__)\_/\_/ \___/(____)(__\_)

By Akatz

EOF

    # Bordered link
    LINK="http://localhost:8000"
    BORDER_LEN=$(( ${#LINK} + 8 ))
    BORDER=$(printf '%*s' "${BORDER_LEN}" | tr ' ' '*')

    echo
    echo "$BORDER"
    echo "*   $LINK   *"
    echo "$BORDER"

    echo
    echo "ComfyUI Environment Manager is running! Open the above link in your browser."
    echo "Server process is running in the background (PID: $SERVER_PID)."
else
    echo "Could not find $SERVER_SCRIPT. Make sure you're in the correct repo directory."
fi
