# Field from Above

**From a satellite image to the first furrow you check.**

A local-first demo that turns the boundary of a Polish parcel into a dated,
cloud-masked NDVI/NDRE map, an orthophoto with segmentation masks, and a short
note that says what was measured, how coarse it is, and where to walk first.
It does not pretend to be a soil test.

Built for the Meta Global AI Developer Hackathon (27 October - 4 November 2026),
theme **Build for Your World**.

---

## What it does

1. **Boundary from the national cadastre.** The user enters a parcel ID; the
   system asks ULDK (the Polish national cadastre service) for the boundary.
   If the parcel is not found, the tool returns a named absence and continues
   with the others - it never turns "no data" into "zero".
2. **Current satellite measurement.** It searches the Sentinel-2 L2A archive
   through STAC, masks clouds and shadow with the scene classification layer,
   and computes NDVI and NDRE inside the parcel boundary. Every number carries
   the scene date, the number of pixels, the cloud share over that parcel and a
   95% confidence interval.
3. **Context layers, each with its own date.** An orthophoto from the national
   geoportal (image date 2025-03-28, so the tool says it is archival), SAM 3.1
   segmentation masks, and terrain heights from the national terrain model.
4. **A description a person can use.** A Meta model receives the same image and
   the same measured numbers and writes two to four sentences: what is visible,
   what to check in the field, and what is uncertain. It is explicitly forbidden
   to invent numbers, recommend fertiliser, or call the result a soil test.

5. **Season and terrain.** One date can lie, so the tool reads the whole 2026
   season (Sentinel-2 scenes with at least 80% clear pixels over the parcel) and
   draws an NDVI curve per parcel. A darker spot on one date must come back on
   other dates (in at least 10% of its pixels) before the tool calls it a weak spot;
   otherwise the verdict is **does not return** and the note says not to start
   there. Terrain heights come from the national terrain model; an empty or
   zero reading is shown as "no data", never as flat ground.

The demo page puts the parcel picker, layer switcher, measurement cards, the
model text and a "what 10 metres cannot tell you" panel in one static file.
It opens from disk and makes **zero external requests**.

## For whom

- **The owner of a few small fields** who has satellite data but cannot walk
  into an image and needs to know which parcel to check first.
- **A developer or judge** who wants to see a complete, dated chain and its
  failure paths - not a mock with pretty numbers.
- **A local-first builder** looking for a pattern where the field image and the
  parcel data stay on the owner's machine.

## Quick start (from zero)

Requirements: **Python 3.12** and a modern browser. The demo page and the chain
stub need no network, no GPU and no paid API.

```bash
git clone <repository-url> pole-z-gory
cd pole-z-gory

# The static demo: open demo/index.html in a browser (double-click is enough).
# Or check the launcher and its offline status:
python demo/uruchom_demo.py

# The chain on synthetic data - four failure/success cases:
python lancuch.py --atrapa ok
python lancuch.py --atrapa chmury
python lancuch.py --atrapa awaria-opisu
python lancuch.py --atrapa pusty

# Tests:
python test_lancuch.py        # 4/4 cases, standard library only
```

Python dependencies for the **real-data modules** (not needed for the page or
the stub):

```bash
python -m pip install -r requirements.txt
python test_sentinel.py       # numbers, clouds, grid, terrain - no network
python test_historia.py       # season curve and weak-spot verdict - no network
python test_teren_punkty.py   # terrain points inside the parcel
```

`test_sentinel.py` needs NumPy, rasterio and Shapely; pyproj is used when
rendering maps. Matplotlib and Pillow are needed only to regenerate the PNGs.
`uruchom_na_dzialkach.py` needs the cached rasters and ULDK masks from the
owner's working project, which are **not part of this
repository**; without that cache it stops with a clear `FileNotFoundError`, by
design.

## What is in this repository

```text
.
|-- lancuch.py               four-step chain + stubs (no network)
|-- adapter.py               cached rasters / ULDK masks / stored descriptions
|-- sentinel.py              STAC search, COG reading, NDVI/NDRE, SCL clouds
|-- mapy.py, orto.py         map and orthophoto rendering
|-- teren.py                 terrain profile; "no data" is not "flat"
|-- historia.py              season curve, weak-spot verdict, terrain map
|-- uruchom_na_dzialkach.py  real-parcel run (needs the internal cache)
|-- test_lancuch.py          chain cases
|-- test_sentinel.py         index, cloud, grid and terrain checks
|-- test_historia.py         season, verdict and terrain cases (19, no network)
|-- test_teren_punkty.py     terrain points stay inside the drawn parcel (7)
|-- demo/dane/               season and terrain data used by the page
|-- demo/index.html          bilingual EN/PL demo page, no external resources
|-- demo/img/                rendered maps (32 PNG files)
|-- demo/uruchom_demo.py     offline launcher; explains the missing-key case
|-- demo/dane.sha256         hash of the single-date measurement data (2 Nov 2026)
|-- dane/opisy_meta.json     stored API descriptions and costs (source of numbers)
|-- BUILT-DURING-HACKATHON.md
|-- THIRD-PARTY.md
`-- LICENSE                  MIT (code written for this project)
```

## Meta models - which one, and where it runs

| model | where it runs | role in this project | shipped here? |
|---|---|---|---|
| **Muse Spark 1.3** | Meta Model API (cloud) | description for all five parcels, prose prompt; 8.4 / 9.1 / 7.5 / 9.3 / 7.1 s per parcel | no; outputs stored in `dane/opisy_meta.json` |
| **Muse Glimmer 30B** | local server, AMD GPU, 96 GiB VRAM, Apache 2.0 | local description; 3 of 5 parcels passed fact validation; 649.9 / 373.1 / 60.6 s | no weights |
| **SAM 3.1** | local, gated checkpoint | orthophoto segmentation into field, grass, bare soil, building and road masks; 99 masks in 12.83 s on 2026-10-28 | no weights |
| **Supertonic 3** | local TTS | narration of the demo video only; the video is not in this repository | no |

The **API key is read only from the `META_API_KEY` environment variable**, never
from a file, never from the page, and never printed. The static demo does not
call the API at all. Without the key, the offline demo and every test still
work; only the live API call is unavailable, and the launcher says so in one
named sentence. The full application - which performs that call - is not part of
this repository.

## Measured results

All numbers below come from two places only: the `DANE` block embedded in
`demo/index.html`, and `dane/opisy_meta.json`. Dates are the measurement dates,
not the publication date.

| parcel | area (ha) | NDVI mean | NDRE mean | pixels used | edge pixels |
|---|---:|---:|---:|---:|---:|
| 90/8 | 0.5029 | 0.791 | 0.521 | 50 | 74.0% |
| 90/12 | 0.5168 | 0.796 | 0.550 | 52 | 71.2% |
| 92/6 | 0.6792 | 0.450 | 0.289 | 67 | 43.3% |
| 92/10 | 2.8833 | 0.402 | 0.254 | 292 | 31.8% |
| 92/11 | 0.3025 | 0.431 | 0.264 | 31 | 58.1% |

- **Scene:** Sentinel-2 L2A `S2B_33UXU_20261026_1_L2A`, 2026-10-26; control
  `S2B_33UXU_20261023_0_L2A`, 2026-10-23. Cloud over all five parcels: **0.0%**.
  Cloud in the whole scene: **11.21%** (control **1.32%**).
- **Cloud failure test:** scene 2026-10-28 with **96.63%** cloud in the scene and
  **100%** over the parcels returns status `CHMURY` - a message, not an old
  number presented as current.
- **Missing parcel:** 90/1 returns `-1 no results` from ULDK. It is a named
  absence; the other five parcels are still computed.
- **Orthophoto:** GUGiK WMS 1.1.1, image 2025-03-28, sheet
  `M-34-15-A-a-4-1`, 0.25 m per pixel. It is archival and the page says so.
- **SAM 3.1:** 99 masks in **12.83 s** on 2026-10-28: 29 agricultural field,
  29 crop, 29 building, 8 grass, 2 bare soil, 2 road.
- **Local descriptions:** **3 of 5** parcels passed fact validation (90/8,
  90/12, 92/10). 92/6 and 92/11 were rejected - 92/6 added EPSG code `32628`,
  which was not in the measurement; 92/11 wrote the scene date as `26/11`
  instead of `26.10`. Those two parcels show the API description and the page
  names the reason.
- **API descriptions:** **5 of 5** parcels; **0.04957 USD** in total at the
  standard price read on 2026-11-01 (input 1.25 USD/M tokens, output
  4.25 USD/M). Per-parcel times: 8.4, 9.1, 7.5, 9.3 and 7.1 s.

## Limits - stated in the product, not hidden

- **10 m per pixel.** A 0.30-hectare parcel is 31 pixels; **58.1%** of them touch
  a boundary. The mean is honest, but the map cannot resolve within-field
  patterns finer than about 20-30 m.
- **NDRE uses B05 at 20 m**, so it is coarser than NDVI (real resolution 20 m).
- **The orthophoto is from 2025-03-28** and is archival. The tool never presents
  it as current.
- **The system does not identify the crop**, does not diagnose disease or
  nutrient deficiency, and does not measure soil. It is not a fertiliser or
  plant-protection recommendation.
- **The cloud mask (SCL) does not catch thin haze.** "0% cloud" is the mask's
  result, not a guarantee of a perfect atmosphere.
- **One parcel (90/1) is unresolved in ULDK**; it needs confirmation in EGiB.
- **Local descriptions exist for three of five parcels.** For 92/6, 92/10 and
  92/11 the local prompt differs in layout from the prompt sent to Spark, so the
  local-versus-API comparison there is **not** a same-prompt comparison. The
  demo states this per parcel.

## Data sources and licences

Full third-party notices, including model licences and attribution lines, are in
[`THIRD-PARTY.md`](THIRD-PARTY.md). In short:

- **Sentinel-2 L2A** - Copernicus Sentinel data, free and open; modified data
  must carry *"Contains modified Copernicus Sentinel data 2026"*.
- **ULDK / GUGiK**, **orthophoto GUGiK WMS 1.1.1**, **NMT GUGiK GetHByXY** -
  public geoportal data; publication requires information about the source.
  Read dates: 2026-11-01 (boundaries, orthophoto, terrain), 2026-10-28 (SAM run).
- **SAM 3.1** - SAM License (not Apache-2.0), gated; no weights are
  redistributed. Publication of results requires acknowledging the use of SAM.
- **Muse Glimmer 30B** - Apache 2.0; no weights are redistributed.
- **Muse Spark 1.3** - Meta Model API; no weights are redistributed.
- **Supertonic 3** - OpenRAIL-M; used only for the demo video, which is not in
  this repository.

## Privacy

Only the owner's five parcels and public data are used. No client data, no
farmer data, no family data and no repository code is sent to the Meta API. The
demo runs locally. The parcel identifiers and the location (Mąkownica) are part
of the demo by design; they are the owner's own fields.

## Licence

The code written for this project is released under the **MIT Licence** - see
[`LICENSE`](LICENSE). Third-party models and data keep their own terms; see
[`THIRD-PARTY.md`](THIRD-PARTY.md).

## What this is not

It is not a soil test, not a fertiliser or plant-protection recommendation, not
a yield forecast, and not an agronomic advisor. It is a dated satellite
measurement with its uncertainty shown next to it, and a short text that tells a
person where to walk first.
