# ComfyUI_Image_Prompt_llama-cpp

Local image prompt enhancement using GGUF language models (including the two Heretic prompt rewriters) and an external llama.cpp **b11115** executable. Includes the default Qwen-Image 2.1 skill and a custom Krea 2 text-expansion skill. Add **ComfyUI_Image_Prompt_llama-cpp** to your workflow.

## Installation

From your ComfyUI directory:

```sh
git clone https://github.com/jalberty2018/ComfyUI_Image_Prompt_llama-cpp.git custom_nodes/ComfyUI_Image_Prompt_llama-cpp
```

Download the models and configure llama.cpp as described below, then restart ComfyUI.

## Modes and inputs

Select `skill`, `model`, `mmproj` and `mode` explicitly. The mode selector offers only `T2I` and `I2I`; model names and connected images never switch it automatically.

- `T2I`: text only. Leave `mmproj` empty. Connected images and any selected projector are ignored.
- `I2I`: connect one to ten reference images and select the matching `mmproj` for your vision-capable model. Missing images or an empty projector produce an error before loading.
- `skill`: select a skill discovered in `custom_skills`. The selected skill is used directly, without automatic routing. Restart ComfyUI after adding skills.

There are exactly ten optional IMAGE inputs, `reference_image_1` through `reference_image_10`. Disconnected inputs and inputs returning `None` are skipped. Each supplied tensor must hold one image, not a batch. Nonempty inputs are numbered consecutively as `<image1>`, `<image2>`, etc., in socket order. Refer to these consecutive numbers in your request. Video and audio inputs are not supported.

The four STRING outputs are `enhanced_prompt`, `selected_skill`, `detected_mode`, and `system_prompt`. The first output (previously `h3_prompt`) contains the extracted `rewritten_prompt` for the selected skill. The third output reports the selected `T2I` or `I2I` mode. The fourth output contains the complete system prompt sent to the model, including the selected skill and additional system instructions. Existing output positions are preserved. Aspect-ratio metadata is parsed internally and is not exposed as an additional output.

### Krea 2 text expansion

Select `skill=krea-2-text-expansion`, `mode=T2I`, and a compatible local GGUF language model. Leave `mmproj` empty and enter your image idea. Connect `enhanced_prompt` to the text prompt input of your Krea 2 workflow. Restart ComfyUI and refresh the page after adding the skill.

The [custom skill](custom_skills/krea-2-text-expansion/SKILL.md) loads the local, unmodified [expansion.txt](custom_skills/krea-2-text-expansion/prompts/expansion.txt) from [Krea's official instructions](https://github.com/krea-ai/krea-2/blob/main/docs/expansion.txt). It does not load the Qwen T2I or I2I rewriting prompts. A final transport contract wraps the expanded paragraph in `rewritten_prompt` and supplies `wh_ratio` (the requested ratio, or an empty string). This replaces the upstream plain-text output requirement. This skill prepares text for Krea 2; it does not run the Krea image model. A general instruction-following GGUF model is preferable; Qwen-specific rewriter models may retain their trained rewriting preferences.

For reference-guided generation or editing, select `mode=I2I` with the same skill. Connect one to ten reference images and select a
vision-capable GGUF model plus its matching `mmproj`. This loads the user-provided
[expansion-i2i.txt](custom_skills/krea-2-text-expansion/prompts/expansion-i2i.txt)
instead of the T2I prompt. Its output instructions include the required
`ratio_follow` string alongside `rewritten_prompt` and `wh_ratio`. This I2I prompt
is not an official upstream Krea prompt.

The node ID and display name are both `ComfyUI_Image_Prompt_llama-cpp`. After updating, restart ComfyUI, refresh the page, and replace the old node with **ComfyUI_Image_Prompt_llama-cpp**. Reconnect its inputs and outputs. Previous node IDs are not registered or migrated. Select `T2I` for text generation or `I2I` for image editing workflows.

## Models

Place models anywhere below `ComfyUI/models/LLM`. The model selector recursively scans this directory for all `.gguf` files (case-insensitive), using relative paths to distinguish duplicate filenames. Files containing `mmproj` in their name appear in the separate projector selector. Cache files are excluded. Restart ComfyUI and refresh the page after adding models.

| Mode | Repository | Default file |
|---|---|---|
| T2I | [PE-T2I-Heretic-GGUF](https://huggingface.co/pottokao/Qwen-Image-2.1-PE-T2I-Heretic-GGUF) | `pe_t2i_heretic-Q4_K_M.gguf` |
| I2I | [PE-I2I-Heretic-GGUF](https://huggingface.co/pottokao/Qwen-Image-2.1-PE-I2I-Heretic-GGUF) | `pe_i2i_heretic-Q4_K_M.gguf` |

For I2I images, place `pe_i2i_heretic.mmproj-bf16.gguf` beside the I2I model. Select that file in the separate `mmproj` dropdown, which lists GGUF files containing `mmproj` in their filename. For other vision models, select their matching projector instead.

From the ComfyUI directory:

```sh
hf download pottokao/Qwen-Image-2.1-PE-T2I-Heretic-GGUF pe_t2i_heretic-Q4_K_M.gguf --local-dir models/LLM/Qwen-Image-2.1-PE-T2I-Heretic-GGUF
hf download pottokao/Qwen-Image-2.1-PE-I2I-Heretic-GGUF pe_i2i_heretic-Q4_K_M.gguf pe_i2i_heretic.mmproj-bf16.gguf --local-dir models/LLM/Qwen-Image-2.1-PE-I2I-Heretic-GGUF
```

For `qwen-image-prompt`, the Qwen system prompts are stored in `custom_skills/qwen-image-prompt/prompts/T2I.txt` and `custom_skills/qwen-image-prompt/prompts/I2I.txt`, with their respective licenses. These instructions define the Qwen JSON response format. Krea uses its own expansion instructions and the transport contract described above. Other models must be supported by the configured llama.cpp runtime and follow this format; appearing in the selector does not guarantee runtime compatibility. The node extracts the prompt and retries once to repair malformed output.

## External llama.cpp b11115

Set the executable path **before starting ComfyUI**. This points to a local executable, not an HTTP URL or an already running server.

Linux:

```sh
export QWEN_IMAGE_LLAMA_SERVER=/opt/llama.cpp/bin/llama-server
```

PowerShell:

```powershell
$env:QWEN_IMAGE_LLAMA_SERVER = 'C:\llama.cpp\b11115\llama-server.exe'
```

Keep the executable's runtime libraries available through the external installation's normal library search paths. The node starts its own process on a free loopback port. It does not install or replace the external executable. Without this environment variable, the existing `runtime_config.json` loader and `python install_runtime.py` fallback remain available; the installer is pinned to b11115.

Seed mapping, thinking/reasoning controls, sampling presets, token budget, model reuse and force unload are retained. `force_unload_model` defaults to true; errors always stop the node-owned server and clear the cache. Switching model, projector or runtime causes a reload.

`additional_system_instructions` is appended to the selected skill’s system prompt and included in the `system_prompt` output. The node uses the standard skill instructions without a profile selector. The default skill is `qwen-image-prompt`; the skill selector also includes discovered custom skills.

## Checks

```sh
python -m unittest discover -s tests -v
```

The tests use mocked ComfyUI and llama.cpp interfaces to check routing, image forwarding, output parsing, model selection and cleanup. A live GPU inference check requires the GGUF files, ComfyUI and the external executable.

## Skill layout

Every skill, including Qwen and Krea, lives under `custom_skills/`. Each skill's
`skill.json` declares supported modes, profiles, and local prompt files. The
loader selects those files without special cases for skill IDs. Skills do not
inherit another skill's instructions. See [the skill format](custom_skills/README.md)
for configuration, loading order, and the shared JSON transport contract.
