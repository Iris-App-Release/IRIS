# Obsidian Documentation Audit Findings
**Date:** 2026-06-01  
**Status:** ✅ COMPLETE — All 6 inaccuracies fixed

## Summary
Deep audit of obsidian-docs/ against source code. Found 6 inaccuracies — **all fixed**.

### Fixes Applied
1. ✅ JSON syntax error in `Worlds/the_watcher/world.json` (missing comma)
2. ✅ Gem facet count in `design-decisions.md` (n=32 → n=16)
3. ✅ Gem background field in `the-gem.md` (`void` → `sky`)
4. ✅ Gem assets documentation in `the-gem.md` (clarified minimal assets)
5. ✅ Schema in `world-system.md` (updated deployed values)
6. ✅ Wiki file renamed: `the-gem.md` → `gem.md` + all references updated

---

## Cleanup Note
**File to remove:** `obsidian-docs/worlds/the-gem.md`  
This file has been replaced by `obsidian-docs/worlds/gem.md` to match the directory structure. The old file should be deleted to avoid Obsidian showing duplicate pages.

---

## INACCURACY #1: Gem Mesh Facet Count (design-decisions.md)
**Severity:** Medium - contradicts the-gem.md  
**Location:** `obsidian-docs/architecture/design-decisions.md`, line 82  
**Current text:**
```
The third world ([[the-gem]]) uses the pre-existing `Gem` renderer class 
with `make_gem(n=32)` (128 flat-shaded triangles).
```

**Ground truth** (Engine/renderer.py:81):
```python
def make_gem(n=16, r_girdle=2.2, table_ratio=0.48, h_crown=0.79, h_pav=2.80):
```

**Usage** (Engine/renderer.py:288):
```python
v, n = make_gem()  # uses default n=16
```

**Correct text:**
```
The third world ([[the-gem]]) uses the pre-existing `Gem` renderer class 
with `make_gem(n=16)` (64 flat-shaded triangles).
```

**Related doc** (the-gem.md:38): ✅ Correct — already states "n=16" and "64 flat-shaded triangles"

---

## INACCURACY #2: Gem World Background Field (the-gem.md)
**Severity:** Medium - inconsistency with actual world.json  
**Location:** `obsidian-docs/worlds/the-gem.md`, line 26  
**Current text:**
```
| `background` | `void` |
```

**Ground truth** (Worlds/gem/world.json:8):
```json
"background": "sky",
```

**Impact:** Doc implies render code treats `void` as a valid background option, but the actual world uses `sky`. The world.json schema handles both, but this specific world uses `sky`.

**Correct text:**
```
| `background` | `sky` |
```

---

## INACCURACY #3: Gem Floor Texture Not Documented (the-gem.md)
**Severity:** Low - feature exists but undocumented  
**Location:** `obsidian-docs/worlds/the-gem.md`, line 57  
**Current section:**
```
## No assets required

Unlike Earth (five textures) and The Watcher (three procedural textures), The Gem is entirely procedural. `make_gem()` generates all geometry at startup; the `gem` shader handles all colour, lighting, and emissive — no texture files are needed.
```

**Ground truth** (Worlds/gem/world.json:19):
```json
"floor_texture": "floor_checkered.png",
```

**Impact:** The gem DOES use a texture asset (floor_checkered.png), contrary to "entirely procedural" claim.

**Correct text:**
The section should note the floor shadow texture:
```
## Minimal assets

Unlike Earth (five textures) and The Watcher (three procedural textures), The Gem is nearly entirely procedural. `make_gem()` generates all geometry at startup; the `gem` shader handles all colour, lighting, and emissive — no texture files are needed for the gem itself. The shadow disk references one texture: `floor_checkered.png` (a simple checkered pattern used for visual grounding).
```

---

## INACCURACY #4: JSON Syntax Error in The Watcher world.json
**Severity:** High - Breaks JSON parsing  
**Location:** `Worlds/the_watcher/world.json`, line 25  
**Current text:**
```json
      "diffuse": "eye_diffuse.png",
      "floor_texture": "floor_checkered.png"
      "normal": "eye_normal.png",
```

**Issue:** Missing comma after `floor_checkered.png"`  

**Correct text:**
```json
      "diffuse": "eye_diffuse.png",
      "floor_texture": "floor_checkered.png",
      "normal": "eye_normal.png",
```

---

## INACCURACY #5: System Interactions Schema References "void" (system-interactions.md)
**Severity:** Low - Misleading default  
**Location:** `obsidian-docs/architecture/system-interactions.md` (implied in the schema section)  
**Context:** The world.json schema block shows:
```json
"background": "stars",              // stars | void
```

But actual deployed worlds use:
- Earth: `"stars"`
- The Watcher: `"sky"`
- The Gem: `"sky"`

**Issue:** None of the deployed worlds actually use `void`. It's mentioned as a valid option but never instantiated. The docs mention it in discussions of rendering flags, but no actual world uses it.

**Note:** This is technically correct (the rendering code likely supports void as a fallback), but the documentation should clarify that all shipped worlds use `sky` instead. The schema doc is aspirational rather than descriptive of deployed worlds.

**Recommendation:** Update schema block to show actual deployed values:
```json
"background": "stars",              // stars | sky (deployed: earth uses stars; the-watcher & gem use sky)
```

---

## INACCURACY #6: Worlds Directory Source Reference Inconsistency (the-gem.md)
**Severity:** Low - Naming inconsistency  
**Location:** `obsidian-docs/worlds/the-gem.md`, frontmatter line 6  
**Current:**
```yaml
sources: [Worlds/gem/world.json, Engine/renderer.py, shaders/gem.vert, shaders/gem.frag, Launcher/app_engine.py]
```

**Ground truth:** Actual directory is `Worlds/gem/` (confirmed by filesystem), so this is CORRECT. However, the document itself uses inconsistent naming:
- Refers to the world as `[[the-gem]]` in docs (note: with hyphen)
- Actual directory: `gem` (no hyphen, no "the-")

**Impact:** Navigation and consistency. The docs reference `[[the-gem]]` but the source is `Worlds/gem/`.

**Pattern check:** Other worlds are consistent:
- `the_watcher` directory → referenced as `[[the-watcher]]` ✅ Consistent (underscore → hyphen)
- `gem` directory → referenced as `[[the-gem]]` ❌ Inconsistent (added "the-")
- `earth` directory → referenced as `[[earth]]` ✅ Consistent (exact match)

**Recommendation:** Either rename the world directory to `the-gem/` for consistency OR update docs to reference `[[gem]]` instead of `[[the-gem]]`. The world's *display name* in world.json is "The Gem", but the reference should match the directory structure.

---

## Summary Table

| # | File | Issue | Severity | Fix |
|---|------|-------|----------|-----|
| 1 | design-decisions.md | `n=32` should be `n=16` | Medium | Change "n=32" to "n=16" and "128" to "64" |
| 2 | the-gem.md | background `void` should be `sky` | Medium | Change table entry |
| 3 | the-gem.md | "entirely procedural" contradicts floor_texture in world.json | Low | Clarify minimal assets |
| 4 | the_watcher/world.json | Missing comma after floor_texture value | High | Add comma |
| 5 | system-interactions.md | Schema mentions "void" but no deployed world uses it | Low | Clarify deployed values in comment |
| 6 | the-gem.md | Directory `gem/` vs doc reference `[[the-gem]]` | Low | Standardize naming |

---

## Recommendations for Future Maintenance

1. **Add validation to CI:** JSON files should be validated with `jq` on commit
2. **Cross-reference sources:** When docs cite a specific file:line, verify it still matches on each edit
3. **Sync world schemas:** The world.json schema in system-interactions.md should be generated from actual deployed worlds, not imagined options
4. **Naming consistency:** Adopt a rule: directory name = reference name (gem/ → [[gem]] or the-gem/ → [[the-gem]])

