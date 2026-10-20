# Custom image prompt skills

All skills live here, including Qwen, Krea and FLUX. Each subdirectory must contain a
`SKILL.md`. Restart ComfyUI and refresh the page after adding or changing skills.
Select the skill explicitly; the default is `qwen-image-prompt` when available.
There is no automatic routing or separate built-in skill directory.

```text
custom_skills/
  qwen-image-prompt/
    SKILL.md
    skill.json
    prompts/
      T2I.txt
      I2I.txt
      uncensored.txt
      T2I-LICENSE
      I2I-LICENSE
      sources.json
  krea-2-text-expansion/
    SKILL.md
    skill.json
    prompts/
      expansion.txt
      expansion-i2i.txt
```

## Skill metadata and configuration

Optional YAML front matter in `SKILL.md` supports `name`, `description`,
`display-name`, and `version`; `meta.yaml` also supports tags. IDs use lowercase
letters, numbers, periods, underscores, and hyphens and cannot be `auto`.
Duplicate IDs are ignored after the first match in folder-name order.

`skill.json` declares supported modes and profiles. Each value is a prompt file
relative to the skill directory, or `null` when no extra prompt is needed:

```json
{
  "modes": {"T2I": "prompts/T2I.txt", "I2I": "prompts/I2I.txt"},
  "profiles": {"standard": null, "uncensored fidelity QWEN": "prompts/uncensored.txt"}
}
```

Without `skill.json`, a skill supports only `T2I` and `standard`, with no extra
prompt files. Mode names are `T2I` and `I2I`; profile names are `standard` and
`uncensored fidelity QWEN`. Unsupported combinations and invalid configuration
are rejected before model loading. Referenced files must stay inside the skill.

The loader combines only the selected mode's prompt, `SKILL.md`, all `.md` and
`.txt` files under `references/`, the selected profile's prompt, and additional
system instructions, in that order. It then appends the shared JSON contract.
Store system prompts in `prompts/` and select them through `skill.json`.
Use optional `references/` only for supplementary guidance shared across modes.
No scripts execute and no internet links are fetched during inference.

## Included skills

- [FLUX.3 klein pup](flux-3-image-klein-pup/SKILL.md): T2I and I2I with the standard profile, using the original `t2i` and `i2i` system prompts.
- [FLUX.3 klein pup bounding boxes](flux-3-image-klein-pup-bbox/SKILL.md): T2I and I2I with the standard profile, using `t2i_bbox` and `i2i_bbox`. The complete caption/instruction and element table are returned directly in the native annotation format, without an outer JSON wrapper. Older responses wrapped in `rewritten_prompt` are also accepted if they contain the complete table. Both FLUX skills use `SKILL.md`, `skill.json`, `prompts/T2I.txt`, `prompts/I2I.txt` and `prompts/sources.json`, matching the Qwen structure. Original prompts and pinned source revisions are preserved under `prompts/`.
- [Qwen](qwen-image-prompt/SKILL.md): T2I and I2I, both profiles. Its original
  prompts, licenses, and source metadata are in its own `prompts/` directory.
- [Krea 2](krea-2-text-expansion/SKILL.md): T2I and I2I with the standard profile only. T2I loads the local,
  unmodified [expansion.txt](krea-2-text-expansion/prompts/expansion.txt) from
  [Krea](https://github.com/krea-ai/krea-2/blob/main/docs/expansion.txt).
  I2I selects the user-provided [expansion-i2i.txt](krea-2-text-expansion/prompts/expansion-i2i.txt),
  adapted to include `ratio_follow` in the node's JSON output schema.

Skills are self-contained: no skill automatically inherits Qwen instructions.
The common transport contract overrides bare-prose output requirements and
requires string fields `rewritten_prompt` and `wh_ratio`, plus `ratio_follow`
for I2I. Skill-specific aspect-ratio rules are preserved. Without such rules,
`wh_ratio` is the requested ratio or empty. The node extracts `rewritten_prompt`
into `h3_prompt`. These skills prepare prompts; they do not run image models.
