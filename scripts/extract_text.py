#!/usr/bin/env python3
"""Convert post.html to plain post.txt.

Deliberately dumb and deterministic. The model reads verbatim text; no
summarisation layer sits between the page and the extraction, which is
what caused the embellished-numbers problem when this used WebFetch.
"""

import html
import re
import sys

try:
    raw = open("post.html", encoding="utf-8", errors="replace").read()
except FileNotFoundError:
    print("::error::post.html not found -- the fetch step produced nothing.")
    sys.exit(1)

raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
raw = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</h[1-6]>", "\n", raw)
txt = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
txt = re.sub(r"[ \t]+", " ", txt)
txt = re.sub(r"\n\s*\n+", "\n\n", txt).strip()

if len(txt) < 500:
    print(f"::error::Only {len(txt)} chars of text extracted. "
          f"The page was probably a block page or an error.")
    sys.exit(1)

open("post.txt", "w", encoding="utf-8").write(txt)
print(f"{len(txt)} chars written")
print("--- first 400 chars " + "-" * 40)
print(txt[:400])
