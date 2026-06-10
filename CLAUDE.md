# archive

Long-running media indexer for shared `SauceMaster` PostgreSQL database. Watches subreddits in `indexsubreddits`, downloads media from new submissions, computes 64-bit perceptual difference hashes, and writes submission metadata and media hashes. Does not comment on Reddit.

## Development Workflow

- **Code changes are made locally** on Windows, not directly on the Ubuntu server.
- **README.md must be kept updated** whenever behavior, service config, dependencies, DB schema, subreddit loading, or Reddit accounts change.
- **Read-only operations on Ubuntu server** (logs, status checks, database inspection) require no permission.
- **Any update, write, or modification to Ubuntu server** requires explicit user confirmation first.

## Production Deployment

| Item | Value |
| --- | --- |
| Host | `ubuntu@100.71.13.89` |
| Path | `/home/ubuntu/Desktop/archive` |
| Service | `archive.service` (enabled, active/running) |
| Entrypoint | `archive.py` |
| Log | `/home/ubuntu/Desktop/archive/archive.log` |
| Reddit Account | `PERVTAKUS` (from `config.py`) |
| Database | `SauceMaster` on PostgreSQL |

## Core Behavior

1. Loads `SUBREDDITLIST` from `indexsubreddits` table
2. Opens PRAW stream with `reddit.subreddit(SUBREDDITLIST).stream.submissions(pause_after=0)`
3. Skips submissions already in `submissions` table
4. Resolves media: direct images, Reddit galleries/previews/videos, Imgur, Redgifs, Gfycat, gifs/gifv, crossposts, self-post URLs
5. Skips low-information/generic media, hashes with 64-bit DifferenceHash
6. Inserts `media` and `submissions` rows in transaction via `addSubmissionAndMedia`

**Nearly identical to `archivelimit`:** If media extraction, hashing, DB writes, Redgifs handling, supported domains, logging, or duplicate detection changes here, inspect and usually update `archivelimit` too.

## Fail-Safe Hardening (2026-06-10)

- `ensureDatabaseConnection` reconnects with exponential backoff (12 attempts, 5s–60s, ~9 min) instead of failing immediately
- `runDatabaseOperation` wrapper reconnects and retries once on mid-query connection drop
- Startup `reddit.user.me()` now in retry loop so transient failures cannot crash service before streaming

## Subreddit Scope

Processes all 242 rows from `indexsubreddits` as of 2026-06-06 (includes `2Booty`, `anime`, `hentai`, `rule34`, etc.).

## Database Contract

Shared `SauceMaster` with `archivelimit`, `repostchecker`, `repostchecker_pornhwa`, `rule34tagbot`:

| Table | Use |
| --- | --- |
| `indexsubreddits` | Source of archive subreddit list |
| `submissions` | Indexed submission metadata (one row per submission) |
| `media` | Image/video frame hashes (one row per unique hash) |

**Production indexes:**
- `submissions_pkey` — PK on `submissions(id)`
- `media_pkey` — PK on `(submission_id, frame_number, hash)`
- `idx_media_sub_id_hash` — B-tree on `(submission_id, hash)`
- `media_hash_chunk_0_idx` to `media_hash_chunk_4_idx` — Expression indexes (used by repostchecker)

**Ignored media:**
- Imgur deleted placeholder: `9925021303884596990`
- Uniform black/white/fade-frame: `18446744073709551615`
- Low-info thresholds: pixel range ≤4 or std dev ≤2.0

**Critical:** Do not change table columns, hash types, primary keys, ignored hashes, or low-info thresholds without updating all shared repos and production recovery docs.

## Related Repos

| Repo | Note |
| --- | --- |
| `archivelimit` | One-shot catch-up version. Keep media extraction and DB shape synchronized. |
| `repostchecker` | Reads this bot's rows. Hash/DB changes affect repost results. |
| `repostchecker_pornhwa` | Legacy pornhwa bot. Check before major changes. |
| `rule34tagbot` | Shares database. |

## Local Development

```bash
python -m venv archive
archive\Scripts\activate
pip install -r requirements.txt
python archive.py
```

Ubuntu:
```bash
python -m venv archive
source archive/bin/activate
pip install -r requirements.txt
python archive.py
```

## AI Maintenance Rules

✓ Update README.md when behavior, service config, dependencies, DB schema, subreddit loading, or Reddit accounts change.

✓ If DB schema changes needed: notify user first, update code, update README, update obsidian-vault notes.

✓ If production DB rows drift: update README to reflect production reality.

✓ When changing media parsing or hashing: check `archivelimit` for same change.

✓ When changing DB writes or hash semantics: check `repostchecker` and `repostchecker_pornhwa` (they read this bot's rows).

✓ For Ubuntu server modifications: always ask user for permission before writing/updating.

✓ Read-only access to Ubuntu (logs, status, inspection) requires no permission.
