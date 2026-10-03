---
name: unity-2d-gameplay-patterns
description: Model 2D board and turn games as engine-free C# - pure reversible moves, grid state, cascade termination, seeded RNG, snapshot undo.
metadata:
  category: mobile
  tags: [unity, csharp, gameplay, grid, board, determinism, undo, state-machine, rng]
user-invocable: false
---

# Unity 2D Gameplay Patterns

> This skill owns **rule algorithms and how game state is modelled and advanced**. Where that code lives and the engine-free assembly boundary belong to `unity-architecture-patterns`; drawing the board belongs to `unity-2d-rendering`; reading the player's gesture belongs to `unity-2d-physics-input`; currency and progression math belong to `unity-game-economy-progression`; writing state to disk belongs to `unity-save-persistence`.

## When to Use

- Modelling a board, grid, or turn structure for a puzzle or casual 2D game
- Adding undo/redo, replay, or a daily-seeded puzzle
- Implementing move legality, match detection, or cascade resolution
- Reviewing gameplay code for determinism, mutation, or non-terminating loops

## Rules

- **Every rule in this skill is plain C# with no `UnityEngine` dependency.** Board state, legality, resolution, and scoring compile and run outside the engine. This is the plugin's central constraint, owned by `unity-architecture-patterns`
- A move returns a **new state**; it never mutates the state passed in. Reversibility comes from keeping the previous value, not from writing an inverse operation. This binds move-driven state; a continuous sim advancing on fixed ticks may step one mutable sim state in place - its reproducibility is the seed plus the input log, not snapshots
- A move returns whether it **changed anything**. "No tile moved" is a distinct outcome from "the move was illegal", and both differ from a successful move
- Randomness arrives as an injected seeded source. `UnityEngine.Random` and an unseeded `System.Random` both make a bug unreproducible
- Every resolution loop has a **stated termination bound**. Where termination depends on rule content that can change (a cascade whose refill may re-match), the bound is a counter checked in code; where it is provable from the loop condition itself (a search relaxing strictly decreasing costs), assert the bound in a test instead. An unbounded cascade is a hang, not a slow frame
- Grid indexing uses one documented convention throughout - row-major or column-major, origin corner named, applied identically in rules, input, and rendering
- Validation and application are separate: `IsLegal(state, move)` answers a question, `Apply(state, move)` produces a state. A method that both checks and mutates cannot be used to build a legal-move list

## Patterns

### State as a value, moves as functions

```csharp
// Bad - mutates in place; undo needs a hand-written inverse for every move type
public void SlideLeft() { for (var r = 0; r < 4; r++) CollapseRow(_cells, r); }

// Good - previous state is still intact, so undo is a pop
public readonly struct MoveResult {
    public readonly BoardState Board; public readonly int ScoreGained; public readonly bool Changed;
    public MoveResult(BoardState board, int gained, bool changed) { Board = board; ScoreGained = gained; Changed = changed; }
}
public static MoveResult SlideLeft(in BoardState board) { /* builds a new BoardState */ }
```

Undo/redo becomes two stacks of `BoardState`. Push before applying, pop to undo. A snapshot holds everything a move reads: the generator state is a value inside `BoardState`, and a move returns the advanced state with the new board, or undo-then-redo spawns a different tile. For a 4x4 or 9x9 board a snapshot is tens of bytes, so snapshot-per-move costs less than maintaining inverse operations and cannot drift out of sync with the forward move.

For large boards, store snapshots as the flat backing array only, and reconstruct derived data (score totals, match caches) on restore rather than snapshotting it.

### Board representation

| Board | Representation | Why |
| --- | --- | --- |
| 2048, Sudoku, Match-3 | flat array `T[width * height]`, index `y * width + x` | one allocation, cache-friendly, trivial to copy and hash |
| Chess-like, 64 squares | `ulong` bitboards per piece type plus a mailbox array | set operations and attack masks become single instructions |
| Irregular or sparse board | dictionary keyed by a coordinate struct | only where the rectangle is mostly empty |

`T[,]` (true 2D) is slower to index than a flat array in Unity's IL2CPP builds and cannot be sliced or copied as cheaply. Prefer the flat array with one indexing helper.

**The row-major trap.** `y * width + x` and `x * height + y` are both valid; mixing them silently transposes the board and only shows up on non-square grids. Write one accessor and never compute an index at a call site:

```csharp
// Bad - the convention is re-derived at each call site, and one of them is wrong
var cell = _cells[x * _height + y];

// Good - one definition, one place to be wrong, bounds checked
public int At(int x, int y) =>
    (uint)x < (uint)Width && (uint)y < (uint)Height ? y * Width + x : throw new ArgumentOutOfRangeException();
```

The bounds check lives in the accessor. A silent wrap from `x = -1` reading the previous row's last cell is the classic off-by-one in grid games.

### Turn and phase as an explicit state machine

Game phase is an enum plus a transition table, not a scatter of booleans:

```csharp
// Bad - illegal combinations are representable; input arrives mid-cascade
bool _isAnimating, _isPlayerTurn, _isGameOver;

// Good - exactly one phase is current; input is rejected outside AwaitingInput
enum Phase { AwaitingInput, Resolving, Animating, GameOver }
```

The presentation layer reads the phase to decide whether to accept input. The rules layer advances it. A cascade running while the phase is `AwaitingInput` is the bug this shape prevents.

Animation duration must not gate rule progression: resolve the full move in the rules layer first, then play the resulting animation sequence. Otherwise a skipped or interrupted animation desynchronises the board from the display.

### Genre micro-examples

Each is the rule kernel only - legality, detection, or generation. Everything around it is the same pure-function shape above.

**2048 slide-merge.** Compact non-zero cells toward the wall, then merge equal neighbours once, then compact again. The merge flag is what stops `4 4 4 4` becoming a single `16`:

```csharp
// One row, left: [2,2,4,0] -> compact [2,2,4] -> merge [4,4] -> pad [4,4,0,0]
static int[] SlideRow(int[] row) { /* compact, single-pass merge with a merged flag, compact */ }
```

A tile that merged this move cannot merge again this move. `2 2 4` slides to `4 4`, not `8`.

**Sudoku constraint check.** Legality is three set-membership tests, not a solver:

```csharp
static bool IsLegal(byte[] grid, int index, byte value) =>
    !RowHas(grid, index / 9, value) && !ColHas(grid, index % 9, value)
    && !BoxHas(grid, (index / 27) * 3 + (index % 9) / 3, value);
```

Track occupancy as nine `ushort` bitmasks each for rows, columns, and boxes to make this O(1) and to make generation and hint-solving affordable.

**Chess move generation and legality.** Generation and legality are two stages, and conflating them is the common bug:

```csharp
// Pseudo-legal: piece movement rules only, ignoring self-check
IEnumerable<Move> Pseudo(Position p);
// Legal: apply, then reject if the mover's own king is attacked
bool IsLegal(Position p, Move m) => !IsKingAttacked(Apply(p, m), p.SideToMove);
```

Because `Apply` is pure, the legality filter is a one-liner and needs no make/unmake pair. Castling also needs an attack test before the move: the king may not castle out of, or through, an attacked square. Castling rights, the en passant target, the halfmove clock, and repetition history are position state, not board contents, so they live in `Position` alongside the squares or they are lost on snapshot. Promotion belongs to the move.

**Match-3 detection.** Scan runs, do not compare fixed offsets:

```csharp
// Per row and per column: extend a run while colour matches; emit indices when run >= 3
// Intersecting runs merge into one group, which is how an L or T shape scores as one match
```

Detection returns the matched cell set for the caller to clear. It does not clear, score, or refill - keeping those separate is what makes cascade resolution testable.

### Cascade resolution with a termination guarantee

```csharp
// Bad - a refill rule that can regenerate a match makes this a hang, not a slow frame
while (TryFindMatches(board, out var m)) board = Refill(Clear(board, m));

// Good - bounded, and hitting the bound is reported, not mistaken for a settled board
const int MaxCascades = 32;
var i = 0;
for (; i < MaxCascades && TryFindMatches(board, out var m); i++)
    board = Refill(Clear(board, m));
if (i == MaxCascades && TryFindMatches(board, out _)) ReportCascadeBound(board);   // assert in tests, log in release
```

The bound is not defensive decoration: hitting it means the refill can produce matches indefinitely, which is a rules bug worth surfacing in a test rather than shipping as a freeze. Assert on the bound in tests; log and break in release.

Resolve the whole cascade in the rules layer, producing an ordered list of steps. The presenter then animates that list. Interleaving resolution with animation frames is what makes cascade code both untestable and prone to input arriving mid-chain.

### Seeded randomness and replay

```csharp
// Bad - board differs per device; a reported bug cannot be reproduced
var spawn = UnityEngine.Random.Range(0, free.Count);

// Good - the seed is part of the game state and is saved with it
public readonly struct SeededRandom {   // a value: snapshots copy it, a draw returns the advanced generator
    public readonly ulong State;        // xorshift or PCG state; never 0
    public SeededRandom(ulong state) => State = state == 0 ? 0x9E3779B97F4A7C15UL : state;
}
```

Requirements this buys, all of which are common in the target genres:

- **Daily puzzle**: seed derived from one agreed calendar date (UTC or server-supplied, never the device's local date), e.g. the `yyyyMMdd` integer fed to the generator's seeding; identical board for every player
- **Replay**: seed plus the move list reproduces the game exactly; store those instead of every frame
- **Reproducible bug reports**: seed plus moves is the whole repro

Three constraints. Save the **generator's state**, not just the seed, or a resumed game diverges from the original; give each move a fixed number of draws so a replay can recover the position. `System.Random` exposes no state - resuming it means re-seeding and discarding the number of draws taken, which is not the move count unless every move draws the same number. Do not assume `System.Random`'s sequence is stable across .NET runtime versions - if cross-version reproducibility matters, implement a small explicit PRNG (xorshift, PCG) in the rules assembly so the sequence is yours.

The third only binds when a replay must reproduce on a *different machine* than it recorded on - lockstep multiplayer, a shared daily leaderboard, a replay file opened on another device. Three things desync before the PRNG does: `float`/`Mathf` results can differ across IL2CPP and Mono and across ARM and x64, so rules math is integer or fixed-point; `Dictionary` and `HashSet` iteration order is not part of the .NET contract, so any rule iterating one needs an explicit sort; and `List.Sort` is introsort and unstable, so its comparer must be a total order with no equal elements. A same-device replay is unaffected by all three, given keys with value-based hashes.

### Advancing the loop

Turn-based genres (2048, Sudoku, Chess, quiz) advance on input, not on frames - there is no per-frame simulation to run, and `Update` should only poll for the phase change. Continuous genres (tower defense, idle) advance on a fixed accumulated step so behaviour is frame-rate independent:

```csharp
// Bad - spawn rate and projectile travel vary with device frame rate
void Update() { _sim.Advance(Time.deltaTime); }

// Good - the rules layer takes fixed ticks; the remainder carries to the next frame
_acc += dt; var steps = 0;
while (_acc >= Tick && steps++ < MaxStepsPerFrame) { _sim.Step(Tick); _acc -= Tick; }
```

Cap the number of catch-up steps per frame. `Time.deltaTime` is already clamped to `Time.maximumDeltaTime`, so time lost to a backgrounded app never arrives as one huge `dt` - it is silently dropped. `unity-game-economy-progression` owns the elapsed-time math for anything longer than a frame hitch.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {Mutation | Determinism | Termination | GridIndexing | PhaseModel | EngineCoupling | LegalitySeam | SnapshotIntegrity | RuleLogic}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {what breaks - "undo restores a corrupted board", "cascade can hang the main thread"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

`LegalitySeam` covers a method that both checks and mutates, and a detector that also clears, scores, or refills. `RuleLogic` covers a rule that computes the wrong outcome (a missed vertical run, a double merge).

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = an unbounded resolution loop, or state corruption that survives into a save. High = rules whose outcome varies by device, run, or environment (including seed provenance), in-place mutation defeating undo or replay, `UnityEngine` referenced from a rule, or a rule computing the wrong outcome in normal play (a transposed index included). Medium = a phase-model flaw contained to one screen, or an indexing flaw with no reachable wrong outcome (a missing bounds check behind validated input). Low = a clarity or structure nit with no current behavioural cost. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: rules-assembly asmdef boundary -> unity-architecture-patterns`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No gameplay findings.` |
| A review was requested with nothing to judge | `Gameplay check not run: no source supplied.` |

## Avoid

- Mutating board state in place where undo, replay, or a legal-move list is needed
- `UnityEngine.Random`, `Time.deltaTime`, or `DateTime.Now` inside a rule
- Resolution loops with no bound
- Re-deriving the flat-array index convention at each call site
- Booleans standing in for game phase
- Rule progression gated on animation completion
- Detection methods that also clear, score, or refill
- Saving a seed without the generator's position
- Depending on `System.Random`'s exact sequence for cross-version reproducibility
- Chess position state (castling rights, en passant target) stored outside the snapshotted position
