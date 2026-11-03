# What was built during the hackathon

Event window: **27 October 2026 – 4 November 2026**. Submission deadline:
4 November 2026, 21:00 ET (5 November 2026, 03:00 Polish time).

Dates below come from the main project's git history:

```bash
git log --date=iso --stat -- hackathon/pole-z-gory
```

The first commit touching this code is `edbdbcd3`, **2026-10-27 09:04 +0100**.
Nothing in this repository is older than that commit, with one explicitly named
exception (the NDVI pattern, see below).

## Timeline

| date (commit) | what appeared | evidence |
|---|---|---|
| **2026-10-27 09:04** (`edbdbcd3`) | Chain skeleton: `lancuch.py` (four steps, four stubs, `PustyObszar`, `CHMURY`, `BEZ_OPISU`), `test_lancuch.py` (4 cases), first README. | commit `edbdbcd3` |
| **2026-11-01 22:35** (`4444e5df`) | Real-data path: `sentinel.py` (STAC search, B04/B05/B08/SCL, NDVI/NDRE, cloud mask), `adapter.py` (cached rasters, ULDK masks, stored descriptions), `uruchom_na_dzialkach.py` (five real parcels + cloud failure test), `mapy.py` / `orto.py` / `teren.py`, `test_sentinel.py`; the first demo page and 16 rendered PNG maps (`demo/img/`); the report `raport_lancuch.json` and its log. | commit `4444e5df` |
| **2026-11-02** (working tree, not committed in the main project) | Demo descriptions updated to the **3/5** local result (92/10 passed; 92/6 and 92/11 rejected), `demo/index.html` data block updated. | `git status`, 2026-11-02 |
| **2026-11-02** (this publication copy) | English `README.md`, `BUILT-DURING-HACKATHON.md`, `LICENSE`, `THIRD-PARTY.md`, the offline launcher `demo/uruchom_demo.py`, and the bilingual EN/PL page (default English). | this directory |
| **2026-11-02** (main project, published 2026-11-03) | Season and terrain: `historia.py` (2026 season, scenes with ≥80% clear pixels, weak-spot verdict with a 10% threshold fixed before the measurement), terrain map from the national model, Season and Terrain tabs, `test_historia.py` (19) and `test_teren_punkty.py` (7), 16 new PNG maps. | commit `0bd4bd2` |
| **2026-11-03** | English verdict label in the Season tab; repository and GitHub Pages published; demo video finished (boundary slide, repository link and date on the end card). | commit `4f89a15` and this commit |

## What predates 26 October 2026 — named explicitly

- **An earlier NDVI script** of mine (the NDVI implementation with the SCL cloud mask,
  coverage and resolution matching) was written **before** the hackathon. It is
  **not copied** into this repository. `sentinel.py` follows its *pattern* and
  adds NDRE (B05, red edge 1 at 705 nm), which that older code does not read.
- The **data sources** (Sentinel-2, ULDK/GUGiK, orthophoto, terrain model) are
  public services that exist independently of the event. The measurement dates
  are 2026-10-23, 2026-10-26, 2026-10-28 and 2026-11-01 — all inside the event
  window.
- **Muse Glimmer 30B**, **Muse Spark 1.3** and **SAM 3.1** are third-party models
  that existed before the event. The event work is the chain that uses them, not
  the models themselves. Their licences are in `THIRD-PARTY.md`.

## What was *not* carried into the public repository

These files exist in the main project but are excluded here on purpose:

- `ZGLOSZENIE.md` — the submission draft (contains the owner's submission text,
  not code);
- `_tmp_*.py` — scratch scripts used to build the page data;
- `demo/scenariusz.md` and `demo/film/` — the demo video script, audio and video
  (the video is a separate deliverable, not code);
- `raport_lancuch.log` — a run log with local paths;
- `__pycache__/` — Python bytecode.

The demo page, the PNG maps and the four chain modules are the same files as
in the main project, except for the English/Polish translation layer in
`demo/index.html` and a portability fix in the two test files (stdout is forced
to UTF-8 so the tests run on a Windows console that is not UTF-8).
