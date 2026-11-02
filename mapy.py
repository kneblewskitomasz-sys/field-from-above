"""Mapy do demo „Pole z góry": ortofoto + ULDK + SAM, NDVI, NDRE.

Jedna zasada: mapa pokazuje **zmierzony raster**, nie wygładzoną ilustrację.
Dlatego NDVI/NDRE rysujemy w rozdzielczości 10 m (nearest), z podziałką i liczbą
pikseli; ortofoto jest tłem kontekstowym z własną datą. Granica ULDK i maski SAM
są osobnymi warstwami, każda z datą w podpisie.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from PIL import Image  # noqa: E402

# Klasy SAM: kolor konturu i wypełnienia (spójne z S147o, żeby dało się porównać)
SAM_KOLORY = {
    "agricultural_field": ("#00ff66", 0.0),
    "crop_field": ("#00b7ff", 0.0),
    "grass": ("#a6ff00", 0.22),
    "bare_soil": ("#ffa500", 0.28),
    "building": ("#ff00ff", 0.45),
    "road": ("#ffee00", 0.0),
}
SAM_NAZWY = {
    "agricultural_field": "agricultural field",
    "crop_field": "crop field",
    "grass": "grass",
    "bare_soil": "bare soil",
    "building": "building",
    "road": "road",
}

# Na mapie rysujemy tylko klasy, które coś lokalizują. „pole uprawne" i „uprawa"
# pokrywają większość kadru i nachodzą na siebie — ich kontury zamalowałyby zdjęcie,
# więc są w liczbach (panel SAM), ale nie w rysunku.
SAM_RYSUJ = ("grass", "bare_soil", "building", "road")


def wczytaj_maski_sam(katalog: str | Path) -> dict[str, np.ndarray]:
    katalog = Path(katalog)
    out = {}
    for plik in sorted(katalog.glob("maski-*.npz")):
        nazwa = plik.stem.replace("maski-", "")
        z = np.load(plik)
        out[nazwa] = z["masks"].any(axis=0)
    if not out:
        raise FileNotFoundError(f"brak masek SAM w {katalog}")
    return out


def _przezroczysty(hex_kolor: str, alpha: float) -> tuple[float, float, float, float]:
    h = hex_kolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b, alpha)


def _kadr_orto(bbox2180, bbox_orto, szer_orto: int, wys_orto: int, margines_m: float):
    x0, y0, x1, y1 = bbox2180
    x0 -= margines_m
    y0 -= margines_m
    x1 += margines_m
    y1 += margines_m
    ox0, oy0, ox1, oy1 = bbox_orto
    kol0 = int(max(0, (x0 - ox0) / (ox1 - ox0) * szer_orto))
    kol1 = int(min(szer_orto, (x1 - ox0) / (ox1 - ox0) * szer_orto))
    wier0 = int(max(0, (oy1 - y1) / (oy1 - oy0) * wys_orto))
    wier1 = int(min(wys_orto, (oy1 - y0) / (oy1 - oy0) * wys_orto))
    if kol1 <= kol0 or wier1 <= wier0:
        raise ValueError("kadr ortofoto wyszedł pusty")
    return slice(wier0, wier1), slice(kol0, kol1)


def _kadr_siatki(bbox32633, siatka, margines_m: float):
    x0, y0, x1, y1 = bbox32633
    x0 -= margines_m
    y0 -= margines_m
    x1 += margines_m
    y1 += margines_m
    # zapis w JSON to lista Affine (a, b, c, d, e, f), nie kolejność GDAL
    a, _b, c, _d, e, f = siatka["transform"][:6]
    kol0 = int(max(0, np.floor((x0 - c) / a)))
    kol1 = int(min(siatka["szer"], np.ceil((x1 - c) / a)))
    wier0 = int(max(0, np.floor((f - y1) / -e)))
    wier1 = int(min(siatka["wys"], np.ceil((f - y0) / -e)))
    return slice(wier0, wier1), slice(kol0, kol1), (c, a, f, e)


def _granica(ax, geom, crs_docelowy, kolor="#ffe100", grubosc=2.2, opis=None,
             odsuniecie=(0, 0), strzalka=False):
    from shapely.ops import transform as sh_transform
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", crs_docelowy, always_xy=True)
    g = sh_transform(tr.transform, geom)
    x, y = g.exterior.xy
    ax.plot(x, y, color="black", lw=grubosc + 1.8, alpha=0.45, zorder=5)
    ax.plot(x, y, color=kolor, lw=grubosc, zorder=6)
    if opis:
        p = g.representative_point()
        ax.annotate(opis, (p.x, p.y), xytext=odsuniecie, textcoords="offset points",
                    fontsize=9.5, fontweight="bold", color="white", zorder=8,
                    ha="center", va="center",
                    arrowprops=({"arrowstyle": "-", "color": "white", "lw": 1.0,
                                 "shrinkA": 0, "shrinkB": 0} if strzalka else None),
                    path_effects=[patheffects.withStroke(linewidth=3, foreground="black")])


def rysuj_orto(sciezka_png, orto_png, bbox_orto, bbox2180, geom4326, maski_sam,
               tytul: str, podtytul: str, margines_m: float = 45.0, opis_pola: str = ""):
    im = Image.open(io.BytesIO(orto_png)).convert("RGB")
    arr = np.asarray(im)
    wier, kol = _kadr_orto(bbox2180, bbox_orto, im.width, im.height, margines_m)
    crop = arr[wier, kol]
    ox0, oy0, ox1, oy1 = bbox_orto
    x0 = ox0 + kol.start / im.width * (ox1 - ox0)
    x1 = ox0 + kol.stop / im.width * (ox1 - ox0)
    y1 = oy1 - wier.start / im.height * (oy1 - oy0)
    y0 = oy1 - wier.stop / im.height * (oy1 - oy0)
    proporcja = max(0.5, (x1 - x0) / (y1 - y0))
    fig, ax = plt.subplots(figsize=(7.4, max(3.6, min(6.4, 7.4 / proporcja + 1.9))), dpi=140)
    ax.imshow(crop, extent=(x0, x1, y0, y1), origin="upper")
    for nazwa in SAM_RYSUJ:
        maska = maski_sam.get(nazwa)
        if maska is None:
            continue
        m = maska[wier, kol]
        if not m.any():
            continue
        kolor, alpha = SAM_KOLORY[nazwa]
        if alpha > 0:
            rgba = np.zeros((*m.shape, 4), dtype=np.float32)
            rgba[m] = _przezroczysty(kolor, alpha)
            ax.imshow(rgba, extent=(x0, x1, y0, y1), origin="upper")
        if nazwa == "road":
            ax.contour(np.linspace(x0, x1, m.shape[1]), np.linspace(y1, y0, m.shape[0]),
                       m.astype(float), levels=[0.5], colors=[kolor], linewidths=1.0, alpha=0.9)
    _granica(ax, geom4326, "EPSG:2180", opis=opis_pola)
    ax.set_title(tytul, fontsize=12.5, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("EPSG:2180 [m]")
    ax.set_ylabel("EPSG:2180 [m]")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7.5)
    legenda = [Line2D([0], [0], color="#ffe100", lw=2.2, label="ULDK boundary")]
    legenda += [Patch(facecolor=SAM_KOLORY[n][0], alpha=max(SAM_KOLORY[n][1], 0.4),
                      edgecolor=SAM_KOLORY[n][0], label=SAM_NAZWY[n])
                for n in SAM_RYSUJ if maski_sam.get(n) is not None and maski_sam[n].any()]
    ax.legend(handles=legenda, loc="lower right", fontsize=6.8, framealpha=0.85)
    ax.set_aspect("equal")
    fig.text(0.01, 0.005, podtytul, fontsize=7.4, color="#333", va="bottom")
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    fig.savefig(sciezka_png, bbox_inches="tight")
    plt.close(fig)


def rysuj_indeks(sciezka_png, arr, siatka, bbox32633, geom4326, tytul, podtytul,
                 cmap="RdYlGn", vmin=-0.1, vmax=0.9, etykieta="NDVI", margines_m=45.0,
                 opis_pola="", scl=None):
    wier, kol, (c, a, f, e) = _kadr_siatki(bbox32633, siatka, margines_m)
    arr = arr[wier, kol].astype(float)
    if scl is not None:
        scl = scl[wier, kol].astype(float)
        arr = np.where(np.isin(scl, [4, 5, 6, 7]), arr, np.nan)
    x0, x1 = c + kol.start * a, c + kol.stop * a
    y1, y0 = f + wier.start * e, f + wier.stop * e
    proporcja = max(0.5, (x1 - x0) / (y1 - y0))
    fig, ax = plt.subplots(figsize=(7.4, max(3.6, min(6.4, 7.4 / proporcja + 1.9))), dpi=140)
    im = ax.imshow(arr, extent=(x0, x1, y0, y1), origin="upper", cmap=cmap,
                   vmin=vmin, vmax=vmax, interpolation="nearest")
    _granica(ax, geom4326, "EPSG:32633", opis=opis_pola)
    ax.set_title(tytul, fontsize=12.5, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("EPSG:32633 [m]   — 1 pixel = 10 m")
    ax.set_ylabel("EPSG:32633 [m]")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7.5)
    ax.set_aspect("equal")
    cb = fig.colorbar(im, ax=ax, fraction=0.036, pad=0.02)
    cb.set_label(etykieta, fontsize=9)
    cb.ax.tick_params(labelsize=7.5)
    fig.text(0.01, 0.005, podtytul, fontsize=7.4, color="#333", va="bottom")
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    fig.savefig(sciezka_png, bbox_inches="tight")
    plt.close(fig)


ODSUNIECIA = {
    "90/8": (0, 14), "90/12": (0, 14), "92/6": (-46, 6), "92/10": (0, 20), "92/11": (0, -15),
}


def rysuj_przeglad(sciezka_png, orto_png, bbox_orto, geometrie4326, maski_sam,
                   arr_ndvi, arr_ndre, scl, siatka, statystyki, tytul="Field from Above — Mąkownica"):
    """Trzy panele: ortofoto+SAM, NDVI, NDRE — wspólny kadr wszystkich działek."""
    im = Image.open(io.BytesIO(orto_png)).convert("RGB")
    arr = np.asarray(im)
    fig, osie = plt.subplots(1, 3, figsize=(15.8, 3.4), dpi=150)
    ox0, oy0, ox1, oy1 = bbox_orto
    ax = osie[0]
    ax.imshow(arr, extent=(ox0, ox1, oy0, oy1), origin="upper")
    for nazwa in SAM_RYSUJ:
        maska = maski_sam.get(nazwa)
        if maska is None:
            continue
        kolor, alpha = SAM_KOLORY[nazwa]
        if alpha > 0:
            rgba = np.zeros((*maska.shape, 4), dtype=np.float32)
            rgba[maska] = _przezroczysty(kolor, alpha)
            ax.imshow(rgba, extent=(ox0, ox1, oy0, oy1), origin="upper")
        if nazwa == "road":
            ax.contour(np.linspace(ox0, ox1, maska.shape[1]), np.linspace(oy1, oy0, maska.shape[0]),
                       maska.astype(float), levels=[0.5], colors=[kolor], linewidths=0.7, alpha=0.9)
    for ident, g in geometrie4326.items():
        krotki = ident.split(".")[-1]
        ods = ODSUNIECIA.get(krotki, (0, 12))
        _granica(ax, g, "EPSG:2180", grubosc=1.5, opis=krotki, odsuniecie=ods,
                 strzalka=max(abs(ods[0]), abs(ods[1])) >= 18)
    ax.set_title("Orthophoto 2025-03-28 + ULDK + SAM 3.1 masks (2026-10-28)",
                 fontsize=9.8, fontweight="bold", loc="left", pad=6)
    ax.set_aspect("equal")
    ax.set_xlabel("EPSG:2180 [m]", fontsize=8)
    ax.set_ylabel("EPSG:2180 [m]", fontsize=8)
    ax.tick_params(labelsize=6.2)
    ax.ticklabel_format(useOffset=False, style="plain")
    legenda = [Line2D([0], [0], color="#ffe100", lw=2.0, label="ULDK boundary")]
    legenda += [Patch(facecolor=SAM_KOLORY[n][0], alpha=max(SAM_KOLORY[n][1], 0.4),
                      edgecolor=SAM_KOLORY[n][0], label=SAM_NAZWY[n])
                for n in SAM_RYSUJ if maski_sam.get(n) is not None and maski_sam[n].any()]
    ax.legend(handles=legenda, loc="lower right", fontsize=5.8, framealpha=0.85)

    a, _b, c, _d, e, f = siatka["transform"][:6]
    x0, x1 = c, c + siatka["szer"] * a
    y1, y0 = f, f + siatka["wys"] * e
    for ax, arrx, tyt, cmap, vmin, vmax, et in (
        (osie[1], arr_ndvi, "NDVI — Sentinel-2 L2A, 2026-10-26", "RdYlGn", -0.05, 0.9, "NDVI"),
        (osie[2], arr_ndre, "NDRE — Sentinel-2 L2A, 2026-10-26", "viridis", -0.05, 0.65, "NDRE"),
    ):
        scl_i = np.nan_to_num(scl, nan=0.0).astype(int)
        pokaz = np.where(np.isin(scl_i, [4, 5, 6, 7]), arrx, np.nan)
        im2 = ax.imshow(pokaz, extent=(x0, x1, y0, y1), origin="upper", cmap=cmap,
                        vmin=vmin, vmax=vmax, interpolation="nearest")
        for ident, g in geometrie4326.items():
            krotki = ident.split(".")[-1]
            ods = ODSUNIECIA.get(krotki, (0, 12))
            _granica(ax, g, "EPSG:32633", grubosc=1.4, opis=krotki, odsuniecie=ods,
                     strzalka=max(abs(ods[0]), abs(ods[1])) >= 18)
        ax.set_title(tyt, fontsize=9.8, fontweight="bold", loc="left", pad=6)
        ax.set_aspect("equal")
        ax.set_xlabel("EPSG:32633 [m] — 1 pixel = 10 m", fontsize=8)
        ax.set_ylabel("EPSG:32633 [m]", fontsize=8)
        ax.tick_params(labelsize=6.2)
        ax.ticklabel_format(useOffset=False, style="plain")
        cb = fig.colorbar(im2, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label(et, fontsize=7.5)
        cb.ax.tick_params(labelsize=6.2)

    fig.suptitle(tytul, fontsize=12.0, fontweight="bold", x=0.012, ha="left", y=0.985)
    fig.text(0.012, 0.012,
             "Data: ULDK/GUGiK (read 2026-11-01) · orthophoto GUGiK WMS 1.1.1, photo 2025-03-28 · "
             "Sentinel-2 L2A Earth Search, scene 2026-10-26 · SAM 3.1, run 2026-10-28. "
             "This is not a soil test or a fertiliser recommendation.",
             fontsize=6.0, color="#444")
    fig.subplots_adjust(left=0.045, right=0.985, top=0.80, bottom=0.17, wspace=0.26)
    fig.savefig(sciezka_png, bbox_inches="tight")
    plt.close(fig)
