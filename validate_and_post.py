#!/usr/bin/env python3
"""Validate extracted levels and POST them to the Apps Script endpoint.

This runs OUTSIDE the agent's turn on purpose. The model decides what the
levels are; this decides whether they are structurally sane before they
reach a chart. Any failure exits non-zero, which fails the workflow, which
emails you.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

# --- Config -----------------------------------------------------------

BAND = 0.10          # reject any price >10% from the smashlevel
MAX_ZONE_WIDTH = 40  # a "zone" wider than this is a misparse, not a zone
COLOR = "yellow"
ALIGN = 1            # 1 = left, matching the current sheet

# label -> (line type, width).  0 line / 1 dash / 2 dot / 3 dash-dot
STYLE = {
    "SMASH": (1, 3),
    "UT1":   (2, 2),
    "UT2":   (3, 2),
    "FUT":   (0, 3),
    "DT1":   (2, 2),
    "DT2":   (3, 2),
    "FDT":   (0, 3),
}
EXTRA_STYLE = (4, 1)  # dash-dot-dot, thin -- visually distinct from the chain

UP_LABELS = {"UT1", "UT2", "UT3", "FUT"}
DOWN_LABELS = {"DT1", "DT2", "DT3", "FDT"}


def die(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def warn(msg):
    print(f"::warning::{msg}")


# --- Load -------------------------------------------------------------

path = sys.argv[1] if len(sys.argv) > 1 else "levels.json"
if not os.path.exists(path):
    die(f"{path} not found -- the extraction step produced nothing.")

try:
    with open(path) as fh:
        d = json.load(fh)
except json.JSONDecodeError as e:
    die(f"{path} is not valid JSON: {e}")

print(json.dumps(d, indent=2))


# --- Gate on the model's own verdict ----------------------------------

if d.get("plan_type") != "daily":
    print(f"plan_type is {d.get('plan_type')!r}, not daily. Nothing to do.")
    sys.exit(0)

if d.get("confidence") != "high":
    die(f"Confidence {d.get('confidence')!r}. Notes: {d.get('notes') or '(none)'}")

if d.get("cross_check") != "pass":
    die(f"Cross-check failed. Notes: {d.get('notes') or '(none)'}")


# --- Structural checks ------------------------------------------------

try:
    plan_date = datetime.strptime(d["plan_date"], "%Y-%m-%d").date()
except (KeyError, ValueError, TypeError):
    die(f"plan_date missing or not YYYY-MM-DD: {d.get('plan_date')!r}")

# Levels are for an upcoming session. Anything far in the past means we
# processed the wrong post -- a stale feed item, or a bad manual replay.
drift = (plan_date - date.today()).days
if drift < -5:
    die(f"plan_date {plan_date} is {abs(drift)} days stale. Refusing to write.")
if drift > 7:
    die(f"plan_date {plan_date} is {drift} days in the future. Refusing to write.")

smash = d.get("smashlevel")
if not isinstance(smash, (int, float)) or smash <= 0:
    die(f"smashlevel is not a positive number: {smash!r}")

lo_bound, hi_bound = smash * (1 - BAND), smash * (1 + BAND)

up = d.get("upside") or []
down = d.get("downside") or []
if not isinstance(up, list) or not isinstance(down, list):
    die("upside/downside must be lists.")
if not up and not down:
    die("No levels on either side.")
if not up or not down:
    warn("Only one side has levels. Unusual but not impossible -- writing anyway.")
if len(up) > 4 or len(down) > 4:
    die(f"Too many levels ({len(up)} up, {len(down)} down). Expected 1-4 per side.")


def check(item, side, allowed):
    label = item.get("label")
    if label not in allowed:
        die(f"Unexpected {side} label {label!r}. Allowed: {sorted(allowed)}")

    price = item.get("price")
    if not isinstance(price, (int, float)):
        die(f"{label}: price is not a number: {price!r}")
    if not (lo_bound <= price <= hi_bound):
        die(f"{label} at {price} is outside +/-{BAND:.0%} of {smash}. "
            f"Likely NQ, SPX, or a recap price.")

    low = item.get("price_low")
    if low is not None:
        if not isinstance(low, (int, float)):
            die(f"{label}: price_low is not a number: {low!r}")
        if not (lo_bound <= low <= hi_bound):
            die(f"{label} zone bound {low} is outside the band.")
        if low > price:
            price, low = low, price          # tolerate reversed bounds
            item["price"], item["price_low"] = price, low
        if price - low > MAX_ZONE_WIDTH:
            die(f"{label} zone spans {price - low} pts (max {MAX_ZONE_WIDTH}). "
                f"Probably two separate levels merged.")
    return label


for it in up:
    check(it, "upside", UP_LABELS)
for it in down:
    check(it, "downside", DOWN_LABELS)

# Directional sanity. Catches an inverted parse instantly.
for it in up:
    if it["price"] <= smash:
        die(f"Upside {it['label']} at {it['price']} is not above smashlevel {smash}.")
for it in down:
    if it["price"] >= smash:
        die(f"Downside {it['label']} at {it['price']} is not below smashlevel {smash}.")

# Ordering within each chain.
for seq, name in ((up, "upside"), (down, "downside")):
    prices = [i["price"] for i in seq]
    ordered = sorted(prices, reverse=(name == "downside"))
    if prices != ordered:
        warn(f"{name} levels are not monotonic: {prices}. Writing anyway.")


# --- Build rows -------------------------------------------------------
# Price | Price 2 | Note | Color | Line Type | Line Width | Text Alignment

rows = []


def row(price, low, note, style):
    lt, lw = style
    rows.append([price, low if low is not None else "", note,
                 COLOR, lt, lw, ALIGN])


row(smash, None, f"SMASH {plan_date.month}/{plan_date.day}", STYLE["SMASH"])
for it in up + down:
    row(it["price"], it.get("price_low"), it["label"], STYLE[it["label"]])

for ex in (d.get("extras") or []):
    p = ex.get("price")
    if isinstance(p, (int, float)) and lo_bound <= p <= hi_bound:
        row(p, ex.get("price_low"), str(ex.get("label", "EXTRA"))[:24], EXTRA_STYLE)
    else:
        warn(f"Dropped out-of-band extra: {ex}")

print(f"\n{len(rows)} rows for {plan_date}:")
for r in rows:
    print("  " + ",".join(str(c) for c in r))

if (d.get("vix") or []):
    print(f"\nVIX levels (not written to sheet): {d['vix']}")


# --- Post -------------------------------------------------------------

if os.environ.get("DRY_RUN", "").lower() == "true":
    print("\nDRY_RUN set. Not writing to the sheet.")
    sys.exit(0)

url = os.environ.get("SHEET_WEBHOOK_URL")
secret = os.environ.get("SHEET_WEBHOOK_SECRET")
if not url or not secret:
    die("SHEET_WEBHOOK_URL / SHEET_WEBHOOK_SECRET not set.")

payload = json.dumps({
    "secret": secret,
    "plan_date": plan_date.isoformat(),
    "rows": rows,
}).encode()

req = urllib.request.Request(
    url, data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode()
except urllib.error.HTTPError as e:
    die(f"Sheet endpoint returned {e.code}: {e.read().decode()[:400]}")
except urllib.error.URLError as e:
    die(f"Could not reach sheet endpoint: {e.reason}")

print(f"\nResponse: {body}")

try:
    result = json.loads(body)
except json.JSONDecodeError:
    die("Sheet endpoint did not return JSON. Check the deployment is set to "
        "'Anyone' access and redeploy after any code change.")

if result.get("status") == "duplicate":
    print(f"Already written for {plan_date}. No change.")
    sys.exit(0)
if result.get("status") != "ok":
    die(f"Sheet write failed: {result}")

print(f"Wrote {result.get('rows')} rows for {plan_date}.")
