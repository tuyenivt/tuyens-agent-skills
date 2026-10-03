---
name: unity-game-economy-progression
description: Model idle and tower-defense economies - offline progress, clock-tamper limits, big-number overflow, prestige loops, data-driven balance.
metadata:
  category: mobile
  tags: [unity, idle, economy, progression, offline-progress, bignumber, balance, scriptableobject, clock]
user-invocable: false
---

# Unity Game Economy and Progression

> This skill owns **currency, progression, and time-based accrual math**. The `IClock` seam and the engine-free rules boundary belong to `unity-architecture-patterns`; board and turn resolution belongs to `unity-2d-gameplay-patterns`; storing and migrating the save belongs to `unity-save-persistence`; server-side receipt validation and anti-tamper enforcement belong to `unity-security-patterns`; import pipelines for large content banks belong to `unity-content-data`.

## When to Use

- Adding offline progress, idle accrual, or timed rewards
- Balancing currency sources against sinks, or a prestige/soft-reset loop
- Numbers exceed what `long` or `double` represents accurately
- Scaling tower-defense waves, costs, or difficulty
- Reviewing economy code for tamper resistance or overflow

## Rules

- **Wall-clock time is untrusted input.** Any grant computed from `DateTime.Now` or `DateTime.UtcNow` is a value the player controls by changing the device clock. Either validate the elapsed span server-side, or clamp it and accept the residual exploit deliberately
- Elapsed time comes from a substitutable `IClock`, never from a direct `DateTime` or `Time` read inside economy math. Offline math is untestable otherwise
- Monotonic time (`Time.realtimeSinceStartup`, `Stopwatch`) is tamper-resistant but does not survive process death; wall-clock survives but is forgeable. Every offline-progress design picks a combination and states which failure it accepts
- Accrual is computed as a **closed-form function of elapsed time**, not by simulating skipped ticks. A one-week absence must not run a week of steps
- Currency totals that can exceed `double`'s exact-integer range use a big-number representation. It buys range, not exactness: small additions to a huge total still round away, so the UI must not promise them. Silent overflow or a stalled total that should still grow is the failure
- Balance numbers - costs, rates, curve coefficients, wave tables - live in ScriptableObjects or imported data, never as literals in gameplay code
- Every currency has an enumerated set of sources and sinks. A currency with no sink inflates; a sink with no source is dead content

## Patterns

### The clock boundary

The exploit is one line long: set the device clock forward a year, collect a year of idle income, set it back.

| Time source | Survives app kill | Tamper-resistant | Use for |
| --- | --- | --- | --- |
| `DateTime.UtcNow` | yes | no | offline elapsed, when clamped or server-checked |
| `Time.realtimeSinceStartupAsDouble` | no (resets) | yes | in-session timers, cooldowns while running (the `float` version loses precision over long sessions) |
| `Stopwatch` / monotonic OS tick | no | yes | in-session accrual; it pauses while a mobile device sleeps, so it undercounts background time |
| Server timestamp | yes | yes | authoritative grants, anything monetised |

```csharp
// Bad - the device clock is the authority; forward-setting mints currency
var elapsed = DateTime.UtcNow - save.LastSeenUtc;
Grant(rate * elapsed.TotalSeconds);

// Good - bounded; a backward jump grants nothing and is recorded (defence 2)
var raw = _clock.UtcNow - save.LastSeenUtc;
if (raw < TimeSpan.Zero) save.ClockSuspect = true;
var elapsed = raw < TimeSpan.Zero ? TimeSpan.Zero : (raw > MaxOffline ? MaxOffline : raw);
```

Three defences, in increasing strength:

1. **Clamp** to a maximum offline window (a design number anyway - most idle games cap at 2-12 hours). Costs nothing, bounds the exploit to one cap per app launch
2. **Detect clock tampering**: a `LastSeenUtc` in the future, or a wall-clock delta far exceeding the monotonic delta measured while running, marks the save suspicious. Record the flag, degrade the grant, do not silently continue
3. **Server timestamp** for anything with real-money consequence. The server is the only authority a modified client cannot forge; enforcement design belongs to `unity-security-patterns`

Store `LastSeenUtc` in UTC. Local time makes a timezone flight indistinguishable from tampering, and a DST transition mints or destroys an hour.

Write `LastSeenUtc` on pause and focus loss, not only on quit - mobile processes are killed without a quit callback.

### Offline accrual as a closed form

```csharp
// Bad - a week offline runs 604,800 iterations on the main thread at resume
for (var t = 0; t < elapsedSeconds; t++) sim.Step(1f);

// Good - constant time regardless of absence length
var earned = ratePerSecond * elapsedSeconds;
```

Non-linear accrual still has a closed form. Compound growth over elapsed time `t` at rate `r` is `initial * Math.Pow(1 + r, t)`, not a loop. Where a genuinely non-analytic system (a TD wave simulation) must advance, run a **capped** number of coarse steps and state the approximation in the design, rather than an unbounded catch-up.

Offline earnings are conventionally reduced against online earnings (a fraction of the online rate). Put that fraction in the balance data, not in the accrual code.

### Big numbers

`float` is exact only to 2^24 (about 1.7e7) and is never a currency type. `double` represents integers exactly only up to 2^53 (about 9.0e15); `long` overflows at about 9.2e18. Idle games with exponential growth cross both, and the `double` failure is worse because it is silent: additions of small values to a large total simply stop having an effect.

```csharp
// Bad - past 2^53, adding 1 gold rounds to the nearest representable total - here, no change
double gold = 9.1e15;
gold += 1; // gold is unchanged

// Good - range past 1e308 without overflow; still not exact (see below)
public readonly struct BigDouble { public readonly double Mantissa; public readonly int Exponent; }
```

Choose deliberately:

| Range needed | Representation |
| --- | --- |
| below ~9.2e18 | `long`, exact, checked for overflow |
| unbounded exponential growth | mantissa-plus-exponent struct (a `BigDouble`-style type) |
| exact arbitrary precision | `System.Numerics.BigInteger` - correct but allocating; wrong for per-frame math |

Requirements for a mantissa/exponent type, all of which bite in practice: normalise after every operation, define comparison and equality (mantissa comparison after exponent comparison), define a display format (scientific, engineering, or named tiers - K/M/B/T then AA/AB), and make it serialisable in a form that round-trips exactly through the save (`unity-save-persistence`). Write it as a `readonly struct` in the rules assembly so it stays engine-free and allocation-free; Unity's serializer and `JsonUtility` skip `readonly` fields, so the save writes it through a mutable DTO or a custom converter.

Adding a value more than about 16 orders of magnitude below the total is a no-op with a `double` mantissa. That is correct behaviour, not a bug, but the UI must not show a "+1" that never lands.

### Currency, sources, and sinks

Every currency gets an explicit table before any of it is implemented:

| Currency | Sources | Sinks | Resets on prestige |
| --- | --- | --- | --- |
| Soft (coins) | idle accrual, level clear, ad reward | upgrades, retries, cosmetics | yes |
| Hard (gems) | IAP, rare milestones | premium upgrades, skips | no |
| Prestige (stars) | prestige conversion | permanent multipliers | no |

Two rules this table enforces: hard currency earned and hard currency purchased should be tracked separately (refunds, analytics, and regional pricing all need the split), and a currency with no sink is inflation the player will notice within a session.

Grant and spend go through one guarded path:

```csharp
// Bad - negative balances, silent underflow, no audit trail
wallet.Coins -= cost;

// Good - the caller must handle failure, and every mutation has a reason attached
public interface IWallet {
    bool TrySpend(CurrencyId id, BigDouble cost, string reason);
    void Grant(CurrencyId id, BigDouble amount, string reason);
}
```

The `reason` string feeds analytics and makes economy bugs diagnosable.

### Prestige and soft reset

A prestige loop trades current progress for a permanent multiplier. The design points that break implementations:

- **Conversion is a curve, not a ratio.** `stars = floor(k * sqrt(lifetimeEarned / threshold))` and similar sublinear forms keep late resets meaningful without runaway. The formula gives the total a lifetime has earned: each prestige grants that total minus stars already banked, and `lifetimeEarned` (everything ever granted - spending never reduces it) never resets. Put `k` and the threshold in balance data
- **The reset must be an explicit list of what is cleared and what persists**, held as data. An implicit "clear everything except these fields" reset drifts every time a field is added, and the resulting bug destroys player progress
- Preview the exact gain before confirming; an irreversible reset with a surprise result is the top complaint in the genre
- Reset is a save-schema event. Version it and make it idempotent, so an interrupted reset does not double-apply (`unity-save-persistence`)

### Balance as data

```csharp
// Bad - a rebalance is a code change, a rebuild, and a store release
private const float UpgradeCost = 25f * 1.15f;

// Good - authored and tunable without a code change (post-release changes need remote config, below)
[CreateAssetMenu] public sealed class EconomyConfig : ScriptableObject {
    [SerializeField] private double baseCost = 25, growth = 1.15;
    public double CostAt(int level) => baseCost * Math.Pow(growth, level);   // BigDouble past ~9e15
}
```

Format by use:

| Data | Format |
| --- | --- |
| A handful of tunables, designer-edited in the editor | ScriptableObject with serialized fields |
| Wave tables, level tables, hundreds of rows | CSV or JSON imported into a ScriptableObject in the editor, validated on import |
| Values that must change after release | remote config, with the shipped ScriptableObject as the fallback |

Validate on import, not at first use: a wave table with a missing column should fail the import, not produce a null-reference on wave 40 in production. Curve shapes are worth checking too - a cost curve that dips is an infinite-money exploit, and it is cheap to assert monotonicity at import.

Never mutate the ScriptableObject at runtime to hold current progress; that edit persists in the editor and diverges from the build (`unity-architecture-patterns`).

### Difficulty, cost, and wave curves

Three shapes cover nearly all of it:

| Shape | Formula | Fits |
| --- | --- | --- |
| Linear | `base + k * n` | early tutorial pacing, small counts |
| Geometric | `base * r^n` (typically `r` in 1.07-1.15) | upgrade costs, idle income tiers |
| Sublinear | `base * n^p`, `p < 1` | prestige conversion, catch-up bonuses |

The standard idle shape is geometric cost per purchase against income that grows linearly per purchase plus periodic multipliers; the multipliers decide whether progress outpaces cost. Express both in the same balance asset so the relationship is visible rather than emergent.

For tower-defense waves, scale count, health, and reward on separate curves. One shared multiplier makes a wave that is simultaneously unbeatable and unrewarding, and a reward curve that outpaces cost growth trivialises the run. Verify by simulating the curves headlessly in an EditMode test - the rules layer is engine-free, so a hundred waves run in milliseconds.

### Testing economy math

Because accrual takes `IClock` and randomness takes `IRandom` (`unity-architecture-patterns`), the whole economy is testable without Play mode:

```csharp
// Advance a fake clock by a week; assert the grant equals the clamp, not the raw elapsed
var clock = new FakeClock(start); clock.Advance(TimeSpan.FromDays(7));
Assert.AreEqual(MaxOffline.TotalSeconds * rate, Compute(save, clock));
```

Cases worth having: clock moved backwards, clock moved forward past the clamp, elapsed exactly zero, a total near the representation's precision ceiling, and prestige applied twice from the same pre-reset save.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {ClockTrust | OfflineAccrual | NumericPrecision | CurrencyFlow | PrestigeReset | BalanceHardcoding | CurveShape | TimeInjection}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation of code, a config value, or a curve setting | not supplied}
- Impact: {what it allows or breaks - "clock change mints unlimited currency", "totals stop increasing past 9e15"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = a currency grant unbounded, or repeatable at will with no clamp, from player-controllable input, or progress lost on a prestige reset. High = silent precision loss, a spend with no balance check (a negative balance or a free purchase), an offline catch-up that hangs at resume, or a monetised grant computed client-side. Medium = balance hardcoded in code, a curve flaw affecting pacing, or an untestable time read. Low = a naming, structure, or documentation nit in economy data. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: reset save-schema migration -> unity-save-persistence`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No economy findings.` |
| A review was requested with nothing to judge | `Economy check not run: no source supplied.` |

## Avoid

- `DateTime.Now` or `DateTime.UtcNow` read directly inside economy math
- Local time stored as the last-seen timestamp
- Offline elapsed time used unclamped and unchecked
- Backward clock movement producing a negative or absolute elapsed span
- Simulating skipped ticks to catch up an absence
- `float` as a currency type, or `double`/`long` totals in a game with exponential growth
- A mantissa/exponent type without normalisation, comparison, and exact save round-trip
- Direct arithmetic on a currency field instead of a guarded `TrySpend`
- Prestige reset written as "clear everything except" rather than an explicit data-driven list
- Balance constants as literals in gameplay code
- Data tables validated at first use rather than at import
- ScriptableObject balance assets mutated at runtime
- Wave count, health, and reward driven by one shared multiplier
