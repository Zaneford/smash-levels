---
name: extract-levels
description: Extract ES futures trading levels from a Smashelito Substack daily plan and emit them as strict JSON. Use this skill whenever you are given a newsletter.smashelito.com post URL, an "ES Daily Plan" post, or asked to pull Smashlevel / UT / DT / FUT / FDT values out of a market newsletter. Always use this skill for that task rather than reading the post ad hoc — the post contains stale prices, other instruments, and embedded promo text that will corrupt a naive read.
---

# Extract Smashelito Levels

You are extracting trading levels that will be drawn on a live chart and
traded against. A wrong number is worse than no number.

**When unsure, set `confidence` to `low` and explain. That is a success,
not a failure.** A flagged post gets a human read in two minutes. A
confidently wrong level gets traded.

## Input

The post text is in post.txt in the repository root. Read it with the Read tool. It is plain text converted from HTML, so expect navigation and footer cruft around the article body.

## Output

Write **only** `levels.json` to the repo root. No commentary, no other
files, no code. Just the JSON.

```json
{
  "plan_type": "daily",
  "plan_date": "2026-09-10",
  "smashlevel": 7654,
  "upside": [
    {"label": "UT1", "price": 7672},
    {"label": "UT2", "price": 7691},
    {"label": "FUT", "price": 7711}
  ],
  "downside": [
    {"label": "DT1", "price": 7633},
    {"label": "DT2", "price": 7610},
    {"label": "FDT", "price": 7589}
  ],
  "vix": [17.26, 15.64],
  "extras": [],
  "cross_check": "pass",
  "confidence": "high",
  "notes": ""
}
```

## Where the levels live

Two places in every post, and you must read **both**:

1. **The anchor paragraph.** Begins `In terms of levels, the Smashlevel
   is...` (sometimes `is at`). Runs through the upside and downside chains
   with labels in parentheses.
2. **The terminal bullet block.** Begins `Going into tomorrow's session,
   I'll closely observe the behavior around X`, then one bullet per
   direction, then a VIX line.

Take the values from **the bullet block**. Use the paragraph for the
labels and for cross-checking.

## Never read anything else

The body is full of numbers that are not tomorrow's levels:

- **The recap section** reviews today's session and is dense with stale
  prices, prior-day levels, and gap fills. Ignore all of it.
- **Other instruments.** NQ (5-digit), SPX and SPY (lower than ES), VIX
  (2 decimals, 10-30 range). Only VIX belongs in output, from its own line.
- **The promo card.** Every daily embeds `digest-post-embed` markup
  containing the *weekly* plan's title and blurb. It is not this post's
  content.
- **The boilerplate.** The "for new subscribers" paragraph explains what
  FUT and FDT mean. It contains no prices for today.

Sanity filter: **discard any candidate more than 10% from the Smashlevel.**
That single rule removes NQ, SPX, and most recap noise.

## Format variation you must handle

Verified across 16 months of posts. All of this is normal:

**Two or three levels per side, not always three.** Sometimes a side runs
UT1 → FUT with no UT2. Emit what is there. Do not invent a middle level.

**Verb phrasing flips by directional bias.** "Break and hold above" and
"Holding above" both appear, as do both downside forms. Meaning is
identical; parse on structure, not wording.

**A level can be a zone.** e.g. a final target given as a support area
between 5815 and 5806. Emit it with both bounds:

```json
{"label": "FDT", "price": 5815, "price_low": 5806}
```

The bullet block expands zones into two slash-separated numbers, so
bullet count will exceed label count on those days. Expected.

**Compressed ranges.** `6809-12` means 6809 to 6812. Expand it:
`{"price": 6812, "price_low": 6809}`.

**Mixed precision.** 5979.25 and 6893.75 are real. Never round.

**Combined-day posts.** A title like `ES Daily Plan | September 7/8, 2026`
covers two sessions. Use the **last** date for `plan_date`.

**Abnormal days.** Occasionally he gives a Smashlevel with no standard
target chain, usually after a violent session. Emit what exists, set
`confidence` to `low`, and say so in `notes`.

## Cross-check

Compare paragraph values against bullet values.

- Match within **2 points** → `cross_check: "pass"`.
- A paragraph value with no bullet counterpart, or a gap over 2 points →
  `cross_check: "fail"`, `confidence: "low"`, both values in `notes`.

Do **not** demand exact equality. He has typo'd his own post (prose 6809-12
vs bullet 6808-12). The tolerance absorbs that; a strict check would throw
a false alarm on a perfectly readable post.

The paragraph is often a subset of the bullets — bullets can extend past
where the prose stops. That is fine and is not a failure.

## Extras

`extras` is for context worth surfacing that isn't part of the standard
chain: composite profile VPOCs, HTF levels, weekly extremes, roll gaps,
naked POCs, single prints, anything he calls out as significant.

```json
{"label": "Composite VPOC", "price": 7640, "why": "he flags it as the magnet if 7654 fails"}
```

Judgment call, and it's why you're reading this rather than a regex.
Include it if a trader would want it on the chart. Skip vague commentary.
Extras never affect `cross_check` or `confidence` — they are additive.
When in doubt, include it; extras land in a separate block and the human
reviews them.

## Confidence

`high` only when **all** of:

- The anchor paragraph and bullet block were both found
- `cross_check` is `pass`
- Every price survives the 10% filter
- At least one level exists per side
- `plan_date` is unambiguous

Otherwise `low`, with a specific reason in `notes`. "Wording differed from
the usual template and I could not locate the bullet block" is a useful
note. "Something seemed off" is not.

Never emit `confidence: "high"` to be helpful. Downstream validation
refuses to write anything below `high`, and that refusal is the safety
mechanism working.
