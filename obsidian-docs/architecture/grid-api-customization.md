---
title: Grid API Customization — Spatial Coordinate System for World Building
type: design-decision
related: [productification, world-system, grid_room, design-decisions, constraints, menu-bar-ui]
last_updated: 2026-06-02
sources: [Worlds/grid_room/world.json, Worlds/world_loader.py, Engine/renderer.py]
---

# Grid API Customization — Spatial Coordinate System for World Building

## Problem

IRIS worlds are currently **content-locked:** users cannot easily customize worlds without editing JSON or Python code. As IRIS scales to multiple worlds, we need a **safe, approachable way for users (and Claude) to customize environment content** without risking the frozen physics/camera math.

## Solution: Grid-Based Spatial Coordinate API

**Approach:** The `grid_room` world acts as a **spatial reference frame and API surface**. A receding wireframe grid teaches users the coordinate system; the JSON schema extended to describe **grid-aligned asset placements**. The frozen camera/physics layers protect against user error.

### Why This Works

1. **Visual coordinate system.** The grid itself is the documentation — users see x/y/z space directly on screen.
2. **Safe customization boundary.** Lock grid volume + camera physics; allow only asset/graphics changes. The frozen layers enforce this.
3. **Claude-friendly API.** Spatial descriptions ("place neon cube in back-left corner at depth 8") translate directly to grid coordinates. Claude can modify `world.json` safely.
4. **Progressive disclosure.** Beginners use point-and-place; advanced users write grid coordinates directly in JSON.

## Grid Coordinate System

### Spatial Bounds & Division

```
Grid Room dimensions:
- X-axis: -4 to +4 (left-right)      [grid_divisions: 8 → 8 cells]
- Y-axis: -3 to +3 (up-down)         [grid_divisions: 8 → 8 cells]
- Z-axis: 0 to 18 (depth/distance)   [grid_depth: 18.0]
```

Users reference grid cells by **discrete integer coordinates [x, y, z]**:
- `[0, 0, 0]` = center, near screen
- `[4, 3, 18]` = far back-right-top
- `[-2, 0, 9]` = center-left, mid-depth

### Grid Cell Size (Normalized)

Each cell is:
- **X:** (8 / 8) = 1.0 unit wide
- **Y:** (6 / 8) = 0.75 unit tall
- **Z:** (18 / 18) = 1.0 unit deep

Objects at grid position `[2, 1, 5]` place at world coordinates approximately `(2.0, 0.75, 5.0)`.

## Extended `world.json` Schema

### Current Grid Room Schema
```json
{
  "name": "Grid Room",
  "environment": {
    "primary_mesh": "room",
    "background": "void",
    "lighting": { "sun_direction": [0, 0, 1], "ambient_intensity": 0.0 }
  },
  "rendering": {
    "grid_color": [0.30, 0.72, 1.0],
    "grid_depth": 18.0,
    "grid_divisions": 8
  }
}
```

### Proposed Extension: Placeable Assets

```json
{
  "name": "Grid Room",
  "environment": { ... },
  "rendering": { ... },
  "assets": {
    "grid_bounds": {
      "min": [-4, -3, 0],
      "max": [4, 3, 18],
      "grid_divisions": 8
    },
    "placeable_objects": [
      {
        "id": "neon_cube_1",
        "type": "mesh",
        "grid_position": [3, 2, 8],       // discrete grid cell
        "model": "assets/neon_cube.obj",   // or: "builtin:cube", "builtin:sphere"
        "scale": 0.8,
        "color": [1.0, 0.2, 0.8],
        "emissive": 0.8,
        "rotation": [0, 45, 0]            // degrees
      },
      {
        "id": "point_light_1",
        "type": "light",
        "grid_position": [0, 3, 12],
        "light_type": "point",
        "intensity": 2.0,
        "color": [0.5, 1.0, 0.5],
        "radius": 3.0
      },
      {
        "id": "crystal_pillar_2",
        "type": "mesh",
        "grid_position": [-2, -2, 5],
        "model": "assets/crystal_pillar.obj",
        "scale": 1.5,
        "material": "glass_blue"
      }
    ]
  }
}
```

### Schema Constraints

**Immutable (protect frozen physics):**
- `grid_bounds`, `grid_divisions`, `grid_depth` — define the coordinate space
- Camera frustum parameters (handled in `camera_math.py`)
- Parallax projection matrix

**Mutable (assets only):**
- `placeable_objects[]` — add/remove/modify objects
- Per-object properties: position, scale, color, model, rotation
- Built-in shapes: `builtin:cube`, `builtin:sphere`, `builtin:cylinder`
- Custom meshes: path to `.obj` or `.gltf` file in `assets/`

## Renderer Integration

The renderer reads `placeable_objects[]` at startup and each frame (if world.json is hot-reloaded):

```python
# Pseudocode (Engine/renderer.py)
def draw_world(world_config):
    # Draw grid (frozen)
    draw_grid(world_config.rendering.grid_color, ...)
    
    # Draw placeable assets (mutable)
    if "assets" in world_config:
        for obj in world_config["assets"]["placeable_objects"]:
            mesh = load_mesh(obj["model"])
            position = grid_to_world(obj["grid_position"], grid_bounds)
            draw_mesh(mesh, position, obj["scale"], obj["color"], ...)
```

**No renderer changes needed** — just read additional JSON and draw meshes. The frozen frustum/parallax math handles everything.

## API Usage Scenarios

### Scenario 1: User Point-and-Place (Future UI)

```
User hovers cursor in grid space
    ↓
Click to place object from palette
    ↓
Settings menu shows grid coordinate [x, y, z]
    ↓
User tweaks color, scale, rotation in UI
    ↓
World.json is updated; changes apply instantly
```

### Scenario 2: Claude Code Customization

User request: *"Add a glowing red sphere in the back-left corner"*

```
Claude reads user request + current world.json
    ↓
Infers grid position [-3, 0, 15] (back-left, mid-height, far depth)
    ↓
Adds to placeable_objects[]:
{
  "id": "red_sphere_glow",
  "type": "mesh",
  "grid_position": [-3, 0, 15],
  "model": "builtin:sphere",
  "scale": 1.2,
  "color": [1.0, 0.0, 0.0],
  "emissive": 1.0
}
    ↓
Writes world.json → daemon hot-reloads next frame
    ↓
User sees red glowing sphere appear in the grid
```

**Safety:** Claude cannot modify `grid_bounds`, `grid_depth`, or frozen camera/physics. Only asset properties.

### Scenario 3: Procedural World Generation

```
User: "Generate a grid room with 10 random glowing cubes at different depths"
    ↓
Claude generates:
{
  "assets": {
    "grid_bounds": { ... },
    "placeable_objects": [
      { "id": "cube_0", "grid_position": [random, random, random], ... },
      { "id": "cube_1", "grid_position": [random, random, random], ... },
      ...
    ]
  }
}
    ↓
User sees procedurally-generated world instantly
```

No physics recalculation; just asset placement on the frozen stage.

## Relationship to Productification

This architecture **enables user-driven customization at scale:**

| Milestone | Relevance |
|---|---|
| **Multi-world support** ([[productification#world-catalog]]) | Grid system is the template for safe, extensible worlds. |
| **Community world building** | Grid API + Claude integration allows users to remix worlds without code knowledge. |
| **AI-assisted customization** | Claude can understand spatial descriptions + grid coordinates; safe to apply user requests. |
| **Subscription/marketplace model** | Users buy or create worlds; grid coordinate system is the common interchange format. |
| **Onboarding UX** | Grid teaches spatial coordinates; reduces documentation burden. |
| **Developer tools** ([[productification#developer-tooling]]) | Grid API is the documented public API for world customization. |

## Implementation Roadmap

### Phase 1: Parser + Hot-Reload
- [ ] Extend `world_loader.py` to parse `assets.placeable_objects[]`
- [ ] Renderer reads and draws placeable objects
- [ ] File watcher for hot-reload on `world.json` change

### Phase 2: Claude Integration
- [ ] Document grid coordinate system + schema in API reference
- [ ] Test Claude modifying `world.json` for spatial asset requests
- [ ] Add validation: ensure objects stay within `grid_bounds`

### Phase 3: UI Point-and-Place (Menu Bar)
- [ ] Settings window displays grid bounds, current objects
- [ ] User clicks on grid cell → object picker → color/scale tweaks
- [ ] UI writes to `world.json`; preview instant

### Phase 4: Procedural + Community
- [ ] World template library (empty grid, starter grids)
- [ ] Share/import worlds via grid coordinate JSON
- [ ] Marketplace integration

## Constraints & Frozen Boundaries

**Do NOT modify:**
- `Engine/camera_math.py` — off-axis frustum is frozen
- `grid_bounds`, `grid_divisions`, `grid_depth` — coordinate space is locked
- `primary_mesh` value (`"room"` for grid) — structure is frozen

**Safe to modify:**
- `placeable_objects[]` — add/remove assets
- Per-object properties: position, color, scale, rotation, model path
- `grid_color`, `clear_color` — aesthetics only

## Testing & Validation

**Headless sim needed:** `Scripts/validation/sim_grid_api.py`
- Verify objects load correctly at grid positions
- Verify grid-to-world coordinate transform
- Verify frozen boundaries are respected

**Manual testing:**
- Hand-edit `world.json`, add objects, verify render
- Test hot-reload: change world.json file while daemon runs
- Test boundary violation: place object outside grid_bounds → should reject or clamp

## References

- [[world-system]] — world JSON schema (parent)
- [[grid_room]] — the grid room world definition
- [[design-decisions]] — immutability principle
- [[constraints]] — frozen physics/camera rules
- [[productification]] — commercial world-building path
