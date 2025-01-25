#!/usr/bin/env bash
set -e

# ------------------------------------------------------------------------------
# This script does the following:
#  1. Checks if any Python 3+ version is installed; if not, installs the default Python 3.
#  2. Checks if Git is installed; if not, installs it.
#  3. Pulls the latest changes from the current repo via git pull.
#  4. Installs 'uv' for package management.
#  5. Creates/activates a Python 3 virtualenv (idempotent).
#  6. Installs requirements via requirements.txt
#  7. Runs start_server.py with proper signal handling for graceful termination.
# ------------------------------------------------------------------------------

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

# Function to print section headers
print_section() {
    echo
    echo "============================="
    echo "==  $1"
    echo "============================="
}

# -----------------------------
# 1. Check if any Python 3+ is installed
# -----------------------------
print_section "1. Check if Python 3+ is installed"
PYTHON_CMD=""
PYTHON_VERSION=""

if command -v python3 &> /dev/null; then
    PYTHON_CMD=$(command -v python3)
    PYTHON_VERSION=$($PYTHON_CMD --version | awk '{print $2}')
    echo -e "✅ Found Python version ${GREEN}$PYTHON_VERSION${NC} at ${GREEN}$PYTHON_CMD${NC}."
else
    echo "🚫 Python 3 not found. Installing the default Python 3..."
    sudo apt-get update

    # Install the default Python 3 and necessary packages
    sudo apt-get install -y python3 python3-venv python3-dev python3-distutils curl

    # Verify installation
    if command -v python3 &> /dev/null; then
        PYTHON_CMD=$(command -v python3)
        PYTHON_VERSION=$($PYTHON_CMD --version | awk '{print $2}')
        echo -e "✅ Python 3 installed successfully. Version: ${GREEN}$PYTHON_VERSION${NC}."
    else
        echo "❌ Failed to install Python 3. Please check the errors above."
        exit 1
    fi
fi

# -----------------------------
# 2. Check if Git is installed
# -----------------------------
print_section "2. Check if Git is installed"
if ! command -v git &> /dev/null
then
    echo "🚫 Git not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y git
    echo "✅ Git installed successfully."
else
    echo "✅ Git is already installed."
fi

# -----------------------------
# 3. Update local repo (git pull)
# -----------------------------
print_section "3. Update local repo (git pull)"
if git rev-parse --is-inside-work-tree &> /dev/null; then
    git pull
    echo "✅ Repository updated successfully."
else
    echo "⚠️  Current directory is not a Git repository. Skipping git pull."
fi

# -----------------------------
# 4. Install uv (Python package manager)
# -----------------------------
print_section "4. Install uv (Python package manager)"
# Ensure pip is installed for the detected Python version
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "🚫 pip not found for Python. Installing pip..."
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $PYTHON_CMD get-pip.py --user
    rm get-pip.py
    echo "✅ pip installed successfully."
fi

# Upgrade pip
$PYTHON_CMD -m pip install --upgrade pip

# Install uv
$PYTHON_CMD -m pip install uv
echo "✅ 'uv' installed successfully."

# -----------------------------
# 5. Create (or reuse) a Python 3 virtual environment
# -----------------------------
print_section "5. Create (or reuse) a Python 3 virtual environment"
if [ ! -d "$VENV_NAME" ]; then
    echo "🚀 Creating the virtual environment with uv..."
    $PYTHON_CMD -m uv venv "$VENV_NAME" --python "$PYTHON_CMD"
    echo "✅ Virtual environment created."
else
    echo "✅ Virtual environment '$VENV_NAME' already exists; reusing it..."
fi

echo "🔄 Activating the virtual environment..."
# Activate the virtual environment
# shellcheck disable=SC1091
source "$VENV_NAME/bin/activate"

echo "✅ Using Python version:"
python --version

# -----------------------------
# 6. Install requirements
# -----------------------------
print_section "6. Install requirements"
if [ -f "$REQ_FILE" ]; then
    echo "📦 Installing dependencies from $REQ_FILE..."
    uv pip install -r "$REQ_FILE"
    echo "✅ Dependencies installed successfully."
else
    echo "⚠️  No $REQ_FILE file found; skipping 'pip install -r $REQ_FILE'."
fi

# -----------------------------
# 7. Run start_server.py with Signal Handling
# -----------------------------
print_section "7. Run $SERVER_SCRIPT"

# Function to handle cleanup on exit
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

    # Trap SIGINT and SIGTERM to gracefully shut down the server
    trap cleanup SIGINT SIGTERM

    # Run the server in the background
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

    # Bordered link with enhanced visibility
    LINK="http://localhost:8000"
    BORDER_LEN=$(( ${#LINK} + 8 ))  # Increased padding for emphasis
    BORDER=$(printf '%*s' "${BORDER_LEN}" | tr ' ' '*')

    # ANSI escape codes for colors and formatting
    BOLD='\033[1m'
    UNDERLINE='\033[4m'
    GREEN='\033[1;32m'    # Bold Green
    YELLOW='\033[1;33m'   # Bold Yellow
    RED='\033[1;31m'      # Bold Red
    BLUE='\033[1;34m'     # Bold Blue
    CYAN='\033[1;36m'     # Bold Cyan
    MAGENTA='\033[1;35m'  # Bold Magenta
    NC='\033[0m'           # No Color

    echo
    echo -e "${BOLD}${CYAN}🔥🔥🔥 COMFYUI Environment Manager is running! 🔥🔥🔥${NC}"
    echo -e "${BOLD}${MAGENTA}👇👇👇 Open the link below in your browser! 👇👇👇${NC}"
    echo
    echo -e "${BOLD}${YELLOW}${BORDER}${NC}"
    echo -e "${BOLD}${YELLOW}*   ${GREEN}${UNDERLINE}${LINK}${NC}   ${BOLD}${YELLOW}*${NC}"
    echo -e "${BOLD}${YELLOW}${BORDER}${NC}"
    echo
    echo -e "${BOLD}${RED}⚠️  Press Ctrl + C to terminate the server.${NC}"

    # Wait for the server process to finish
    wait "$SERVER_PID"
else
    echo "❌ Could not find $SERVER_SCRIPT. Make sure you're in the correct repo directory."
fi
