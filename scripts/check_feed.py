#!/usr/bin/env python3
"""Poll the Substack feed and decide whether there is anything new to do.

Runs on a schedule, before the extraction step. Everything expensive
happens downstream of this, so the cost of a scheduled run that finds
nothing is one HTTP request.

Writes to GITHUB_OUTPUT:
    skip=true|false
    url=<post url>
    title=<post title>
    reason=<why, for the log>
"""

import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

FEED = "https://newsletter.smashelito.com/feed"
PREFIX = "ES Daily Plan"
UA = "Mozilla/5.0 (compatible; smash-levels/1.0)"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def emit(skip, reason, url="", title=""):
    print(f"{'SKIP' if skip else 'RUN '}: {reason}")
    if url:
        print(f"  url:   {url}")
    if title:
        print(f"  title: {title}")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as fh:
            fh.write(f"skip={'true' if skip else 'false'}\n")
            fh.write(f"url={url}\n")
            fh.write(f"title={title}\n")
            fh.write(f"reason={reason}\n")
    sys.exit(0)


def get(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def plan_date_from_title(title):
    """'ES Daily Plan | September 17, 2026' -> '2026-09-17'.

    Combined-day posts ('September 7/8, 2026') use the LAST date, since
    that is the session the levels apply to.
    """
    m = re.search(r"([A-Za-z]+)\s+([\d/]+),\s*(\d{4})", title)
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return None
    day = m.group(2).split("/")[-1]
    try:
        return f"{int(m.group(3)):04d}-{month:02d}-{int(day):02d}"
    except ValueError:
        return None


def last_written_date():
    """Ask the sheet endpoint what plan_date it last wrote. None on any
    failure -- a probe that cannot answer must not block the run."""
    base = os.environ.get("SHEET_WEBHOOK_URL")
    secret = os.environ.get("SHEET_WEBHOOK_SECRET")
    if not (base and secret):
        return None
    try:
        q = urllib.parse.urlencode({"secret": secret})
        body = get(f"{base}?{q}", timeout=30).decode()
        import json
        return json.loads(body).get("plan_date") or None
    except Exception as e:                      # noqa: BLE001
        print(f"note: freshness probe failed ({e}); continuing")
        return None


# --- Fetch the feed ---------------------------------------------------

try:
    raw = get(FEED)
except urllib.error.URLError as e:
    # A genuine failure. Exit non-zero so the run goes red and emails you --
    # a feed we cannot reach is exactly the silent failure to catch.
    print(f"::error::Could not fetch the feed: {e}")
    sys.exit(1)

try:
    root = ET.fromstring(raw)
except ET.ParseError as e:
    print(f"::error::Feed is not valid XML: {e}")
    sys.exit(1)

items = root.findall(".//item")
if not items:
    print("::error::Feed contained no items.")
    sys.exit(1)

print(f"Feed returned {len(items)} items. Newest few:")
for it in items[:4]:
    t = (it.findtext("title") or "").strip()
    print(f"  - {t}")


# --- Pick the newest daily plan ---------------------------------------
# Substack orders newest first. Only the newest item is considered: if a
# daily plan is not at the top, it has already been handled or superseded.

newest = items[0]
title = (newest.findtext("title") or "").strip()
url = (newest.findtext("link") or "").strip()

if not title.startswith(PREFIX):
    emit(True, f"newest post is not a daily plan ({title!r})")

if not url:
    emit(True, "newest item had no link")

plan_date = plan_date_from_title(title)
if not plan_date:
    # Unparseable title but right prefix -- let it through rather than
    # silently skipping a real post over a formatting change.
    emit(False, f"could not parse a date from {title!r}; running anyway",
         url, title)

last = last_written_date()
print(f"plan_date from title: {plan_date}   last written: {last}")

if last and last == plan_date:
    emit(True, f"{plan_date} already written")

emit(False, f"new daily plan for {plan_date}", url, title)
