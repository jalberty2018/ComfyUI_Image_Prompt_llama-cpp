---
name: krea-2-text-expansion
description: Expand text-to-image requests into natural-language image prompts for Krea 2. Select with T2I mode.
---

# Krea 2 text expansion

Expand the brief into one coherent image-description paragraph. Retain the requested medium, subjects, actions, colors, and arrangement. Keep each subject's properties and actions together, with clear placement and interactions.

Choose framing, illumination, and mood that support the brief. Add only grounded detail; do not introduce unsupported objects, people, animals, wardrobe, or materials. For an already rich description, make small improvements instead of expanding aggressively. Preserve requested lettering exactly and enclose it in quotation marks. Depict people respectfully, with intimate areas covered by clothing. Keep deliberation out of the result.

For this skill, these conservative expansion rules replace generic directions to invent the rest of a scene or always produce a long paragraph.

## Node integration

Use T2I mode. Put the paragraph in `rewritten_prompt` within the node's required JSON object, including its required `wh_ratio` string. The paragraph itself contains no headings, lists, or formatting. Preserve the model's aspect-ratio rules and JSON schema; do not return bare prose. If selected in I2I mode, preserve reference facts and the I2I schema rather than treating the request as text-only.

## Sources

Adapted from Krea's [expansion instructions](https://github.com/krea-ai/krea-2/blob/main/docs/expansion.txt) and [prompting guidelines](https://github.com/krea-ai/krea-2/blob/main/docs/prompting.md). The upstream plain-text response is wrapped in JSON here for node compatibility.
