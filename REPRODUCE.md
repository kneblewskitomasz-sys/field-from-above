# Reproduce Field from Above

This file lists what runs from a clean copy without an account, a GPU or a
network, and what is deliberately absent. The demo and test commands below were
run on 3 November 2026 against commit `21a4d80` in a clean copy with an empty
working tree (`git status --short` printed nothing).

Environment used: Python 3.12.10, NumPy 2.5.1, rasterio 1.5.0, Shapely 2.1.2,
pyproj 3.7.2.

## 1. Instant demo (no installation)

Open `demo/index.html` in a modern browser — a double-click is enough. It is one
static file with local images; `demo/index.html` contains zero `http://` or
`https://` URLs, zero protocol-relative `src`/`href` references, zero `@import`,
zero `fetch()` calls and zero `XMLHttpRequest`; all 26 explicit image paths used by
the page and `demo/dane/s155a.js` exist among the 32 PNG files in `demo/img/`. No
key, server or network is needed.

To confirm the offline mode from a terminal:

```bash
python demo/uruchom_demo.py
```

Result in the clean copy: exit code 0 and

```text
Field from Above — demo
Mode: offline (no network, no API key)
Page: .../demo/index.html
META_API_KEY is not set — the offline demo still works. Only the live Meta API call is unavailable.
```

## 2. Offline tests

From the repository root:

```bash
# standard library only
python lancuch.py --atrapa ok
python lancuch.py --atrapa chmury
python lancuch.py --atrapa awaria-opisu
python lancuch.py --atrapa pusty
python test_lancuch.py

# real-data modules: NumPy, rasterio, Shapely, pyproj
python test_sentinel.py
python test_historia.py
python test_teren_punkty.py
```

What the four `lancuch.py` calls show (the nonzero exits are the failure paths,
not test failures):

| command | status in the output | exit code |
|---|---|---:|
| `--atrapa ok` | `OK` | 0 |
| `--atrapa chmury` | `CHMURY` (no number, no description) | 1 |
| `--atrapa awaria-opisu` | `BEZ_OPISU` (the measurement stays, the sentence does not) | 1 |
| `--atrapa pusty` | `PUSTY_OBSZAR` | 2 |

The exit codes come from `lancuch.py`: `return 2` for `PustyObszar` and
`return 0 if wynik.status == STATUS_OK else 1` at the end of the demo function.

Test results in the same clean copy:

| command | result | exit code |
|---|---|---:|
| `python test_lancuch.py` | `4/4 przypadków zielonych (18 sprawdzeń, 0 przypadków czerwonych)` | 0 |
| `python test_sentinel.py` | `22/22 OK, 0 czerwonych` | 0 |
| `python test_historia.py` | `Ran 19 tests ... OK` | 0 |
| `python test_teren_punkty.py` | `Ran 7 tests ... OK` | 0 |

The three `test_*.py` files above import NumPy, rasterio, Shapely and pyproj;
`requirements.txt` lists them. The page and the four `lancuch.py` cases need none
of them.

### Clean-copy check

The clean copy was created at commit `21a4d80` from a local `git bundle` of this
repository, because `git clone` of a local path needs the MSYS shell on the
verification machine and that shell was not available. `git rev-parse HEAD` in
that copy printed `21a4d802e85b2360f6c2eba6039ee91c9d346494`, and
`git status --short` printed nothing both before and after the run. On a normal
machine the equivalent is:

```bash
git clone https://github.com/kneblewskitomasz-sys/field-from-above.git pole-z-gory
cd pole-z-gory
```

## 3. What is not in this repository, and why

- **The private raster and mask cache.** `uruchom_na_dzialkach.py` expects
  `indeksy26.npz`, `maski.npz`, `scl28.npy`, `sceny.json` and `indeksy_26.json`
  from the owner's working project. They contain the owner's five parcels and are
  not published; without them the script stops with a clear `FileNotFoundError`
  (for example on `indeksy_26.json`) by design. This is why the real-parcel run is
  not reproduced here.
- **Model weights.** SAM 3.1 is a gated checkpoint, Muse Glimmer 30B runs from a
  local server, and Muse Spark 1.3 is an API model; no weights are redistributed
  (see "Meta models" and `THIRD-PARTY.md`). The demo and all tests above run
  without them.
- **The full application and its API client.** The code that calls the Meta Model
  API is private; this repository stores the outputs in `dane/opisy_meta.json`.
  There is no API-call section here because there is no API-call script in this
  repository.
- **The demo video and its audio.** They are a separate deliverable; the
  repository does not ship `demo/film/` (see `BUILT-DURING-HACKATHON.md`). The
  video link is at the top of the README.

The static page, the 32 PNG maps and the measurement JSON files are included. The
large items are the private cache and the model weights, not missing code.
