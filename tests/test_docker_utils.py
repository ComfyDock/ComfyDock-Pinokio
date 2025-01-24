import os
import shutil
import tempfile
import unittest
from pathlib import Path
import tarfile  # in case it’s needed
from unittest.mock import patch, MagicMock

# Run all tests with:
# python -m unittest discover -s tests

# Import our functions from our module
from utils.docker_utils import (
    convert_old_to_new_style,
    _create_mounts_from_new_config,
    create_mounts,
    copy_directories_to_container,
    install_custom_nodes,
    CONTAINER_COMFYUI_PATH
)
from docker.types import Mount

# A dummy container that simulates a Docker container's basic behavior
class DummyContainer:
    def exec_run(self, cmd):
        # Simply print out the command for diagnostic purposes.
        print(f"DummyContainer.exec_run called with: {cmd}")
        return

    def put_archive(self, container_path, tar_data):
        # Simulate a successful put_archive call.
        print(f"DummyContainer.put_archive called for container_path: {container_path}")
        return True


class TestMountConversion(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory to simulate comfyui_path
        self.temp_dir = tempfile.mkdtemp()
        self.comfyui_path = Path(self.temp_dir)
        # Pre-create directories for the old-style test config
        (self.comfyui_path / "user").mkdir()
        (self.comfyui_path / "models").mkdir()
        (self.comfyui_path / "output").mkdir()
        (self.comfyui_path / "input").mkdir()

    def tearDown(self):
        # Clean up the temporary directory after each test
        shutil.rmtree(self.temp_dir)

    def test_convert_old_to_new_style(self):
        old_config = {
            "user": "mount",
            "models": "mount",
            "output": "mount",
            "input": "mount",
            "ignore_this": "skip"  # Not "mount", should be ignored.
        }
        new_config = convert_old_to_new_style(old_config, self.comfyui_path)
        self.assertIn("mounts", new_config)
        # We expect four entries
        self.assertEqual(len(new_config["mounts"]), 4)

        # Create a set of keys from the converted container paths
        container_paths = {m["container_path"] for m in new_config["mounts"]}
        expected_container_paths = {
            f"{CONTAINER_COMFYUI_PATH}/user",
            f"{CONTAINER_COMFYUI_PATH}/models",
            f"{CONTAINER_COMFYUI_PATH}/output",
            f"{CONTAINER_COMFYUI_PATH}/input"
        }
        self.assertEqual(container_paths, expected_container_paths)

        # Check that for each, host_path is comfyui_path/<key>
        for m in new_config["mounts"]:
            key = Path(m["host_path"]).name
            expected_host = (self.comfyui_path / key).resolve().as_posix()
            self.assertEqual(m["host_path"], expected_host)
            self.assertEqual(m["type"], "mount")
            self.assertFalse(m["read_only"])

    def test_create_mounts_from_new_config_with_relative_host_path(self):
        # New style config with relative host_path
        new_config = {
            "mounts": [
                {
                    "container_path": f"{CONTAINER_COMFYUI_PATH}/models",
                    "host_path": "custom_models",  # relative path
                    "type": "mount",
                    "read_only": False
                }
            ]
        }
        target_dir = self.comfyui_path / "custom_models"
        self.assertFalse(target_dir.exists())

        mounts = _create_mounts_from_new_config(new_config, self.comfyui_path)
        # Filter the mounts to the one we created for models
        test_mounts = [m for m in mounts if m["Target"] == f"{CONTAINER_COMFYUI_PATH}/models"]

        self.assertEqual(len(test_mounts), 1)
        mount_obj = test_mounts[0]
        expected_source = str(target_dir.resolve())
        self.assertEqual(mount_obj["Source"], expected_source)
        self.assertEqual(mount_obj["Target"], f"{CONTAINER_COMFYUI_PATH}/models")
        self.assertEqual(mount_obj["Type"], "bind")
        self.assertFalse(mount_obj["ReadOnly"])
        # Verify that the directory was created
        self.assertTrue(target_dir.exists())

    def test_create_mounts_from_new_config_with_absolute_host_path(self):
        # Create an absolute temporary directory for testing
        abs_temp_dir = tempfile.mkdtemp()
        try:
            new_config = {
                "mounts": [
                    {
                        "container_path": f"{CONTAINER_COMFYUI_PATH}/models",
                        "host_path": abs_temp_dir,  # absolute path
                        "type": "mount",
                        "read_only": True
                    }
                ]
            }
            mounts = _create_mounts_from_new_config(new_config, self.comfyui_path)
            test_mounts = [m for m in mounts if m["Target"] == f"{CONTAINER_COMFYUI_PATH}/models"]
            self.assertEqual(len(test_mounts), 1)
            mount_obj = test_mounts[0]
            expected_source = str(Path(abs_temp_dir).resolve())
            self.assertEqual(mount_obj["Source"], expected_source)
            self.assertEqual(mount_obj["Target"], f"{CONTAINER_COMFYUI_PATH}/models")
            self.assertEqual(mount_obj["Type"], "bind")
            self.assertTrue(mount_obj["ReadOnly"])
        finally:
            shutil.rmtree(abs_temp_dir)
            
    def test_create_mounts_from_new_config_with_posix_style_absolute_path(self):
        """
        Verifies that a POSIX-style absolute path (e.g. /tmp/custom_models) is
        handled correctly on Windows (or any OS).
        """
        posix_abs_path = "/tmp/custom_models"

        new_config = {
            "mounts": [
                {
                    "container_path": f"{CONTAINER_COMFYUI_PATH}/models",
                    "host_path": posix_abs_path,  # POSIX-style absolute path
                    "type": "mount",
                    "read_only": True
                }
            ]
        }

        mounts = _create_mounts_from_new_config(new_config, self.comfyui_path)
        # Filter the mount for our container path
        test_mounts = [m for m in mounts if m["Target"] == f"{CONTAINER_COMFYUI_PATH}/models"]

        self.assertEqual(len(test_mounts), 1)
        mount_obj = test_mounts[0]

        # On Windows, Path("/tmp/custom_models") is considered absolute, so it shouldn't
        # get joined to comfyui_path. Instead, you should see something like "C:\\tmp\\custom_models"
        # for mount_obj["Source"], if you're on Windows, or "/tmp/custom_models" if on Linux/macOS.
        # We'll just check that it ends with "tmp/custom_models" for cross-platform consistency.
        self.assertTrue(mount_obj["Source"].replace("\\", "/").endswith("tmp/custom_models"))

        self.assertEqual(mount_obj["Target"], f"{CONTAINER_COMFYUI_PATH}/models")
        self.assertEqual(mount_obj["Type"], "bind")
        self.assertTrue(mount_obj["ReadOnly"])

        # Additionally, verify that the directory actually got created.
        # This will exist at something like C:/tmp/custom_models on Windows or /tmp/custom_models on *nix
        source_path = Path(mount_obj["Source"])
        self.assertTrue(source_path.exists())
        
        # Cleanup: remove it now that we're done
        shutil.rmtree(source_path, ignore_errors=True)

    def test_create_mounts_backwards_compatibility(self):
        # Test create_mounts with an old style config.
        old_config = {
            "user": "mount",
            "models": "mount",
            "output": "mount",
            "input": "mount",
            "skip_me": "ignore"
        }
        mounts = create_mounts(old_config, self.comfyui_path)
        # Excluding any extra mount (e.g. for /usr/lib/wsl),
        # we should have exactly 4 mounts (the ones starting with CONTAINER_COMFYUI_PATH)
        test_mounts = [m for m in mounts if m["Target"].startswith(CONTAINER_COMFYUI_PATH)]
        self.assertEqual(len(test_mounts), 4)

        expected_targets = {
            f"{CONTAINER_COMFYUI_PATH}/user",
            f"{CONTAINER_COMFYUI_PATH}/models",
            f"{CONTAINER_COMFYUI_PATH}/output",
            f"{CONTAINER_COMFYUI_PATH}/input",
        }
        actual_targets = {m["Target"] for m in test_mounts}
        self.assertEqual(expected_targets, actual_targets)


class TestCopyDirectoriesToContainer(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory that serves as comfyui_path for tests
        self.temp_dir = tempfile.mkdtemp()
        self.comfyui_path = Path(self.temp_dir)
        # Create a couple of directories that may be used in tests
        (self.comfyui_path / "custom_models").mkdir(exist_ok=True)
        (self.comfyui_path / "user").mkdir(exist_ok=True)
        (self.comfyui_path / "models").mkdir(exist_ok=True)
        # Create a dummy container instance
        self.dummy_container = DummyContainer()
        # Patch the Docker client to return our dummy container
        patcher = patch("utils.docker_utils.client.containers.get", return_value=self.dummy_container)
        self.addCleanup(patcher.stop)
        self.mock_get = patcher.start()
        # Patch install_custom_nodes to simply record calls and avoid side effects.
        self.install_nodes_patch = patch("utils.docker_utils.install_custom_nodes", return_value=None)
        self.addCleanup(self.install_nodes_patch.stop)
        self.mock_install_nodes = self.install_nodes_patch.start()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_copy_new_config_copy_action(self):
        """
        Test a new-style mount config that uses a 'copy' action.
        The host_path is relative so it should resolve against comfyui_path.
        """
        new_config = {
            "mounts": [
                {
                    "container_path": f"{CONTAINER_COMFYUI_PATH}/models",
                    "host_path": "custom_models",
                    "type": "copy",
                    "read_only": False
                }
            ]
        }
        installed = copy_directories_to_container("dummy_container_id", self.comfyui_path, new_config)
        # For the 'models' key the custom_nodes installer should NOT be triggered.
        self.assertFalse(installed)
        # The directory should exist (it was created in setUp)
        self.assertTrue((self.comfyui_path / "custom_models").exists())

    def test_copy_old_config_copy_and_mount_actions(self):
        """
        Test the old-style configuration with both 'copy' and 'mount' actions.
        In the old style the keys are mapped automatically.
        """
        # First, test an old style config with 'copy' on models and 'mount' on user.
        old_config = {
            "models": "copy",
            "user": "mount"
        }
        installed = copy_directories_to_container("dummy_container_id", self.comfyui_path, old_config)
        # "models" is not custom_nodes so installed should be False
        self.assertFalse(installed)

        # Now, test custom_nodes with the copy action.
        old_config_custom = {
            "custom_nodes": "copy"
        }
        installed_custom = copy_directories_to_container("dummy_container_id", self.comfyui_path, old_config_custom)
        # When processing custom_nodes, our helper _process_copy_mount should trigger install_custom_nodes.
        self.assertTrue(installed_custom)
        # Verify that install_custom_nodes was indeed called.
        self.mock_install_nodes.assert_called()

    def test_copy_new_config_mount_action_custom_nodes(self):
        """
        Test a new-style configuration that uses a 'mount' action on a custom_nodes directory.
        In this case the copy_directories_to_container function should trigger install_custom_nodes.
        """
        new_config = {
            "mounts": [
                {
                    "container_path": f"{CONTAINER_COMFYUI_PATH}/custom_nodes",
                    "host_path": "custom_models",
                    "type": "mount",
                    "read_only": False
                }
            ]
        }
        installed = copy_directories_to_container("dummy_container_id", self.comfyui_path, new_config)
        self.assertTrue(installed)
        self.mock_install_nodes.assert_called()

if __name__ == "__main__":
    unittest.main()
