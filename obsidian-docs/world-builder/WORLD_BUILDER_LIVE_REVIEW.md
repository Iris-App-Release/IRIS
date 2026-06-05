---
title: World Builder Live — Generation Review
type: review
related: [WORLD_BUILDER_AUDIT, WORLD_SCHEMA, grid-creator-tool-plan, IMPLEMENTATION_ROADMAP]
last_updated: 2026-06-05
sources:
  - UI/world_builder_api.py
  - Scripts/world_builder_cli.py
  - .claude/skills/world-builder-live/SKILL.md
  - Worlds/placeable.py
---

# World Builder Live — Generation Review (Phase 5)

> **Scope.** Audit how `/world-builder-live` (and the in-app **Send**) turns a prompt
> into placed objects: how placement decisions are made, how coordinates are generated,
> and whether **coordinate confidence** and **determinism** can be improved. Grounded
> in `UI/world_builder_api.py` and the skill.

---

## 1. How it works today

```
prompt
  → generate_world_objects(prompt, world_def)        [UI/world_builder_api.py]
      • DEFAULT_MODEL = claude-sonnet-4-6 (override IRIS_WB_MODEL)
      • system = SYSTEM_PROMPT  (cache_control: ephemeral)   ← cached, billed cheap after 1st
      • user   = _build_user_message(prompt, divisions, depth)
      • max_tokens = 1500, no temperature set (⇒ default)
      • messages.create(...)  → text
  → _parse_json_objects(text)   (tolerant: strips fences, falls back to outer [...] slice)
  → sanitize_objects(raw, D)    (clamp + allowlist + cap)     ← SAFETY GATE
```

**Strengths (keep):**
- The **safety gate is unconditional** — output is clamped/allowlisted before disk, so
  a bad generation degrades gracefully (skipped/clamped), never crashes or escapes the box.
- **Tolerant parser** — survives stray markdown fences or prose despite the strict prompt.
- **System-prompt caching** — the static contract is billed at cache rate after the first
  call (good COGS hygiene; see [[grid-creator-tool-plan]] §10.7).
- **Robust key resolution** — env → `~/.iris/anthropic_key` → `~/.iris/config.json`, so a
  Finder-launched `.app` (no shell env) still finds a key.
- **Dev/test parity** — the CLI `--objects` bridge routes hand-authored JSON through the
  identical `sanitize_objects`, so offline tests are byte-identical to live output.

---

## 2. Q1 — How are placement decisions made?

Entirely by the model, steered by the `SYSTEM_PROMPT` spatial-language rules:

> "back-left → gx negative, gz near D; up front / near the glass → gz near 0; floating
> high → gy positive; on the floor → gy near −D/2; centre → 0."

It is **zero-shot** (rules only, no worked examples) and **free-form JSON** (no
structured-output enforcement). The user message supplies `grid_divisions`, `grid_depth`,
and the valid cell ranges, which is good grounding. The convention now matches the rest
of the system (gz=0 = glass), so the model, the renderers, and the grid ruler all speak
the same coordinate language (post-fix; see [[WORLD_BUILDER_AUDIT]]).

## 3. Q2 — How are coordinates generated?

Free text → JSON array → tolerant parse → clamp. There is **no schema-level guarantee**
that the model returns valid JSON of the right shape; correctness rests on (a) the prompt,
(b) the tolerant parser, and (c) the clamp. In practice this works for typical prompts,
but two failure modes remain:
- **Silent clamp drift** — a model that mis-reads depth (e.g., emits gz≈D for "near the
  glass") is *silently corrected toward the box*, not toward the user's intent: the object
  lands clamped but in the wrong place, with no signal.
- **Parse-empty** — a sufficiently chatty or malformed reply slices to `[]` ⇒ "No objects
  generated", which reads as a failure even when the model "tried".

---

## 4. Q3 — Can coordinate confidence be improved? (recommended)

| # | Improvement | Effort | Why it raises confidence |
|---|---|---|---|
| C1 | **Structured output via tool use** — define an `emit_objects` tool with an `input_schema` matching [[WORLD_SCHEMA]] and force `tool_choice`. | M | Eliminates parse failures and shape drift entirely; the model *must* return the contract. The tolerant parser becomes a fallback, not the primary path. |
| C2 | **Few-shot anchors** — 2–3 `(prompt → exact JSON)` examples covering front/back/left/right/floor/ceiling. | S | Anchors the spatial mapping far better than rules alone; biggest accuracy win per token. |
| C3 | **Echo a labelled grid** — include an ASCII/coordinate legend of the cells (e.g., centre = 0, walls = ±D/2, glass = gz 0) and ask the model to *name the cell in words then the numbers*. | S | Forces the model to reason in the same frame the user reads off the oblique grid. |
| C4 | **Per-object rationale (debug channel)** — optional `"_why"` string the renderers ignore but the CLI/skill relays. | S | Surfaces *intent vs clamped result*; makes "silent clamp drift" visible to the user/author. |
| C5 | **Clamp-report** — have the CLI/Send diff pre- vs post-`sanitize` and warn when a cell was clamped (object moved). | S | Turns the silent correction in §3 into actionable feedback ("moved your cube inside the box"). |

## 5. Q4 — Can descriptions be made more deterministic? (recommended)

| # | Improvement | Effort | Effect |
|---|---|---|---|
| D1 | **Set `temperature=0`** (or ~0.2) for the generation call. | XS | Same prompt → near-identical objects run to run; the single highest-leverage determinism lever. Currently unset (default ≈1.0). |
| D2 | **Deterministic ids** — derive `id` from model+index (`cube_1`) in `sanitize_objects` when absent, instead of trusting the model. | XS | Stable references for later edit/delete; reproducible diffs. |
| D3 | **Stable ordering** — sort the sanitized list by `(gz, gx, gy)` before write. | XS | Byte-stable `world.json` for the same scene ⇒ clean git diffs, reproducible tests. |
| D4 | **Pin a snapshot model alias** in releases (already overridable via `IRIS_WB_MODEL`). | XS | Output doesn't shift under the user when the default model rolls. |

> C1 (structured output) + D1 (temperature 0) together convert generation from
> "usually parses, roughly right" to "always valid, reproducible" — the reliability bar a
> paid hook needs ([[grid-creator-tool-plan]] §9).

---

## 6. COGS & gating note

Each **Send** is one real Claude call (the developer's cost, not the user's). The system
prompt is cached and `max_tokens=1500`, so unit cost is small but non-zero. Determinism
work (D1) does not change cost; structured output (C1) is roughly cost-neutral. The
freemium lever (`FREE_CUSTOMIZATION_LIMIT`, currently `inf`) is what caps free-tier spend
— turn it finite alongside whichever API-cost channel ships (proxy / BYOK / hybrid). See
[[grid-creator-tool-plan]] §10.7 and [[IMPLEMENTATION_ROADMAP]].

## 7. Recommended order

1. **D1** (temperature 0) — one line, immediate determinism.
2. **C2** (few-shot) — biggest accuracy gain.
3. **C1** (tool-use structured output) — removes parse/shape risk class.
4. **C5/C4** (clamp-report / rationale) — make silent drift visible.
5. **D2/D3** (deterministic ids + ordering) — reproducible artifacts.

None of these touch the frozen core or the safety gate; they harden the authoring layer
only. Each should keep all headless sims green and be spot-checked against the §9
reliability bake (10+ varied prompts, zero crashes, zero out-of-box escapes).

## Related
[[WORLD_BUILDER_AUDIT]] · [[WORLD_SCHEMA]] · [[grid-creator-tool-plan]] · [[IMPLEMENTATION_ROADMAP]]
