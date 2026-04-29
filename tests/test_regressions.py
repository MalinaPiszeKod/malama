from __future__ import annotations

import tempfile
import unittest
from subprocess import TimeoutExpired
from pathlib import Path
from unittest.mock import Mock, patch
import os

from turbolauncher.chat import (
    ChatMessage,
    build_base_url,
    get_model_id,
    stream_chat_completion,
    stream_chat_events,
)
from turbolauncher.command_builder import build_command_args
from turbolauncher.command_backends import BACKEND_COMMAND_RULES
from turbolauncher.core import LauncherCore
from turbolauncher.monitoring import parse_prometheus_metrics, parse_slots_status
from turbolauncher.settings import DEFAULT_SETTINGS
from turbolauncher.services.launcher_service import (
    LaunchRequest,
    LauncherService,
    RunningProcess,
)
from turbolauncher.services.monitoring_service import MonitoringService


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
            patch.object(core_module, "MODEL_CONFIGS_DIR", self.model_configs_dir),
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

    def test_resolve_model_entry_loads_chat_fields_from_cfg(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "demo.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "demo.cfg"
        cfg_path.write_text(
            "MODEL_PATH = ../models/demo.gguf\n"
            "ALIAS = Demo Alias\n"
            "CHAT_SYS_PROMPT = System prompt\n"
            "PROMPT_TEMPLATE = Template fallback\n",
            encoding="utf-8",
        )

        entry = core.resolve_model_entry("ignored", cfg_path)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.path, model_path.resolve())
        self.assertEqual(entry.alias, "Demo Alias")
        self.assertEqual(entry.config_path, cfg_path.resolve())
        self.assertEqual(entry.sys_prompt, "System prompt")
        self.assertEqual(entry.chat_template, "Template fallback")
        self.assertIsNone(entry.transformer_layers)
        self.assertIsNone(entry.output_layer)
        self.assertIsNone(entry.full_offload_layers)

    def test_resolve_model_entry_uses_full_offload_layers_override(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "override.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "override.cfg"
        cfg_path.write_text(
            "MODEL_PATH = ../models/override.gguf\n"
            "FULL_OFFLOAD_LAYERS = 99\nTRANSFORMER_LAYERS = 12\nOUTPUT_LAYER = off\n",
            encoding="utf-8",
        )

        entry = core.resolve_model_entry("ignored", cfg_path)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.full_offload_layers, 99)
        self.assertEqual(entry.transformer_layers, 12)
        self.assertFalse(entry.output_layer)

    def test_resolve_model_entry_computes_full_offload_layers_with_output_on(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "computed-on.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "computed-on.cfg"
        cfg_path.write_text(
            "MODEL_PATH = ../models/computed-on.gguf\n"
            "TRANSFORMER_LAYERS = 40\nOUTPUT_LAYER = on\n",
            encoding="utf-8",
        )

        entry = core.resolve_model_entry("ignored", cfg_path)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.transformer_layers, 40)
        self.assertTrue(entry.output_layer)
        self.assertEqual(entry.full_offload_layers, 41)

    def test_resolve_model_entry_defaults_output_layer_on_when_unspecified(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "computed-default.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "computed-default.cfg"
        cfg_path.write_text(
            "MODEL_PATH = ../models/computed-default.gguf\n"
            "TRANSFORMER_LAYERS = 40\n",
            encoding="utf-8",
        )

        entry = core.resolve_model_entry("ignored", cfg_path)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.transformer_layers, 40)
        self.assertIsNone(entry.output_layer)
        self.assertEqual(entry.full_offload_layers, 41)

    def test_resolve_model_entry_computes_full_offload_layers_with_output_off(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "computed-off.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "computed-off.cfg"
        cfg_path.write_text(
            "MODEL_PATH = ../models/computed-off.gguf\n"
            "TRANSFORMER_LAYERS = 40\nOUTPUT_LAYER = off\n",
            encoding="utf-8",
        )

        entry = core.resolve_model_entry("ignored", cfg_path)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.transformer_layers, 40)
        self.assertFalse(entry.output_layer)
        self.assertEqual(entry.full_offload_layers, 40)

    def test_resolve_model_entry_leaves_unknown_offload_metadata_none(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "unknown.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "unknown.cfg"
        cfg_path.write_text(
            "MODEL_PATH = ../models/unknown.gguf\nCHAT_SYS_PROMPT = System prompt\n",
            encoding="utf-8",
        )

        entry = core.resolve_model_entry("ignored", cfg_path)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertIsNone(entry.transformer_layers)
        self.assertIsNone(entry.output_layer)
        self.assertIsNone(entry.full_offload_layers)

    def test_load_models_with_report_applies_sidecar_cfg(self) -> None:
        core = LauncherCore()
        model_dir = self.sandbox.app_dir / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.model_configs_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "demo.gguf"
        model_path.write_text("demo", encoding="utf-8")
        cfg_path = self.sandbox.model_configs_dir / "demo.cfg"
        cfg_path.write_text(
            "CHAT_SYS_PROMPT = System prompt\nCHAT_TEMPLATE = Template text\n",
            encoding="utf-8",
        )

        core.save_model_source_dirs([model_dir])
        models, report = core.load_models_with_report()

        self.assertTrue(any("Found 1 GGUF file(s)" in line for line in report))
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].config_path, cfg_path.resolve())
        self.assertEqual(models[0].sys_prompt, "System prompt")
        self.assertEqual(models[0].chat_template, "Template text")


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
        self.assertEqual(args["n-cpu-moe"], 28)
        self.assertNotIn("cpu-moe", args)
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

    def test_build_command_args_omits_moe_flags_when_disabled(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        settings["NcpuMoe"] = 0

        args = build_command_args("D:/models/demo.gguf", settings)

        self.assertNotIn("n-cpu-moe", args)
        self.assertNotIn("cpu-moe", args)

    def test_build_command_args_applies_backend_specific_rules(self) -> None:
        def add_backend_flag(args, settings) -> None:
            args["fork-flag"] = "enabled"

        settings = dict(DEFAULT_SETTINGS)
        with patch.dict(BACKEND_COMMAND_RULES, {"example-fork": (add_backend_flag,)}, clear=False):
            args = build_command_args("D:/models/demo.gguf", settings, backend="example-fork")

        self.assertEqual(args["fork-flag"], "enabled")


class ModelSourceDefaultsRegressionTests(unittest.TestCase):
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

    def test_default_model_source_dirs_accepts_env_override(self) -> None:
        with patch.dict(os.environ, {"TURBOLAUNCHER_MODEL_SOURCE_DIRS": str(self.sandbox.root / "custom")}, clear=False):
            core = LauncherCore()
            defaults = core.default_model_source_dirs()

        self.assertEqual(defaults[0], self.sandbox.root / "custom")


class LauncherServiceRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = LauncherService()

    def test_redacts_api_key_in_command_text(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        settings["ApiKey"] = "super-secret"
        request = LaunchRequest(
            executable_path=Path(r"C:\Program Files\Turbo Launcher\llama-server.exe"),
            model_path=Path(r"D:\Models\demo model.gguf"),
            settings=settings,
        )

        command = self.service.build_launch_command(request)

        self.assertIn("--api-key ***", command.redacted_command_text)
        self.assertNotIn("super-secret", command.redacted_command_text)
        self.assertIn("super-secret", command.command_text)

    def test_command_text_quotes_windows_paths_with_spaces(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        request = LaunchRequest(
            executable_path=Path(r"C:\Program Files\Turbo Launcher\llama-server.exe"),
            model_path=Path(r"D:\AI Models\demo model.gguf"),
            settings=settings,
        )

        command = self.service.build_launch_command(request)

        self.assertIn('"C:\\Program Files\\Turbo Launcher\\llama-server.exe"', command.command_text)
        self.assertIn('"D:\\AI Models\\demo model.gguf"', command.command_text)

    def test_invalid_paths_raise_service_layer_errors(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        request = LaunchRequest(
            executable_path=Path(r"C:\missing\llama-server.exe"),
            model_path=Path(r"D:\missing\model.gguf"),
            settings=settings,
        )

        with self.assertRaises(FileNotFoundError):
            self.service.validate_launch_request(request)

    def test_invalid_launch_settings_raise_value_error(self) -> None:
        settings = dict(DEFAULT_SETTINGS)
        settings["Port"] = 0
        request = LaunchRequest(
            executable_path=Path(r"C:\Program Files\Turbo Launcher\llama-server.exe"),
            model_path=Path(r"D:\Models\demo.gguf"),
            settings=settings,
        )

        with self.assertRaises(ValueError):
            self.service.build_launch_args(request)

    def test_stop_process_uses_kill_fallback_after_timeout(self) -> None:
        process = Mock()
        process.wait.side_effect = [TimeoutExpired(cmd="x", timeout=3), None]
        running = RunningProcess(
            process=process,
            request=LaunchRequest(
                executable_path=Path(r"C:\Program Files\Turbo Launcher\llama-server.exe"),
                model_path=Path(r"D:\Models\demo.gguf"),
                settings=dict(DEFAULT_SETTINGS),
            ),
            command=Mock(),
        )

        self.service.stop_process(running)

        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)


class MonitoringServiceRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MonitoringService()

    def test_collect_monitoring_snapshot_merges_server_and_slot_metrics(self) -> None:
        metrics_payload = (
            "llamacpp:prompt_tokens_total 12\n"
            "llamacpp:tokens_predicted_total 34\n"
            "llamacpp:prompt_seconds_total 1.2\n"
            "llamacpp:tokens_predicted_seconds_total 3.4\n"
            "llamacpp:prompt_tokens_seconds 10.0\n"
            "llamacpp:predicted_tokens_seconds 20.0\n"
            "llamacpp:kv_cache_usage_ratio 0.5\n"
            "llamacpp:kv_cache_tokens 128\n"
            "llamacpp:n_tokens_max 4096\n"
            "llamacpp:requests_processing 2\n"
            "llamacpp:requests_deferred 1\n"
        )
        slot_payload = (
            '{"slots":[{"id":7,"id_task":11,"n_ctx":2048,"is_processing":true,'
            '"next_token":{"n_decoded":5,"n_remain":15,"has_next_token":true}}]}'
        )

        class Response:
            def __init__(self, payload: str) -> None:
                self.payload = payload

            def __enter__(self) -> Response:
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return self.payload.encode("utf-8")

        def fake_urlopen(url, timeout=0):
            if url.endswith("/metrics"):
                return Response(metrics_payload)
            if url.endswith("/slots"):
                return Response(slot_payload)
            raise AssertionError(url)

        with patch("turbolauncher.services.monitoring_service.urllib.request.urlopen", side_effect=fake_urlopen):
            snapshot = self.service.collect_monitoring_snapshot("127.0.0.1", 1234)

        self.assertIsNotNone(snapshot.server_metrics)
        self.assertIsNotNone(snapshot.slot_state)
        self.assertEqual(snapshot.ui_metrics["requests"], 3)
        self.assertEqual(snapshot.ui_metrics["slot_id"], 7)
        self.assertEqual(snapshot.ui_metrics["slot_ctx"], 2048)
        self.assertAlmostEqual(snapshot.ui_metrics["session_progress"], 0.25)
        self.assertEqual(snapshot.ui_metrics["session_decoded"], 5)
        self.assertEqual(snapshot.ui_metrics["session_remaining"], 15)

    def test_fetch_local_resource_usage_formats_ui_metrics(self) -> None:
        with patch("turbolauncher.services.monitoring_service.get_cpu_usage", return_value=17.3), patch(
            "turbolauncher.services.monitoring_service.get_ram_usage",
            return_value={"TotalGB": 16.0, "UsedGB": 8.5, "FreeGB": 7.5, "Percent": 53.0},
        ), patch(
            "turbolauncher.services.monitoring_service.get_gpu_info",
            return_value={"Utilization": 44.0, "UsedVramGB": 3.2, "TotalVramGB": 8.0, "Driver": "NVIDIA"},
        ):
            snapshot = self.service.fetch_local_resource_usage()

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.to_ui_metrics()["cpu"], "17%")
        self.assertEqual(snapshot.to_ui_metrics()["ram"], "8.5 / 16.0 GB (53%)")
        self.assertEqual(snapshot.to_ui_metrics()["gpu"], "44%")
        self.assertEqual(snapshot.to_ui_metrics()["gpu_vram"], "3.2 / 8.0 GB")

class ChatRegressionTests(unittest.TestCase):
    def test_build_base_url_uses_host_and_port(self) -> None:
        self.assertEqual(build_base_url("127.0.0.1", 8080), "http://127.0.0.1:8080")

    def test_get_model_id_reads_first_available_model(self) -> None:
        class FakeResponse:
            def __init__(self, payload: str) -> None:
                self.payload = payload.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return self.payload

        with patch(
            "turbolauncher.chat.urllib.request.urlopen",
            return_value=FakeResponse('{"data": [{"id": "demo-model"}]}'),
        ):
            self.assertEqual(get_model_id("127.0.0.1", 8080), "demo-model")

    def test_stream_chat_completion_yields_sse_chunks(self) -> None:
        class FakeResponse:
            def __init__(self, lines: list[bytes]) -> None:
                self.lines = lines

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __iter__(self):
                return iter(self.lines)

        lines = [
            b'data: {"choices": [{"delta": {"content": "Hel"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": "lo"}}]}\n\n',
            b'data: [DONE]\n\n',
        ]

        with patch(
            "turbolauncher.chat.urllib.request.urlopen",
            return_value=FakeResponse(lines),
        ):
            chunks = list(
                stream_chat_completion(
                    "127.0.0.1",
                    8080,
                    [ChatMessage(role="user", content="Hi")],
                    "demo-model",
                )
            )

        self.assertEqual("".join(chunks), "Hello")

    def test_stream_chat_events_keeps_prompt_progress_events(self) -> None:
        class FakeResponse:
            def __init__(self, lines: list[bytes]) -> None:
                self.lines = lines

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __iter__(self):
                return iter(self.lines)

        lines = [
            b'data: {"prompt_progress": {"processed": 128, "total": 256}}\n\n',
            b'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n',
            b'data: [DONE]\n\n',
        ]

        with patch(
            "turbolauncher.chat.urllib.request.urlopen",
            return_value=FakeResponse(lines),
        ):
            events = list(
                stream_chat_events(
                    "127.0.0.1",
                    8080,
                    [ChatMessage(role="user", content="Hi")],
                    "demo-model",
                )
            )

        self.assertEqual(events[0]["prompt_progress"]["processed"], 128)
        self.assertEqual(events[1]["choices"][0]["delta"]["content"], "Hi")


class MonitoringRegressionTests(unittest.TestCase):
    def test_parse_prometheus_metrics_supports_current_llamacpp_names(self) -> None:
        content = """
llamacpp:predicted_tokens_seconds 42.5
llamacpp:prompt_tokens_seconds 128.0
llamacpp:tokens_predicted_total 850
llamacpp:prompt_tokens_total 300
llamacpp:tokens_predicted_seconds_total 12.75
llamacpp:prompt_seconds_total 1.5
llamacpp:n_tokens_max 65536
llamacpp:kv_cache_usage_ratio 0.42
llamacpp:kv_cache_tokens 4096
llamacpp:requests_processing 2
llamacpp:requests_deferred 1
"""

        metrics = parse_prometheus_metrics(content)

        self.assertEqual(metrics["tps"], 42.5)
        self.assertEqual(metrics["peps"], 128.0)
        self.assertEqual(metrics["total_decode_tokens"], 850)
        self.assertEqual(metrics["total_prompt_tokens"], 300)
        self.assertEqual(metrics["total_decode_time"], 12.75)
        self.assertEqual(metrics["total_prompt_time"], 1.5)
        self.assertEqual(metrics["ctx_size"], 65536)
        self.assertEqual(metrics["kv_usage"], 0.42)
        self.assertEqual(metrics["kv_cache_tokens"], 4096)
        self.assertEqual(metrics["requests"], 3)
        self.assertEqual(metrics["requests_processing"], 2)
        self.assertEqual(metrics["requests_deferred"], 1)

    def test_parse_prometheus_metrics_keeps_legacy_fallbacks(self) -> None:
        content = """
tokens_per_second 9.5
prompt_eval_tokens_per_second 17.25
eval_n_total 120
prompt_eval_n_total 64
eval_seconds_total 3.0
prompt_eval_seconds_total 1.0
n_ctx 8192
kv_cache_usage_count 0.25
llama_server_request_success_total 7
"""

        metrics = parse_prometheus_metrics(content)

        self.assertEqual(metrics["tps"], 9.5)
        self.assertEqual(metrics["peps"], 17.25)
        self.assertEqual(metrics["total_decode_tokens"], 120)
        self.assertEqual(metrics["total_prompt_tokens"], 64)
        self.assertEqual(metrics["total_decode_time"], 3.0)
        self.assertEqual(metrics["total_prompt_time"], 1.0)
        self.assertEqual(metrics["ctx_size"], 8192)
        self.assertEqual(metrics["kv_usage"], 0.25)
        self.assertEqual(metrics["requests"], 7)

    def test_parse_slots_status_extracts_active_session_metrics(self) -> None:
        payload = """
[
  {"id":0,"id_task":11,"n_ctx":65536,"is_processing":true,
   "next_token":{"n_decoded":120,"n_remain":30,"has_next_token":true}},
  {"id":1,"id_task":-1,"n_ctx":65536,"is_processing":false,
   "next_token":{"n_decoded":0,"n_remain":0,"has_next_token":false}}
]
"""

        metrics = parse_slots_status(payload)

        self.assertEqual(metrics["slot_id"], 0)
        self.assertEqual(metrics["task_id"], 11)
        self.assertEqual(metrics["slot_ctx"], 65536)
        self.assertTrue(metrics["slot_processing"])
        self.assertEqual(metrics["session_decoded"], 120)
        self.assertEqual(metrics["session_remaining"], 30)
        self.assertAlmostEqual(metrics["session_progress"], 0.8)

    def test_parse_slots_status_accepts_dict_wrapped_slots_payload(self) -> None:
        payload = """
{"slots": [
  {"id":2,"id_task":17,"n_ctx":32768,"is_processing":true,
   "next_token":{"n_decoded":0,"n_remain":-1,"has_next_token":true}}
]}
"""

        metrics = parse_slots_status(payload)

        self.assertEqual(metrics["slot_id"], 2)
        self.assertEqual(metrics["task_id"], 17)
        self.assertEqual(metrics["slot_ctx"], 32768)
        self.assertTrue(metrics["slot_processing"])
        self.assertEqual(metrics["session_decoded"], 0)
        self.assertEqual(metrics["session_remaining"], -1)
        self.assertNotIn("session_progress", metrics)


if __name__ == "__main__":
    unittest.main()
