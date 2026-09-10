# smash-levels

Pulls ES levels from the Smashelito daily plan and writes them to the
Google Sheet the Sierra Chart importer study reads.

```
Substack /feed
  -> Make.com  (RSS trigger -> HTTP request)
  -> GitHub    repository_dispatch: smash-post
  -> Actions   Claude Code reads the post, emits levels.json
  -> Python    validates structure, POSTs rows
  -> Apps Script -> SMASH sheet -> importer study
```

Claude decides *what the levels are*. Python decides *whether they are
sane*. Nothing reaches the sheet without passing both.

---

## Setup

Build in this order. Each step is testable on its own — don't wire the
next one until the current one works.

### 1. Apps Script (~10 min)

1. Open the SMASH sheet → Extensions → Apps Script.
2. Paste `appsscript/Code.gs`. Check `SHEET_NAME` matches your tab.
3. Project Settings → Script Properties → add `SECRET` = a long random
   string. Keep it; you need it again in step 3.
4. Run `testWrite` once. Approve the permission prompt. A row should
   appear in the sheet and vanish two seconds later.
5. Deploy → New deployment → Web app. **Execute as: Me. Access: Anyone.**
   Copy the `/exec` URL.

Test it:

```bash
curl -sS -L -X POST "<EXEC_URL>" -H 'Content-Type: application/json' \
  -d '{"secret":"<SECRET>","plan_date":"2026-09-10","rows":[[7654,"","SMASH 9/10","yellow",1,3,1]]}'
```

Expect `{"status":"ok","rows":1,...}` and a row in the sheet. Run it
again — expect `{"status":"duplicate"}` and no change.

> "Access: Anyone" means anyone with the URL can call it. The secret is
> what actually protects it, which is why it needs to be long and random.

### 2. Repo (~5 min)

Push these files to a **private** repo. Private matters: the URL and
secret live in Actions secrets, and public repos disable scheduled
workflows after 60 days of inactivity (which would kill the heartbeat).

### 3. Secrets

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your API key |
| `SHEET_WEBHOOK_URL` | the `/exec` URL from step 1 |
| `SHEET_WEBHOOK_SECRET` | the `SECRET` from step 1 |

### 4. Test before automating

Actions → Smash Levels → Run workflow. Paste a post URL, tick **dry_run**.

```
https://newsletter.smashelito.com/p/es-daily-plan-september-10-2026
```

Expected: 7654 SMASH, 7672/7691/7711 up, 7633/7610/7589 down.

**Replay at least five past posts before connecting Make.** Include the
awkward ones — this is the only way to find out whether the guards throw
false alarms, and you want to learn that now rather than at 6am:

| Post | Tests |
|---|---|
| `es-daily-plan-september-10-2026` | the known-good baseline |
| `es-daily-plan-may-23-2025` | FDT given as a zone |
| `es-daily-plan-october-24-2025` | `6809-12` range, prose/bullet typo |
| `es-daily-plan-june-16-2025` | 2 levels up, 3 down |
| `es-daily-plan-september-78-2026` | combined-day title |
| `es-weekly-plan-september-7-11-2026` | must skip clean, write nothing |

Then run one without dry_run and confirm the sheet fills.

### 5. Make.com

- **Trigger:** RSS → Watch RSS feed items → `https://newsletter.smashelito.com/feed`.
  No username or password — the feed is public and those fields are for
  HTTP basic auth.
- **Action:** HTTP → **Make a request** (not "Webhook response" — that
  module replies to inbound webhooks and is the wrong direction).

```
POST https://api.github.com/repos/<you>/smash-levels/dispatches
Headers:
  Authorization: Bearer <fine-grained PAT>
  Accept: application/vnd.github+json
Body (raw, application/json):
  {"event_type":"smash-post","client_payload":{"url":"{{link}}","title":"{{title}}"}}
```

PAT: fine-grained, this repo only, **Contents: read and write**. That
permission is what `repository_dispatch` requires. Nothing else.

GitHub returns **204 No Content** on success — Make may flag an empty
body as odd. It isn't.

---

## Operating notes

**Failures email you.** Every guard exits non-zero, which fails the run,
which GitHub emails. The `heartbeat` workflow covers the case Make can't:
if the scenario silently stops firing, nothing fails because nothing ran.
Heartbeat fails if no levels landed in 26 hours.

**Nothing partial ever gets written.** Validation runs before the POST,
so a bad extraction leaves the previous day's levels in place. They're
labelled with their date (`SMASH 9/10`), so stale levels are visible on
the chart rather than silently wrong. If you see yesterday's date at the
open, paste manually and check the Actions log.

**When something fails:** the run's artifact holds the raw `levels.json`,
kept 90 days. It's usually obvious from that whether the model misread
the post or the post itself was unusual.

**Tuning:** all thresholds are constants at the top of
`validate_and_post.py` — the ±10% band, max zone width, colours, line
types. Format rules live in `.claude/skills/extract-levels/SKILL.md`; edit
that when his wording shifts.

---

## Not built yet

- **Weekly plans.** Skipped by the title filter. They need a second sheet
  and study instance, 5 levels per side, `*`-marked weekly extremes, and
  subset-not-equality cross-checking. Reserve line type 4 for them so
  they're distinguishable from daily levels on the same chart.
- **VIX levels.** Extracted and logged, not written — they can't plot on
  an ES chart.
- **Image-only posts.** Every level so far appears in text. If that
  changes, the skill flags low confidence rather than guessing.
