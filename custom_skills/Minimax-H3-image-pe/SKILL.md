---
name: minimax-h3-image-pe
display-name: Minimax-H3-image-pe
description: Expand still-image generation and reference-conditioned editing prompts for Minimax H3, with plain-text output.
---

Preserve user intent and visible reference facts. Return the complete caption or
editing description as plain text, without JSON. Use aspect-ratio decisions only
to guide composition internally. The user message contains the input request.
For I2I, reference images use <Picture N> labels and exact aspect-ratio metadata.
If no separate User Aspect Ratio Selection is supplied, use adaptive mode.
