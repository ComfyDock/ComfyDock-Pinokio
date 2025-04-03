import sys
import subprocess
import shlex

# --- Configuration ---
UV_LOCK_FILE = "uv.lock"
# --- End Configuration ---

def run_command(command_list, capture_output=False, check=True, suppress_output=False):
    """
    Runs a command using subprocess and handles basic error checking.

    Args:
        command_list (list): The command and its arguments as a list of strings.
        capture_output (bool): If True, capture stdout and stderr.
        check (bool): If True, raise CalledProcessError if the command returns a non-zero exit code.
        suppress_output (bool): If True, don't print stdout/stderr even on error when check=True.
                                Also suppresses output if capture_output is False.

    Returns:
        subprocess.CompletedProcess: The result object from subprocess.run.

    Raises:
        subprocess.CalledProcessError: If check=True and the command fails.
        FileNotFoundError: If the command executable is not found.
    """
    print(f"Running: {' '.join(shlex.quote(arg) for arg in command_list)}")

    # Determine stdout/stderr settings based on flags
    stdout_setting = None
    stderr_setting = None

    if not capture_output and suppress_output:
        # Only suppress manually if not capturing output
        stdout_setting = subprocess.PIPE
        stderr_setting = subprocess.PIPE

    try:
        # Pass capture_output directly. Don't set stdout/stderr if capture_output is True.
        process = subprocess.run(
            command_list,
            capture_output=capture_output,
            text=True,
            check=False, # Check manually later for better error reporting
            stdout=stdout_setting, # Use None if capture_output=True or if not suppressing
            stderr=stderr_setting, # Use None if capture_output=True or if not suppressing
        )

        # Manual check after execution for more control over error messages
        if check and process.returncode != 0:
             # Reconstruct the exception manually or raise a custom one
             print(f"Error executing command: {' '.join(shlex.quote(arg) for arg in command_list)}")
             print(f"Return code: {process.returncode}")
             # Print captured output if available and not suppressed (or if check failed)
             if process.stdout:
                 print(f"Stdout:\n{process.stdout.strip()}")
             if process.stderr:
                 print(f"Stderr:\n{process.stderr.strip()}")
             # Raise the error to stop execution
             raise subprocess.CalledProcessError(process.returncode, command_list, output=process.stdout, stderr=process.stderr)

        return process
    except FileNotFoundError:
        print(f"Error: Command '{command_list[0]}' not found. Is it installed and in PATH?")
        sys.exit(1)
    # Note: CalledProcessError is now raised manually above if check=True

# --- main() function remains the same as before ---
def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python update_script.py <main-branch-name>")
        print("Example: python update_script.py main")
        sys.exit(1)

    main_branch = sys.argv[1]
    print(f"Target Branch: {main_branch}")
    print("-" * 20)

    # 1. Git Fetch
    print("Fetching latest changes...")
    try:
        # Use check=True here, as fetch should succeed
        run_command(["git", "fetch", "origin"], check=True)
    except subprocess.CalledProcessError:
        print("\nError: Failed to fetch updates from remote.")
        print("Check your internet connection and repository access rights.")
        sys.exit(1)
    print("Fetch successful.")
    print("-" * 20)

    # 2. Check uv.lock status
    print(f"Checking local status of '{UV_LOCK_FILE}'...")
    try:
        # Run 'git status' - capture output, don't fail on non-zero exit code itself
        status_result = run_command(
            ["git", "status", "--porcelain", UV_LOCK_FILE],
            capture_output=True,
            check=False # Output presence indicates modification, not exit code
        )

        # Check if stdout is not empty, indicating changes (M, A, ??, etc.)
        if status_result.stdout and status_result.stdout.strip():
            print(f"Local '{UV_LOCK_FILE}' was modified or is not clean.")
            print(f"Resetting '{UV_LOCK_FILE}' to match 'origin/{main_branch}'...")
            try:
                # Now run checkout, this time we expect success (check=True)
                run_command(["git", "checkout", f"origin/{main_branch}", "--", UV_LOCK_FILE], check=True)
                print(f"Local '{UV_LOCK_FILE}' reset successfully.")
            except subprocess.CalledProcessError:
                # Error during checkout
                print(f"\nError: Failed to reset '{UV_LOCK_FILE}'.")
                print("Cannot proceed with update while this file has uncommitted changes.")
                sys.exit(1)
        else:
            print(f"Local '{UV_LOCK_FILE}' is clean.")

    except subprocess.CalledProcessError:
        # This might happen if 'git status' itself failed unexpectedly (e.g. not a git repo)
        # Error message is printed by run_command's manual check now
        print("\nError checking git status.") # Add context
        sys.exit(1)
    except Exception as e:
         # Catch other potential errors during status check
         print(f"\nAn unexpected error occurred during git status check: {e}")
         sys.exit(1)
    print("-" * 20)

    # 3. Git Pull
    print("Pulling latest code changes...")
    try:
        # Run pull without check=True initially to provide specific guidance on failure
        pull_result = run_command(
            ["git", "pull", "origin", main_branch],
            capture_output=True, # Capture output to show user if needed
            check=False # Handle non-zero exit code manually below
        )

        if pull_result.returncode != 0:
            print("\nError: Failed to pull updates.")
            print("-" * 10 + " Git Output " + "-" * 10)
            if pull_result.stdout: print(pull_result.stdout.strip())
            if pull_result.stderr: print(pull_result.stderr.strip())
            print("-" * 32)
            print("This might be due to local changes you made to other tracked files")
            print("or unresolved merge conflicts.")
            print("\nPlease backup your changes, then consider:")
            print("  1. Stashing your changes: 'git stash push -m \"Update backup\"'")
            print("  2. Running this update script again.")
            print("  3. Restoring your changes (if needed): 'git stash pop'")
            print("\nAlternatively, commit your local changes if they are intentional.")
            sys.exit(1)
        else:
            # Print stdout from pull if successful (usually shows updated files)
            if pull_result.stdout:
                 print("Git Pull Output:\n" + pull_result.stdout.strip())
            print("Code update successful.")

    except Exception as e:
         # Catch other potential errors during pull
         print(f"\nAn unexpected error occurred during git pull: {e}")
         sys.exit(1)
    print("-" * 20)

    # 4. UV Sync
    # Note: Consider adding '--frozen' here if desired: ["uv", "sync", "--frozen"]
    print("Synchronizing Python environment with uv...")
    try:
        # Use check=True as we expect uv sync to succeed normally
        run_command(["uv", "sync"], check=True)
        print("Environment synchronization successful.")
    except subprocess.CalledProcessError:
        print("\nError: Failed to synchronize Python environment using 'uv sync'.")
        print("The environment might be incomplete or inconsistent.")
        print("Check the output above for specific uv errors.")
        sys.exit(1)
    except Exception as e:
         # Catch other potential errors during sync
         print(f"\nAn unexpected error occurred during uv sync: {e}")
         sys.exit(1)

    print("-" * 20)

    print("Update complete!")
    sys.exit(0)


if __name__ == "__main__":
    run_command(["git", "--version"])
    run_command(["git", "config", "--list", "--show-origin"])
    main()