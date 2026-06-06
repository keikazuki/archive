# archive

`archive` is the long-running media indexer for the shared `SauceMaster` PostgreSQL database. It watches the subreddits stored in `indexsubreddits`, downloads supported image/gif/video media from new Reddit submissions, computes 64-bit perceptual difference hashes, and writes both the submission metadata and media hashes into the shared database. It does not comment on Reddit posts.

Production was inspected on 2026-06-06.

## Production

| Item | Value |
| --- | --- |
| Host | `ubuntu@100.71.13.89` |
| Production path | `/home/ubuntu/Desktop/archive` |
| Service | `archive.service` |
| Service state | enabled, active/running |
| Entrypoint | `archive.py` |
| Virtualenv | `/home/ubuntu/Desktop/archive/archive` |
| Log file | `/home/ubuntu/Desktop/archive/archive.log` |
| Reddit account | `PERVTAKUS` from `config.py` |
| Database | `SauceMaster` on PostgreSQL |

Useful commands:

```bash
sudo systemctl status archive.service
sudo systemctl restart archive.service
tail -f /home/ubuntu/Desktop/archive/archive.log
```

## What The Bot Does

1. Imports `databasehandler` and loads `SUBREDDITLIST` from `SELECT subreddit FROM indexsubreddits`.
2. Opens a PRAW stream with `reddit.subreddit(SUBREDDITLIST).stream.submissions(pause_after=0)`.
3. Skips a submission when `submissions.id` already exists.
4. Resolves media from direct image links, Reddit galleries/previews/videos, Imgur albums, Redgifs, Gfycat, gifs/gifv, crossposts, and self-post URLs.
5. Hashes images and video frames with `DifferenceHash`.
6. Inserts rows into `media` and `submissions` in one transaction via `addSubmissionAndMedia`.

`archive.py` is intentionally similar to `archivelimit.py`. If media extraction, hashing, database writes, Redgifs handling, supported domains, logging, or duplicate detection changes here, inspect and usually update `archivelimit` too.

## Current Production Subreddits

This repo processes the current rows of `indexsubreddits`. Production had 145 rows on 2026-06-06:

```text
﻿2busty2hide
AhegaoGirls
AiSayama
anime_irl
AnimeART
AnimeFigures
AnimeH34
animememes
Animemes
AnimeMILFS
animenocontext
AnimeSauce
AnimeSketch
AnimeTitties
AnimeWallpaper
AsianCuties
AsianHalves
AsianHotties
AyumiShinoda
babesdirectory
BigAnimeTiddies
CamGirl
Cawwsplay
celebnsfw
cosplay
cosplaybabes
cosplaybutts
cosplaygirls
CosplayGirlsNSFW
CosplayLewd
CosplayNation
CosplayNSFW_
CumHentai
derpixon
DigitalArt
doujinshi
Eimi_Fukada
EliteFemale
FetishJAV
findthatpornstar
FunnyJAV
Futanari
GalJAV
GeekyBikini
GeekyChan
GenshinImpactHentai
goodanimemes
GravureGirls
Hentai_Gif
hentai_irl
hentaimemes
HentaiSource
HentaiVTuberGirls
HistoryAnimemes
Hitomi_Tanaka
HonkaiStarRailHentai
HypnoHentai
idols_japan_pic
ImaginaryAnime
ImaginaryCharacters
JapaneseAsses
JapaneseBreastSucking
JapaneseFacials
JapaneseGokkun
JapaneseHotties
JapaneseKissing
JapanesePorn2
jav
JAVboratory
javdreams
JavFantasy
JavPaizuri
JuliaJAV
KahoShibuya
kpopfap
KpopHotties
lewdgames
LightNovels
MaidHentai
manga
mangaart
mangacoloring
Manhua
Manhua_Nsfw
manhwa
ManhwaRealm
manhwarecommendations
MayFucks
MenintroubleJAV
Models
Moescape
MonsterGirl
nameherplease
nhentai
noveltranslations
NSFW_China
NSFW_Japan
nsfwcosplay
NSFWgaming
NTR
NudeGravureGirls
OtomeIsekai
PetiteJAV
PixelArtNSFW
Pixiv
PornhubAds
pornhwa__MILFS
PornhwaNormal
pornhwaRaw
pornID
PornIdBetter
porninfifteenseconds
PornoMemes
Pornwha
PremiumCheeks
PrettyWomen
Priconne
PublicHentai
ReZeroHentai
rule34
rule34gay
SFMCompileClub
ShinjukuIdols
ShionUtsunomiya
Slutoon
sources4porn
SpaghettiHentai
SpreadingHentai
ThaiBeauties
TheHentaiZone
TimeStopJAV
tipofmypenis
Waifus34
webtoons
whatanime
WhatAWeeb
wholesomeanimemes
wholesomehentai
wholesomeyuri
WutheringWavesHentai
yaoi
yuri
YuShinoda
ZenlessZoneNSFW
ZettaiRyouiki
```

If production rows differ from this list, update this README and `obsidian-vault/Setup/Ubuntu Server Set-Up.md`.

## Shared Database Contract

This repo shares the `SauceMaster` database with `archivelimit`, `repostchecker`, `repostchecker_pornhwa`, and `rule34tagbot`.

Tables touched directly:

| Table | Use |
| --- | --- |
| `indexsubreddits(subreddit, IsPornhwa)` | Source of archive/index subreddit list. |
| `submissions` | One row per indexed Reddit submission. |
| `media` | One row per image hash or unique video/gif frame hash. |

Important production keys and indexes:

| Object | Definition |
| --- | --- |
| `submissions_pkey` | Primary key on `submissions(id)`. |
| `media_pkey` | Primary key on `(submission_id, frame_number, hash)`. |
| `idx_media_sub_id_hash` | B-tree index on `(submission_id, hash)`. |
| `media_hash_chunk_0_idx` to `media_hash_chunk_4_idx` | Expression indexes used by `repostchecker` to find hash candidates quickly. |

Do not change table columns, hash types, primary keys, or the ignored hash value `9925021303884596990` without updating all shared repos and the production recovery documentation. If a future AI sees live production schema drift, it should update this README and the setup note after confirming the real schema.

## Local Development

```bash
python -m venv archive
archive\Scripts\activate
pip install -r requirements.txt
python archive.py
```

On Ubuntu production:

```bash
python -m venv archive
source archive/bin/activate
pip install -r requirements.txt
python archive.py
```

`config.py` currently contains live credentials. Treat it as sensitive. Prefer moving secrets to environment variables before publishing or sharing logs.

## AI Maintenance Rules

- Update this README in the same change when behavior, service config, dependencies, DB schema, subreddit loading, or Reddit accounts change.
- If DB schema changes are needed, tell the owner first, update code, update this README, and update `obsidian-vault/Setup/Ubuntu Server Set-Up.md`.
- If production DB rows are changed manually and later queries reveal drift, update this README so it reflects production reality.
- When changing media parsing or hashing, check `archivelimit` for the same change.
- When changing database writes or hash semantics, check `repostchecker` and `repostchecker_pornhwa` because they read the rows this bot creates.
