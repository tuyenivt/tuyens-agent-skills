---
name: unity-2d-rendering
description: Set up Unity 2D rendering for mobile - sprite atlases and batching, sorting layers, URP 2D lights, tilemaps, pixel-perfect camera, overdraw control.
metadata:
  category: mobile
  tags: [unity, 2d, sprites, atlas, sorting, urp, tilemap, camera, overdraw, batching]
user-invocable: false
---

# Unity 2D Rendering

> This skill owns **how 2D visuals are composed and submitted to the GPU**. Frame budget measurement and the profiler-first workflow belong to `unity-performance`; UI Toolkit panels and screen layout belong to `unity-ui-patterns`; when a renderer is created and destroyed belongs to `unity-monobehaviour-lifecycle`; what the board looks like as data belongs to `unity-2d-gameplay-patterns`.

## When to Use

- Setting up sprites, atlases, sorting, or the camera for a 2D game
- Draw calls, batches, or fill rate appear in a profile
- Sprites render in the wrong order or flicker between frames
- Adding 2D lights, tilemaps, or a pixel-art presentation

## Rules

- **Two batchers apply.** On URP 2D, sprite and SpriteShape renderers on the stock Sprite-Lit/Unlit shaders, and tilemaps in SRP Batch mode, go through the SRP Batcher, which groups consecutive draws by shader variant across materials and cuts per-draw state cost. Merging sprites into fewer draws (dynamic sprite batching, the fallback path) needs a shared material and texture - in practice atlas membership. The Frame Debugger names which batcher ran and why a batch broke
- Sorting is decided by sorting layer, then order-in-layer, then distance to camera. Fix draw order with the first two; leave Z at a constant for a 2D game unless the camera is perspective
- A multi-sprite entity that must sort as a unit carries a `SortingGroup`. Per-child order-in-layer does not survive interleaving with other entities
- Ties in the full sort key are resolved by the renderer's internal order, which is not stable across frames or scene loads. Never leave two overlapping sprites on an identical layer and order
- Orthographic size is half the visible world height. Design a safe world rectangle the board must fit, and derive the size from it and the current aspect - never a constant
- Every transparent sprite costs fill rate whether or not it is visible behind another. On mobile, overdraw is the fill-rate ceiling, not triangle count
- Material property changes made per-instance break batching. `MaterialPropertyBlock` is not the fix: on a Scriptable Render Pipeline, calling `SetPropertyBlock` removes SRP Batcher compatibility for that renderer, and the dynamic batcher will not merge renderers with differing blocks either. Prefer a per-vertex or built-in channel the batch already carries (`SpriteRenderer.color`), or accept a shared variant, and measure

## Patterns

### Atlases and what actually batches

Sprite Atlas (an engine asset type; the 2D Sprite package adds the Sprite Editor) packs loose sprites into one texture at build time. The payoff is batching and fewer texture binds. On 6000.3 the Editor's Sprite Atlas Mode defaults to **Sprite Atlas V2 - Enabled**; V1 is deprecated and the migration to V2 is one-way, so treat a project still pinned to V1 in Project Settings > Editor as a finding.

```
// Bad - each UI icon and each tile a separate texture; every distinct sprite is its own batch
Assets/Art/Icons/*.png  (no atlas)

// Good - one atlas per screen or per logical group; the group draws in one batch
Assets/Art/Atlases/Gameplay.spriteatlasv2   <- board tiles, effects
Assets/Art/Atlases/MetaUI.spriteatlasv2     <- menu and HUD art
```

Group by **what appears on screen together**, not by folder. An atlas containing gameplay tiles plus rarely-shown menu art loads the whole page into memory for either use.

Constraints worth knowing before committing to a layout:

- A sprite in two atlases is packed twice and wastes that memory; keep membership exclusive
- Atlas size is capped by the platform's max texture size; oversize atlases split into multiple pages and lose the single-batch benefit
- Tight packing saves space but the generated mesh has more vertices than a quad. For small icons, full-rect is often cheaper overall
- Compression format is per-platform (ASTC on modern Android/iOS). Set it per-atlas rather than accepting the default, and verify in the build report

A sprite drawn between two atlased sprites from a *different* atlas breaks the batch in three. Draw-order interleaving is as much a batching concern as material assignment.

### Sorting: layers, order, and Z

| Mechanism | Use for | Note |
| --- | --- | --- |
| Sorting Layer | coarse bands: Background, Board, Pieces, Effects, Overlay | project-wide, ordered list in Tags and Layers |
| Order in Layer | ordering within a band | signed int; leave gaps (10, 20, 30) so insertions do not renumber |
| Z position | avoid in 2D | affects orthographic sort but not layout; a stray Z is invisible until it reorders something |

```csharp
// Bad - fights the layer system with transform Z, which nothing else in the project reads
transform.position = new Vector3(x, y, -0.01f * row);

// Good - the intent is explicit and visible in the inspector
spriteRenderer.sortingLayerName = "Pieces";
spriteRenderer.sortingOrder = row * 10;
```

For a top-down board where nearer rows must overlap farther ones, derive order-in-layer from the grid row using the same coordinate convention the rules layer uses (`unity-2d-gameplay-patterns`). Deriving it from world Y instead invites float ties. Units that move between rows re-derive their order when the row changes. For continuous Y sorting, put them on one shared sorting layer and order and set the 2D Renderer's Transparency Sort Mode to Custom Axis (0, 1, 0) - the axis only breaks ties within a layer and order, so it replaces the row-derived order rather than combining with it.

### SortingGroup for composite entities

A piece made of body plus outline plus badge has three renderers. Without grouping, another entity's sprite can render between them.

```csharp
// Bad - child order-in-layer is global; a neighbouring piece interleaves
// Piece/Body (order 10), Piece/Badge (order 12), Neighbour/Body (order 11) -> neighbour draws between body and badge

// Good - the group sorts as one unit; children sort only against each other
[RequireComponent(typeof(SortingGroup))]   // UnityEngine.Rendering, on the Piece root
public class PieceView : MonoBehaviour { }
```

`SortingGroup` is a real cost: it forces its subtree into a separate sorting decision and can break batching with surrounding sprites. Add it to composite entities that visibly need it, not to every prefab.

### 2D lights under URP

2D lights require the URP 2D Renderer (Renderer 2D asset) to be the assigned renderer; with the Universal Renderer they do nothing. Verify the pipeline asset before debugging a light that is not appearing.

Cost model on mobile, in rough order:

| Feature | Mobile cost |
| --- | --- |
| Global light 2D | cheap; usually one per blend-style layer |
| Spot light 2D (formerly Point) | per-light extra draw over affected sprites; watch the count |
| Shadow casters 2D | expensive; each caster adds geometry and a pass |
| Multiple blend styles | each active style is a separate render target |

Blend styles are configured on the Renderer 2D asset, which holds at most **four**; every 2D light picks one of them. Each style that is actually in use costs a render target, so the lever is using fewer of the four, not how many are defined - two is enough for most effects. For a casual 2D puzzle game, a single global light plus baked highlights in the art is usually the correct answer, and lit sprites need the Sprite-Lit material; unlit sprites ignore 2D lights entirely.

### Tilemaps

Tilemap renders in chunks. The relevant knobs:

- **Chunk Culling Bounds**: tiles whose visual extends past the chunk (tall props, glow) get culled while still on screen. Extend the bounds rather than disabling culling
- **Mode: SRP Batch, Chunk, or Individual**: under URP choose SRP Batch, the SRP Batcher-compatible mode; Chunk builds one mesh per chunk and is not SRP Batcher-compatible; Individual is needed only when per-tile sort order matters and costs a draw call per tile
- Tiles from one Tile Palette should share one atlas, otherwise a chunk splits into several batches
- Rebuilding a large tilemap at runtime (`SetTile` in a loop) is a main-thread cost; use `SetTiles` with a bulk array, or `SetTilesBlock`, for bulk edits

For a fixed-size puzzle board, a tilemap is often more machinery than a pooled grid of `SpriteRenderer`s. Choose tilemap for authored levels and large scrolling worlds; choose sprites for a board the rules layer already indexes.

### Camera and resolution independence

```csharp
// Bad - assumes a 16:9 device; tall phones crop the board, tablets show empty margin
cam.orthographicSize = 5f;

// Good - the safe world rectangle fits on both axes at the current aspect
var sizeForHeight = safeWorldHeight * 0.5f;
var sizeForWidth = safeWorldWidth / cam.aspect * 0.5f;
cam.orthographicSize = Mathf.Max(sizeForHeight, sizeForWidth);
```

Design a **safe world rectangle** the board must fit; the larger of the two sizes guarantees both axes. Recompute on resolution change, not only at `Start` - device rotation, split-screen, and desktop window resize all change `camera.aspect`.

For pixel art, add the Pixel Perfect Camera component (Reference Resolution plus Assets Pixels Per Unit) and let it own orthographic size; a manual size assignment fights it and produces shimmer. Its Grid Snapping (None, Pixel Snapping, Upscale Render Texture) and Crop Frame settings trade sharpness against letterboxing - set them deliberately rather than leaving the defaults. Pixel-art sprites import with Filter Mode Point, Compression None, and one Pixels Per Unit across the project.

World-space versus screen-space: gameplay elements that must align to the board live in world space and move with the camera. HUD, popups, and menus belong to UI Toolkit (`unity-ui-patterns`), not to world-space sprites positioned by unprojecting screen coordinates.

### Overdraw

Overdraw is the mobile fill-rate killer in 2D, because transparent sprites cannot be depth-rejected and every layer is shaded for every covered pixel.

```
// Bad - 5 full-screen transparent layers over the board = 5x fill on every pixel
Background + Vignette + Gradient + ParticleSheet + DimPanel

// Good - flatten static layers into one authored background; dim only when a modal is open
```

Practical reductions, cheapest first:

- Delete or bake full-screen transparent overlays that never change
- Disable, do not just fade to alpha 0 - a fully transparent sprite still costs fill
- Trim sprite alpha borders (tight mesh in the sprite editor) so the quad is not mostly empty
- Cap particle overdraw with fewer, larger, shorter-lived particles rather than many stacked ones
- Use the Rendering Debugger's overdraw visualisation to find the layers, rather than guessing

`unity-performance` owns whether overdraw is actually your bottleneck; this skill owns what to do once it is.

### Material and shader variants

```csharp
// Bad - allocates (and leaks) a material instance per sprite and breaks dynamic sprite batching
spriteRenderer.material.color = tint;

// Also bad under URP - SetPropertyBlock removes SRP Batcher compatibility for this renderer
var mpb = new MaterialPropertyBlock();
mpb.SetColor(ColorId, tint);   // ColorId = Shader.PropertyToID("_Color"), cached
spriteRenderer.SetPropertyBlock(mpb);

// Good - a built-in per-renderer channel the sprite batch already carries
spriteRenderer.color = tint;
```

`renderer.material` instantiates on access; `renderer.sharedMaterial` does not. Cache shader property IDs (`Shader.PropertyToID`) rather than passing strings per call. For a simple tint, `SpriteRenderer.color` is the batch-safe path and needs neither a material copy nor a property block. When a per-instance value genuinely has no built-in channel, confirm the cost in the Frame Debugger rather than assuming the block is free.

Keyword variants multiply shader compilation and can stall on first use. For casual 2D, one sprite shader with a small fixed feature set beats a variant per effect.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {Batching | AtlasLayout | ImportSettings | SortingOrder | SortingGroup | Lighting2D | Tilemap | CameraFit | Overdraw | MaterialVariant}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation of code, a component setting, or an asset configuration | not supplied}
- Impact: {what it costs - "board cropped on 20:9 devices", "5x full-screen overdraw"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = content unreachable or illegible on a supported device (board cropped, sprites invisible), or a frame-rate collapse traced to this cause. High = a visible rendering artifact under normal play (wrong or flickering draw order, pixel shimmer, tiles culled on screen), or a measurable fill-rate or draw-call cost on the primary mobile tier. Medium = an inefficiency with headroom to absorb it. Low = a convention or maintainability nit. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: whether overdraw is the measured bottleneck -> unity-performance`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No rendering findings.` |
| A review was requested with nothing to judge | `Rendering check not run: no source supplied.` |

## Avoid

- Loose sprites where an atlas would batch them
- One atlas mixing gameplay and menu art
- Transform Z used to order 2D sprites
- Two overlapping sprites sharing a sorting layer and order
- `SortingGroup` added to every prefab by default
- 2D lights or shadow casters added without checking the Renderer 2D asset is assigned
- Tilemap chunk culling left at default when tiles overflow their cell
- `orthographicSize` set to a constant
- Manual orthographic size assignment alongside Pixel Perfect Camera
- Full-screen transparent overlays stacked and left enabled at alpha 0
- `renderer.material` touched at runtime for a tint
- Shader property names passed as strings per frame
