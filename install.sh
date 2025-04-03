#!/bin/bash

# Optional: Define the main branch name
MAIN_BRANCH=$1 # Or "master", etc.

echo "Checking for updates..."

echo "MAIN_BRANCH: $MAIN_BRANCH"

# Fetch the latest changes from the remote repository
echo "Fetching latest changes..."
git fetch origin
if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch updates from remote. Check connection and repository access."
    exit 1
fi

# Check if uv.lock is modified locally
# We want to discard these local changes before pulling.
echo "Checking local uv.lock status..."
# Use 'git status --porcelain uv.lock' to check for modifications
if [[ $(git status --porcelain uv.lock) ]]; then
    echo "Local uv.lock was modified. Resetting it to match the latest remote version..."
    # Discard local changes to uv.lock, resetting it to the version in the remote branch
    # Use 'git checkout' which is generally safe for single files.
    # The syntax is 'git checkout <commit-ish> -- <path>'
    git checkout "origin/${MAIN_BRANCH}" -- uv.lock
    if [ $? -ne 0 ]; then
        echo "Error: Failed to reset local uv.lock. Cannot proceed with update."
        # Optional: More robust approach might try 'git restore' or inform user
        exit 1
    fi
    echo "Local uv.lock reset."
else
    echo "Local uv.lock is clean."
fi

# Now that uv.lock is clean (or reset), attempt to pull/merge changes
echo "Pulling latest code changes..."
# Using 'git pull' which is 'git fetch' + 'git merge'
# It might still fail if the *user* modified *other* tracked files.
git_output=$(git pull origin "${MAIN_BRANCH}" 2>&1)
PULL_STATUS=$?

if [ $PULL_STATUS -ne 0 ]; then
    echo "Failed to pull updates."
    echo "This might be due to local changes you made to other files."
    echo "Please backup your changes, then try 'git stash', run the update again, and finally 'git stash pop'."
    echo "Or commit your changes if they are intentional."
    # A more advanced script could attempt 'git stash push --keep-index' before pull
    # and 'git stash pop' after, but error handling gets complex.
    exit 1
fi

echo "Code update successful."

# Run uv sync AFTER the pull is successful
echo "Synchronizing Python environment..."
uv sync
if [ $? -ne 0 ]; then
    echo "Failed to synchronize Python environment using 'uv sync'."
    # The environment might be inconsistent. User might need to manually fix.
    exit 1
fi

echo "Environment synchronization successful."
echo "Update complete."

exit 0