from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbolauncher.command_builder import build_command_args
from turbolauncher.core import LauncherCore
from turbolauncher.settings import DEFAULT_SETTINGS


class PathSandbox:
    def __init__(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.app_dir = self.root / "app"
        self.session_dir = self.root / "session"
        self.presets_dir = self.app_dir / "presets"
        self.model_configs_dir = self.app_dir / "model-configs"
        self.registry_file = self.app_dir / "models.registry"
        self.runtime_path_file = self.session_dir / "runtime_path.txt"
        self.session_file = self.session_dir / "session.json"
        self.model_library_file = self.session_dir / "model_library.json"
        self.log_file = self.session_dir / "launcher.log"
        self.hf_cache_dir = self.root / "hf_download"

    def cleanup(self) -> None:
        self._tempdir.cleanup()

    def patchers(self):
        import turbolauncher.core as core_module
        import turbolauncher.paths as paths_module

        patches = [
            patch.object(core_module, "APP_DIR", self.app_dir),
            patch.object(core_module, "PRESETS_DIR", self.presets_dir),
            patch.object(core_module, "REGISTRY_FILE", self.registry_file),
            patch.object(core_module, "RUNTIME_PATH_FILE", self.runtime_path_file),
            patch.object(core_module, "SESSION_FILE", self.session_file),
            patch.object(core_module, "MODEL_LIBRARY_FILE", self.model_library_file),
            patch.object(core_module, "HF_CACHE_DIR", self.hf_cache_dir),
            patch.object(paths_module, "APP_DIR", self.app_dir),
            patch.object(paths_module, "PRESETS_DIR", self.presets_dir),
            patch.object(paths_module, "MODEL_CONFIGS_DIR", self.model_configs_dir),
            patch.object(paths_module, "SESSION_DIR", self.session_dir),
            patch.object(paths_module, "SESSION_FILE", self.session_file),
            patch.object(paths_module, "RUNTIME_PATH_FILE", self.runtime_path_file),
            patch.object(paths_module, "MODEL_LIBRARY_FILE", self.model_library_file),
            patch.object(paths_module, "LOG_FILE", self.log_file),
            patch.object(paths_module, "HF_CACHE_DIR", self.hf_cache_dir),
        ]
        return patches


class LauncherCoreRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = PathSandbox()
        self._patchers = self.sandbox.patchers()
        for patcher in self._patchers:
            patcher.start()
        self.addCleanup(self._stop_patchers)
        self.addCleanup(self.sandbox.cleanup)

    def _stop_patchers(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()

    def test_save_and_load_custom_preset_round_trip(self) -> None:
        core = LauncherCore()
        settings = dict(DEFAULT_SETTINGS)
        settings["CtxSize"] = 32768
        settings["Alias"] = "test_alias"

        saved_path = core.save_preset("QA Preset", "round-trip", settings)
        loaded = core.load_preset("QA Preset")
        presets = core.list_presets()

        self.assertEqual(saved_path, self.sandbox.presets_dir / "QA-Preset.json")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["Name"], "QA Preset")
        self.assertEqual(loaded["Settings"]["CtxSize"], 32768)
        self.assertEqual(loaded["Settings"]["Alias"], "test_alias")
        self.assertFalse(loaded["IsBuiltIn"])
        self.assertIn("QA Preset", [preset["Name"] for preset in presets])

    def test_save_session_writes_legacy_and_nested_keys(self) -> None:
        core = LauncherCore()
        settings = dict(DEFAULT_SETTINGS)
        settings["Threads"] = 24

        core.save_session("Agentic AI", "D:/models/demo.gguf", settings)
        loaded = core.load_session()

        self.assertEqual(loaded["LastPreset"], "Agentic AI")
        self.assertEqual(loaded["PresetName"], "Agentic AI")
        self.assertEqual(loaded["LastModel"], "D:/models/demo.gguf")
        self.assertEqual(loaded["ModelPath"], "D:/models/demo.gguf")
        self.assertEqual(loaded["Threads"], 24)
        self.assertEqual(loaded["Settings"]["Threads"], 24)
        self.assertIn("SavedAt", loaded)


class CommandBuilderRegressionTests(unittest.TestCase):
    def test_build_command_args_keeps_expected_flags(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        settings.update(
            {
                "FlashAttn": True,
                "Thinking": False,
                "Webui": False,
                "Parallel": 3,
                "Alias": "demo_alias",
                "ApiKey": "secret",
                "Mlock": True,
                "NoMmap": True,
                "TensorSplit": 12.5,
                "SplitMode": "layer",
                "DryMultiplier": 0.8,
                "XtcProb": 0.2,
                "Seed": 7,
            }
        )

        args = build_command_args("D:/models/demo.gguf", settings)

        self.assertEqual(args["model"], "D:/models/demo.gguf")
        self.assertEqual(args["flash-attn"], "on")
        self.assertEqual(args["reasoning-format"], "none")
        self.assertTrue(args["mlock"])
        self.assertTrue(args["no-mmap"])
        self.assertEqual(args["split-mode"], "layer")
        self.assertEqual(args["tensor-split"], 12.5)
        self.assertEqual(args["parallel"], 3)
        self.assertEqual(args["alias"], "demo_alias")
        self.assertEqual(args["api-key"], "secret")
        self.assertTrue(args["no-webui"])
        self.assertEqual(args["dry-multiplier"], 0.8)
        self.assertEqual(args["dry-penalty-last-n"], -1)
        self.assertEqual(args["xtc-probability"], 0.2)
        self.assertEqual(args["xtc-threshold"], 0.5)
        self.assertEqual(args["seed"], 7)

    def test_build_command_args_can_explicitly_disable_flash_attn(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        settings["FlashAttn"] = False

        args = build_command_args("D:/models/demo.gguf", settings)

        self.assertEqual(args["flash-attn"], "off")


if __name__ == "__main__":
    unittest.main()
