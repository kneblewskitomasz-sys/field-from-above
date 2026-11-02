# Third-party notices

The code written for this project is licensed under **MIT** (see `LICENSE`).
The models, data and libraries below keep their own terms. Nothing here grants
rights to the model weights: **no model weights are included in this
repository**.

## Data

| source | used for | terms | attribution required in public copies |
|---|---|---|---|
| **Copernicus Sentinel-2 L2A** (ESA / Copernicus, accessed through Earth Search STAC) | NDVI, NDRE, cloud mask (SCL) | Copernicus Sentinel Data Licence: free, full and open; reproduction, distribution, adaptation and commercial use allowed. Source: <https://cds.climate.copernicus.eu/licences/ec-sentinel>, read 2026-08-17 (project legal note). | `Contains modified Copernicus Sentinel data 2026` |
| **ULDK / GUGiK** (Polish national cadastre service) | parcel boundaries | Geoportal terms: publication of material from the service is allowed provided the source is stated; no specific formula and no ban on commercial use. Source: <https://www.geoportal.gov.pl/pl/regulamin/>, read 2026-08-17. | `Boundaries: ULDK/GUGiK, read 2026-11-01` |
| **Orthophoto, GUGiK WMS 1.1.1** | context layer in the demo maps | Same Geoportal terms as above. Image date 2025-03-28, sheet `M-34-15-A-a-4-1`. | `Orthophoto: GUGiK WMS 1.1.1, image 2025-03-28` |
| **Terrain model, GUGiK NMT GetHByXY** | terrain range and profile | Same Geoportal terms as above. Read 2026-11-01. | `Terrain: GUGiK NMT GetHByXY, read 2026-11-01` |

The rendered PNG maps in `demo/img/` are **derived works** of these data: the
index maps contain modified Copernicus Sentinel data, and the orthophoto panels
contain GUGiK orthophoto. The attribution above must travel with them. The demo
page repeats the attribution in its footer.

## Models

| model | version / checkpoint | licence | what is used here | weights included? |
|---|---|---|---|---|
| **SAM 3.1** (Meta) | `sam3.1_multiplex.pt` (~3.5 GB, 848 M parameters) | **SAM License**, “Last Updated: November 19, 2025”. Not Apache-2.0. Royalty-free, non-exclusive, worldwide, non-transferable, limited licence to use, reproduce, distribute and modify the SAM Materials. Distribution only under the same terms and with a copy of the agreement. Prohibits use in violation of ITAR, military, weapons, nuclear and espionage contexts. Publication of results requires acknowledging the use of SAM. Commercial use is not prohibited. | orthophoto segmentation masks (field, crop, grass, bare soil, building, road); run 2026-10-28 | **no** — gated checkpoint at <https://huggingface.co/facebook/sam3.1>, not redistributed |
| **Muse Glimmer 30B** (Meta) | `muse-glimmer:30b`, 18 GB Ollama build; 29,776,626,688 parameters in BF16 | **Apache 2.0** | local field descriptions (3 of 5 parcels passed fact validation) | **no** |
| **Muse Spark 1.3** (Meta) | `muse-spark-1.3` through the Meta Model API | Meta Model API terms; proprietary service, no open weights found for this version | API field descriptions (5 of 5 parcels); stored in `dane/opisy_meta.json` | **no** |
| **Supertonic 3** | local TTS, voice F1 | **OpenRAIL-M** (per project research note, 2026-10-21) | narration of the demo video only — the video is **not** in this repository | **no** |

### Note on Meta API output text

`dane/opisy_meta.json` and the `opisy.meta` blocks in `demo/index.html` contain
the five descriptions generated through the Meta Model API. The Meta Model API
terms were **not re-read line by line for this publication**; the project read
the pricing page on 2026-11-01. The descriptions are short factual texts
generated from the owner's own measurements, not third-party content. **If the
owner wants zero legal doubt before publishing**, remove `dane/opisy_meta.json`
and the `opisy.meta` blocks from `demo/index.html`; the page then falls back to
the local descriptions for 3 of 5 parcels, and the API comparison table becomes
empty. This is a decision for the owner, recorded in the report.

## Software libraries

The chain stub (`lancuch.py`) uses only the Python standard library (PSF
licence). The real-data modules use these packages; the versions are those
tested on 2026-11-02:

| package | version tested | licence (from installed metadata) |
|---|---|---|
| **NumPy** | 2.5.1 | BSD-3-Clause (bundle also lists 0BSD, MIT, Zlib, CC0-1.0) |
| **rasterio** | 1.5.0 | BSD-3-Clause |
| **Shapely** | 2.1.2 | BSD-3-Clause |
| **pyproj** | 3.7.2 | MIT |
| **Matplotlib** | 3.11.1 | Matplotlib licence (PSF-based, BSD-compatible) |
| **Pillow** | 12.3.0 | MIT-CMU |
| **GDAL** (rasterio dependency) | as bundled with rasterio | MIT/X11 |

The licence column comes from `importlib.metadata` on the machine where the
repository was prepared (2026-11-02). Before redistributing a bundled wheel,
check that wheel's own `LICENSE` file.

## Fonts and assets

The demo page uses system fonts only and bundles no font files. The 16 PNG maps
were rendered with Matplotlib and Pillow; no stock images, icons or clip art are
included. The only photographs are the GUGiK orthophoto crops described above.

## Required attribution block

If you republish the demo page or the maps, keep this block (or an equivalent
one) together with them:

> Contains modified Copernicus Sentinel data 2026.
> Boundaries, orthophoto and terrain: GUGiK (ULDK, WMS 1.1.1, NMT GetHByXY),
> read 2026-11-01.
> Segmentation masks produced with SAM 3.1 (Meta), SAM License, run 2026-10-28.
> Description text: Muse Glimmer 30B (Apache 2.0) and Muse Spark 1.3
> (Meta Model API).
