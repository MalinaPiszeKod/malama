# llama-server integration notes

Sources consulted:
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README-dev.md
- https://github.com/ggml-org/llama.cpp/pull/17470
- https://github.com/ggml-org/llama.cpp/issues/18035
- https://github.com/ggml-org/llama.cpp/pull/18206

## Current llama-server defaults / behavior

- `--ctx-size` default is `0`, meaning use the context length loaded from model metadata.
- `--n-gpu-layers` default is `auto`; current docs allow exact number, `auto`, or `all`.
- GPU offload is layer-based and the output layer can be part of full offload depending on model/runtime behavior. The launcher should treat `TRANSFORMER_LAYERS + output layer` as the full offload count unless sidecar metadata says otherwise.
- `--cache-type-k` and `--cache-type-v` default to `f16`; lower-bit KV cache types reduce memory at possible quality/speed trade-offs.
- `--flash-attn` default is `auto`; expose on/off/auto rather than a fake boolean-only assumption.
- `--mmap` is enabled by default; `--mlock` is off by default. `mlock` pins model memory and can hurt the system if RAM is tight.
- `--batch-size` default is `2048`; `--ubatch-size` default is `512`. `ubatch` is the more direct VRAM pressure knob.
- `--parallel` default is auto (`-1` in docs). Higher values increase concurrent slots and KV cache memory use.
- Continuous batching is enabled by default and improves multi-request throughput.
- Jinja/chat template should default to model metadata/auto unless the user overrides a template.
- Sampling defaults in current docs: temp `0.8`, top-k `40`, top-p `0.95`, min-p `0.05`, typical-p disabled/`1.0`, repeat-last-n `64`, repeat-penalty around `1.1`, seed `-1` random.

## Router / multi-model mode

- `--models-dir` enables router/multi-model repository mode.
- `--models-max` defaults to `4`; `0` means unlimited.
- `--models-autoload` is enabled by default and means load a requested model on demand, not preload every model at startup.
- Router mode exposes `/models`, `/models/load`, `/models/unload`, and `/v1/models` style endpoints depending on build/version.
- Router mode is still evolving; the UI should label it as repository/router mode and not imply all models are resident in VRAM.

## UI guidance

- Prefer `Auto / model default` where llama-server has a meaningful auto default.
- Dropdowns should cover safe/common values, but any field that maps to a free-form flag must also allow custom override.
- Tooltips should explain ownership and trade-offs: startup flag vs model-load flag vs request-time default.
- Inferred limits are guardrails for sliders, not hard validation for manual numeric overrides.

## Verified dropdown values

- Flash Attention: `auto`, `on`, `off`; default `auto`.
- KV cache K/V: `f32`, `f16`, `bf16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, `q5_0`, `q5_1`; default `f16`.
- Split mode: `none`, `layer`, `row`; default `layer` in llama.cpp docs. The launcher may show `auto` for compatibility/older saved settings, but should pass only explicit values when changed.
- Reasoning format: `auto`, `none`, `deepseek`, `deepseek-legacy`; default `auto`.
- Reasoning use: `auto`, `on`, `off`; default `auto`.
