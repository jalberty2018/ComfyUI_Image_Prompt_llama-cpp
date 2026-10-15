---
name: qwen-image-prompt
description: Rewrite generation and editing requests for Qwen-Image 2.1.
---

Follow the selected mode's prompt from this skill's prompts directory:
[ T2I ](prompts/T2I.txt) for generation, [ I2I ](prompts/I2I.txt) for editing.
The loader selects exactly one through skill.json. Preserve user intent and
visible reference facts. The optional Qwen profile is also local to this skill.
