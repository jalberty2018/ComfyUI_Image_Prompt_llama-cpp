---
name: krea-2-text-expansion
description: Expand generation and reference-image editing requests for Krea 2. Supports T2I and I2I with the standard profile.
---

# Krea 2 prompt expansion

Follow the selected mode's instructions, loaded through skill.json:

- T2I: [prompts/expansion.txt](prompts/expansion.txt), the unmodified official Krea expansion prompt.
- I2I: [prompts/expansion-i2i.txt](prompts/expansion-i2i.txt), the user-supplied multi-reference prompt, with its output section adapted to include the node's required ratio_follow field.

The loader selects exactly one mode prompt. For I2I, use only supplied reference
images and their assigned roles; the node numbers them consecutively in socket
order as <image1> through <image10>. A vision-capable GGUF model and matching
mmproj are required. The node appends its JSON transport contract and extracts
rewritten_prompt for the output.

T2I source: https://github.com/krea-ai/krea-2/blob/main/docs/expansion.txt
Prompting guidance: https://github.com/krea-ai/krea-2/blob/main/docs/prompting.md
The I2I prompt is user-provided, not an official upstream Krea prompt.

No Qwen rewriting instructions are included. Both modes require the standard
profile; the Qwen-specific profile is rejected before loading the model.
