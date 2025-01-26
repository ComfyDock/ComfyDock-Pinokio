#!/usr/bin/env bash
set -e

# ------------------------------------------------------------------------------
# This script does the following:
#  1. Checks that 'apt' is available; if not, throws an error (unsupported distro).
#  2. Checks if Git is installed; if not, installs it using 'apt'.
#  3. Pulls the latest changes from the current repo via 'git pull'.
#  4. Installs 'uv' (which handles Python downloads/venvs) using the official script.
#  5. Creates/activates a virtual environment using 'uv'.
#  6. Installs requirements from requirements.txt using 'uv' if present.
#  7. Runs start_server.py with proper signal handling for Ctrl + C.
# ------------------------------------------------------------------------------

# Get the script's directory and move one level up to the project directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# -----------------------------
# 0. Check if 'apt' is available
# -----------------------------
if ! command -v apt &> /dev/null; then
    echo "❌ 'apt' not found. This script only supports Debian/Ubuntu-based distros."
    exit 1
fi

# -----------------------------
# 1. Check if Git is installed
# -----------------------------
echo
echo "============================="
echo "== 1. Check if Git is installed"
echo "============================="
if ! command -v git &> /dev/null; then
    echo "🚫 Git not found. Installing via apt..."
    sudo apt update
    sudo apt install -y git
    echo "✅ Git installed successfully."
else
    echo "✅ Git is already installed."
fi

# -----------------------------
# 2. Update local repo (git pull)
# -----------------------------
echo
echo "============================="
echo "== 2. Update local repo (git pull)"
echo "============================="
if git rev-parse --is-inside-work-tree &> /dev/null; then
    git pull
    echo "✅ Repository updated successfully."
else
    echo "⚠️  Current directory is not a Git repository. Skipping git pull."
fi

# -----------------------------
# 3. Install uv (Package manager)
# -----------------------------
echo
echo "============================="
echo "== 3. Install uv"
echo "============================="
if ! command -v uv &> /dev/null; then
    echo "🚀 Installing uv using the official install script..."
    /bin/bash -c "$(curl -sSfL https://astral.sh/uv/install.sh)"
    echo "✅ uv installed successfully."
else
    echo "✅ uv is already installed."
fi

# -----------------------------
# 4. Create (or reuse) a uv-based virtual environment
# -----------------------------
echo
echo "============================="
echo "== 4. Create (or reuse) uv-based venv"
echo "============================="

VENV_NAME=".venv"

if [ ! -d "$VENV_NAME" ]; then
    echo "🚀 Creating the virtual environment with uv..."
    # No need to specify a Python version; uv will handle downloads automatically
    uv venv "$VENV_NAME"
    echo "✅ Virtual environment created."
else
    echo "✅ Virtual environment '$VENV_NAME' already exists; reusing it..."
fi

# We'll rely on 'uv' commands (like "uv pip", "uv python") within the venv.

# -----------------------------
# 5. Install requirements (if present)
# -----------------------------
REQ_FILE="requirements.txt"
echo
echo "============================="
echo "== 5. Install requirements"
echo "============================="

if [ -f "$REQ_FILE" ]; then
    echo "📦 Installing dependencies from $REQ_FILE..."
    uv pip install -r "$REQ_FILE"
    echo "✅ Dependencies installed successfully."
else
    echo "⚠️  No $REQ_FILE file found; skipping 'pip install -r $REQ_FILE'."
fi

# -----------------------------
# 6. Run start_server.py with Signal Handling
# -----------------------------
echo
echo "============================="
echo "== 6. Run start_server.py"
echo "============================="

SERVER_SCRIPT="start_server.py"

# Cleanup function to handle Ctrl + C
cleanup() {
    echo
    echo "🛑 Interrupt received. Shutting down the server..."
    if kill -0 "$SERVER_PID" &> /dev/null; then
        kill "$SERVER_PID"
        wait "$SERVER_PID" 2>/dev/null
        echo "✅ Server process (PID: $SERVER_PID) terminated."
    fi
    exit 0
}

if [ -f "$SERVER_SCRIPT" ]; then
    echo "🚀 Starting server..."
    trap cleanup SIGINT SIGTERM

    # Start the server in the background using uv to run Python
    uv run python "$SERVER_SCRIPT" &
    SERVER_PID=$!
    echo "✅ Server started with PID: $SERVER_PID."

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

    by Akatz
EOF

    # Big link banner
    LINK="http://localhost:8000"
    BORDER_LEN=$(( ${#LINK} + 8 ))
    BORDER=$(printf '%*s' "${BORDER_LEN}" | tr ' ' '*')

    # ANSI codes for formatting
    BOLD='\033[1m'
    UNDERLINE='\033[4m'
    GREEN='\033[1;32m'    # Bold Green
    YELLOW='\033[1;33m'   # Bold Yellow
    RED='\033[1;31m'
    CYAN='\033[1;36m'
    MAGENTA='\033[1;35m'
    NC='\033[0m'

    echo
    echo -e "${BOLD}${CYAN}🔥🔥🔥 COMFYUI Environment Manager is running! 🔥🔥🔥${NC}"
    echo -e "${BOLD}${MAGENTA}👇👇👇 Open the link below in your browser! 👇👇👇${NC}"
    echo
    echo -e "${BOLD}${YELLOW}${BORDER}${NC}"
    echo -e "${BOLD}${YELLOW}*   ${GREEN}${UNDERLINE}${LINK}${NC}   ${BOLD}${YELLOW}*${NC}"
    echo -e "${BOLD}${YELLOW}${BORDER}${NC}"
    echo
    echo -e "${BOLD}${RED}⚠️  Press Ctrl + C to terminate the server.${NC}"

    # Keep script running and wait for the server process
    wait "$SERVER_PID"
else
    echo "❌ Could not find $SERVER_SCRIPT. Make sure you're in the correct repo directory."
fi
