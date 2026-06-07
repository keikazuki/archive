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
5. Skips known generic/low-information media, then hashes images and video frames with `DifferenceHash`.
6. Inserts rows into `media` and `submissions` in one transaction via `addSubmissionAndMedia`.

`archive.py` is intentionally similar to `archivelimit.py`. If media extraction, hashing, database writes, Redgifs handling, supported domains, logging, or duplicate detection changes here, inspect and usually update `archivelimit` too.

## Current Production Subreddits

This repo processes the current rows of `indexsubreddits`. Production had 242 rows on 2026-06-06:

```text
﻿2Booty
2busty2hide
3DHentai
AhegaoGirls
AiSayama
anime
anime_irl
Anime_Porn
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
Arknights
Artistic_Hentai
AsianCuties
AsianHalves
AsianHotties
AsianHottiesNSFW
attackontitan
AyumiShinoda
babesdirectory
BigAnimeTiddies
Bleach
BlenderNSFW
BlueArchive
BlueArchiveHentai
BlueArchiveNSFW
BocchiTheRock
BokuNoHeroAcademia
CamGirl
Cartoon_Porn
CartoonPorn
Cawwsplay
celebnsfw
ChainsawMan
ChainsawManHentai
cosplay
cosplaybabes
cosplaybutts
cosplaygirls
CosplayGirlsNSFW
CosplayLewd
CosplayNation
CosplayNSFW_
CumHentai
Cyberbooty
DDLC
DemonSlayerAnime
derpixon
DigitalArt
DispatchR34
doujinshi
DragonMaid
ecchi
Eimi_Fukada
EliteFemale
Evangelion
FateHentai
fatestaynight
FetishJAV
FFXIV
FFXIVNSFW
FinalFantasy
FinalFantasyNSFW
findthatpornstar
FireEmblem
FireEmblemHeroes
FortniteNSFW
FunnyJAV
FunPiece
Futanari
GalJAV
GeekyBikini
GeekyChan
Genshin_Impact
GenshinImpactHentai
GenshinImpactNSFW
GirlsFrontline
goodanimemes
GravureGirls
hentai
Hentai_AnimeNSFW
Hentai_Gif
hentai_irl
HentaiGifs
hentaimemes
HentaiSchoolGirls
HentaiSource
HentaiVTuberGirls
HighSchoolDxD
HistoryAnimemes
Hitomi_Tanaka
Hololewd
hololive
HonkaiStarRail
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
Jujutsufolk
JujutsuKaisen
JuliaJAV
KaguyaHentai
KahoShibuya
KillLaKill
KillLaKillHentai
KimetsuNoYaiba
Komi_san
Konosuba
KonosubaNSFW
kpopfap
KpopHotties
KurwaSuka
LeagueOfLegendsNSFW
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
MasturbationHentai
MayFucks
MenintroubleJAV
Metroid
Metroid34
Models
Moescape
MonsterGirl
MyHeroAcadamia
Nagatoro
NagatoroHentai
nameherplease
Naruto
Naruto_Hentai
nhentai
NikkeNSFW
noveltranslations
NSFW_China
NSFW_Japan
nsfwcosplay
NSFWgaming
NTR
NudeGravureGirls
OnePiece
OnePieceHentai
OnePunchMan
OtomeIsekai
Overwatch_Porn
Persona34
Persona5
PetiteJAV
PixelArtNSFW
Pixiv
PokemonNSFW
PokePorn
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
PunishingGrayRaven
ReZeroHentai
rule34
rule34gay
Rule34LoL
Rule_34
RWBY
SailorMoon
SakuraMatou
sex_comics
SFMCompileClub
ShingekiNoKyojin
ShinjukuIdols
ShionUtsunomiya
Slutoon
SonoBisqueDoll
sources4porn
SpaghettiHentai
SpreadingHentai
SpyxFamily
SpyxFamilyHentai
StardustCrusaders
ThaiBeauties
TheHentaiZone
thick_hentai
thighdeology
TimeStopJAV
tipofmypenis
touhou
Touhou_NSFW
vtubers
Waifus34
webtoons
whatanime
WhatAWeeb
wholesomeanimemes
wholesomehentai
wholesomeyuri
WutheringWaves
WutheringWavesHentai
yaoi
YorForger
yuri
YuShinoda
Zelda
ZeldaIsCute
ZenlessZoneNSFW
ZenlessZoneZero
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

Ignored media behavior:

| Item | Value |
| --- | --- |
| Imgur deleted placeholder hash | `9925021303884596990` |
| Uniform black/white/fade-frame hash | `18446744073709551615` |
| Low-information sample | 16x16 grayscale image |
| Low-information thresholds | pixel range `<= 4` or standard deviation `<= 2.0` |

`archive.py` drops low-information images before DB insert. This prevents whole-black, whole-white, and near-uniform transition frames from polluting repost matching. `databasehandler.getAllMedia` also excludes both ignored hashes for compatibility with older code paths.

Do not change table columns, hash types, primary keys, ignored hashes, or low-information thresholds without updating all shared repos and the production recovery documentation. If a future AI sees live production schema drift, it should update this README and the setup note after confirming the real schema.

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
