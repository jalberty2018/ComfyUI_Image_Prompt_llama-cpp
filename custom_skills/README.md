# Custom image prompt Skills

Place each prompt-only Skill in its own subdirectory with a `SKILL.md`, then restart ComfyUI. Optional YAML front matter supports `name`, `description`, `display-name` and `version`; `meta.yaml` also supports tags. IDs use lowercase letters, numbers, periods, underscores and hyphens and cannot be `auto`. Duplicate IDs cannot override bundled Skills.

Markdown and text files under `references/` are loaded as additional guidance. No scripts or tools are executed. Use Skills for image style or editing instructions. The selected model's JSON contract and reference-image facts take precedence over Skill instructions. The node extracts `rewritten_prompt` into its first output.

Select a Skill explicitly from the node's `skill` dropdown; automatic routing is not supported. The default remains `qwen-image-prompt`.

## Included custom Skill

[`krea-2-text-expansion`](krea-2-text-expansion/SKILL.md) expands text-to-image briefs for Krea 2 using the official [Krea documentation](https://github.com/krea-ai/krea-2/tree/main/docs). Select it with `mode=T2I` and a compatible GGUF language model. The expanded paragraph is returned through `h3_prompt`; the model response keeps the node's required JSON format. This is a prompt-only Skill in [ComfyUI_Image_Prompt_llama-cpp](https://github.com/jalberty2018/ComfyUI_Image_Prompt_llama-cpp), not a Krea image-generation runtime.
