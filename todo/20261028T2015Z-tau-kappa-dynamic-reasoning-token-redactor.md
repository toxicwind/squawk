# dynamic redaction patcher — strip leaked reasoning tokens (<thinking>, <antThinking>, <*>) in tau + kappa TUIs

- **Status:** NOT-STARTED
- **Found:** 2026-10-28T19:25Z — architect saw raw `<antThinking>` markers rendered live
  in the kappa TUI (leaked "token" from a model turn)

## Problem

OpenAI-compatible providers emit reasoning as pseudo-tags (`<thinking>`, `<antThinking>`,
`<reasoning>`, and provider-specific variants). When a model inlines them inside visible
`text` content (instead of the typed reasoning channel), tau/kappa render the raw markers
to the user — leaked internals, confusing "gaslighting" surface.

## Fix direction (forward, dynamic, not model-locked)

1. **Hyper research task (untruncated):** enumerate every tag-like leak class seen in the
   estate — grep tau session stores (~/.tau/agent/sessions) + kappa storage + report
   bundles for `<thinking>`, `<antThinking>`, `<reasoning>`, `<|`, `SAT>`, `<next>`,
   `<thought>`, provider tags (z-ai glm, minimax, qwen variants). Log the inventory with
   counts and provenance.
2. Implement a **dynamic patcher plugin/extension** (tau extension + kappa plugin):
   a streaming post-processor that detects `<tag>...</tag>` reasoning blocks in text
   content, relocates them to the typed reasoning channel (or redacts), and keeps a
   reactive registry so NEW tag classes are caught by pattern (any `<x>` block that
   providers use for hidden channels) — not a hardcoded list only.
3. Register the tag inventory as shared state (squawk log or malachite dataset) so tau and
   kappa redact identically.

## Acceptance

- Live kappa TUI + tau session replay: zero raw reasoning markers in visible output;
  tagged content correctly routed/redacted; inventory dataset committed.
