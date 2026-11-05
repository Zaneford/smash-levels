#!/usr/bin/env python3
"""Fetch the post text from the Substack email, via the Apps Script endpoint.

Replaces the old curl-the-webpage step. As of October 2026 both the web
page and the RSS body are gated to subscribers, but the email Substack
sends is complete -- and Apps Script already runs as the account that
receives it.

Writes post.txt. Exits non-zero (failing the run, which emails you) on
anything unexpected.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

base   = os.environ.get("SHEET_WEBHOOK_URL", "")
secret = os.environ.get("SHEET_WEBHOOK_SECRET", "")
title  = os.environ.get("POST_TITLE", "").strip()

if not base or not secret:
    print("::error::SHEET_WEBHOOK_URL / SHEET_WEBHOOK_SECRET not set.")
    sys.exit(1)

if not title:
    print("::error::No post title supplied; the email is located by subject.")
    sys.exit(1)

print(f"Looking for the email with subject: {title!r}")

query = urllib.parse.urlencode({
    "secret": secret,
    "mode": "post",
    "subject": title,
})
req = urllib.request.Request(
    f"{base}?{query}",
    headers={"User-Agent": "smash-levels/1.0"},
)

try:
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
except urllib.error.HTTPError as e:
    print(f"::error::Mail endpoint returned {e.code}: {e.read().decode()[:300]}")
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"::error::Could not reach the mail endpoint: {e.reason}")
    sys.exit(1)

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("::error::Endpoint did not return JSON. Check the deployment is set "
          "to 'Anyone' access and was redeployed as a NEW VERSION.")
    print(raw[:300])
    sys.exit(1)

if data.get("error"):
    print(f"::error::{data['error']}")
    sys.exit(1)

body = data.get("body") or ""

if len(body) < 500:
    print(f"::error::Only {len(body)} chars returned -- the email looks "
          f"truncated or empty.")
    print(body[:300])
    sys.exit(1)

with open("post.txt", "w", encoding="utf-8") as fh:
    fh.write(body)

print(f"{len(body)} chars written to post.txt")
print("--- first 400 chars " + "-" * 40)
print(body[:400])
