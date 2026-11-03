"""S155a: historia sezonu 2026, mapy czterech terminów i teren dla pięciu działek.

Zasady, które ten skrypt trzyma jawnie:
* do wyniku wchodzi scena tylko wtedy, gdy na działce ma co najmniej 80% czystych
  pikseli SCL; odrzucone trafiają do `historia.json` z powodem,
* progi klas NDVI i próg werdyktu są zapisane w kodzie PRZED pierwszym
  uruchomieniem na danych (nie dobierane po wyniku),
* brak sceny w miesiącu i luka > 45 dni są przerwą w linii, nie interpolacją,
* `NIE WRACA` jest wynikiem tak samo pełnoprawnym jak `WRACA`,
* brak odpowiedzi NMT to `BRAK DANYCH`, nie teren płaski.

Uruchomienie (z katalogu hackathon/pole-z-gory):
    python historia.py
    python historia.py --bez-terenu      # mapa sezonu i krzywe bez GUGiK
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import numpy as np

import sentinel
import teren
import mapy

KATALOG = Path(__file__).resolve().parent
DEMO = KATALOG / "demo"
DANE = DEMO / "dane"
IMG = DEMO / "img"
CACHE = DANE / "cache-sezon"

DZIALKI = ["90/8", "90/12", "92/6", "92/10", "92/11"]
START, KONIEC = "2026-03-01", "2026-10-26"
PROG_CZYSTE_PCT = 80.0
OKRESY = [("April", 4, 4), ("May/June", 5, 6), ("July", 7, 7), ("October", 10, 10)]
ZLACZE_DNI = 45
MIESIACE_SEZONU = {(2026, m) for m in range(3, 11)}

# Progi werdyktu — zapisane przed pierwszym uruchomieniem (02.11.2026).
MIN_PIKSELI_WERDYKT = 100
PROG_WRACA_PCT = 10.0
PROG_PERCENTYL = 95
PERMUTACJE = 1000
ZIARNO = 20261102


# ────────────────────────────────────────────────────────────────────────────
# Wejście: działki
# ────────────────────────────────────────────────────────────────────────────

def wczytaj_dzialki() -> dict[str, dict]:
    """Pięć działek z `demo/dane/dzialki.json`; gdy brak — z `const DANE` strony."""
    plik = DANE / "dzialki.json"
    if plik.exists():
        return json.loads(plik.read_text(encoding="utf-8"))
    tekst = (DEMO / "index.html").read_text(encoding="utf-8")
    m = re.search(r"const DANE = (\{.*?\});\s*\n", tekst, re.S)
    if not m:
        raise RuntimeError("nie znajduję const DANE w demo/index.html")
    dane = json.loads(m.group(1))
    out = {}
    for dz in dane["dzialki"]:
        out[dz["id"]] = {"id": dz["id"], "ident": dz["ident"], "wkt": dz["wkt"],
                         "powierzchnia_ha": dz["powierzchnia_ha"],
                         "bbox32633": dz["bbox32633"]}
    DANE.mkdir(parents=True, exist_ok=True)
    plik.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def geometrie(dzialki: dict[str, dict]):
    from pyproj import Transformer
    from shapely import wkt
    from shapely.ops import transform as sh_transform

    do_33 = Transformer.from_crs("EPSG:4326", "EPSG:32633", always_xy=True)
    do_18 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
    g33, g18 = {}, {}
    for ident, dz in dzialki.items():
        g = wkt.loads(dz["wkt"])
        g33[ident] = sh_transform(do_33.transform, g)
        g18[ident] = sh_transform(do_18.transform, g)
    return g33, g18


def przygotuj_siatke(g33: dict[str, object]):
    from shapely.ops import unary_union

    unia = unary_union(list(g33.values()))
    siatka = sentinel.zrob_siatek(unia, res=10.0, margines=30.0)
    maski = {ident: sentinel.maska_dzialki(g, siatka) for ident, g in g33.items()}
    return siatka, maski


def kadr(siatka, bbox, margines: float = 25.0):
    """Wycinek siatki wokół działki (mapa tylko w obrębie działki)."""
    x0, y0, x1, y1 = bbox
    x0 -= margines
    y0 -= margines
    x1 += margines
    y1 += margines
    a, _b, c, _d, e, f = siatka.transform[:6]
    kol0 = max(0, int(math.floor((x0 - c) / a)))
    kol1 = min(siatka.szer, int(math.ceil((x1 - c) / a)))
    wier0 = max(0, int(math.floor((f - y1) / -e)))
    wier1 = min(siatka.wys, int(math.ceil((f - y0) / -e)))
    extent = (c + kol0 * a, c + kol1 * a, f + wier1 * e, f + wier0 * e)
    return (slice(wier0, wier1), slice(kol0, kol1)), extent


# ────────────────────────────────────────────────────────────────────────────
# STAC + odczyt scen
# ────────────────────────────────────────────────────────────────────────────

def z_proba(fn, opis: str, proby: int = 3):
    ostatni = None
    for i in range(proby):
        try:
            return fn()
        except Exception as blad:  # noqa: BLE001
            ostatni = blad
            time.sleep(0.5 + i)
    raise RuntimeError(f"{opis}: po {proby} próbach nie udało się ({type(ostatni).__name__}: {ostatni})")


def szukaj_scen(bbox, proby: int = 3):
    return z_proba(lambda: sentinel.szukaj_scen(bbox, START, KONIEC, ile=500),
                   "STAC Earth Search", proby=proby)


def prog_przyjecia(st: dict) -> bool:
    """Jedno miejsce, w którym zapada próg 80% — test sprawdza właśnie je."""
    return st["czyste_pct"] >= PROG_CZYSTE_PCT and st["piksele_uzyte"] > 0


def status_terenu(n_punktow: int, n_danych: int, n_blad: int) -> str:
    """BRAK_USLUGI (sieć) różni się od BRAK DANYCH (serwis odpowiedział 0/pusto)."""
    if n_punktow == 0:
        return "BRAK DANYCH"
    if n_danych == 0 and n_blad == n_punktow:
        return "BRAK_USLUGI"
    brak_pct = 100.0 * (n_punktow - n_danych) / n_punktow
    return "BRAK DANYCH" if brak_pct > 20.0 else "OK"


def statystyki(ndvi_arr, ndre_arr, maska, scl_i):
    czyste = maska & np.isin(scl_i, list(sentinel.SCL_CZYSTE))
    uzyte = czyste & np.isfinite(ndvi_arr) & np.isfinite(ndre_arr)
    n_pola = int(maska.sum())
    n_czyste = int(czyste.sum())
    n_uzyte = int(uzyte.sum())
    pct = 100.0 * n_czyste / n_pola if n_pola else 0.0
    if n_uzyte:
        v_ndvi = ndvi_arr[uzyte].astype(np.float64)
        v_ndre = ndre_arr[uzyte].astype(np.float64)
        ndvi_sr, ndre_sr = float(v_ndvi.mean()), float(v_ndre.mean())
    else:
        ndvi_sr = ndre_sr = None
    return {
        "czyste_pct": round(pct, 1),
        "piksele_pola": n_pola,
        "piksele_czyste": n_czyste,
        "piksele_uzyte": n_uzyte,
        "ndvi_srednia": None if ndvi_sr is None else round(ndvi_sr, 4),
        "ndre_srednia": None if ndre_sr is None else round(ndre_sr, 4),
    }


def przetworz_scene(item, px, siatka, maski):
    data = sentinel.data_sceny(item)
    scena = item["id"]
    bledy = []

    def pasmo(nazwa, metoda):
        url = px.adres(sentinel.href_pasma(item, nazwa))
        return z_proba(lambda: sentinel.wczytaj_pasmo(url, siatka, metoda),
                       f"{scena} {nazwa}")

    try:
        scl = pasmo("SCL", "nearest")
    except Exception as blad:  # noqa: BLE001
        return {"scena": scena, "data": data, "blad": str(blad), "pct": {},
                "przyjete": {}, "stats": {}}
    scl_i = np.nan_to_num(scl, nan=0.0).astype(np.uint8)
    pct = {}
    for ident, maska in maski.items():
        n = int(maska.sum())
        czyste = int((maska & np.isin(scl_i, list(sentinel.SCL_CZYSTE))).sum())
        pct[ident] = round(100.0 * czyste / n, 1) if n else 0.0
    if not any(v >= PROG_CZYSTE_PCT for v in pct.values()):
        return {"scena": scena, "data": data, "pct": pct, "przyjete": {},
                "stats": {}, "ndvi": None, "scl": None, "blad": None}

    try:
        b04 = sentinel.odbicie(pasmo("B04", "bilinear"))
        b08 = sentinel.odbicie(pasmo("B08", "bilinear"))
        b05 = sentinel.odbicie(pasmo("B05", "bilinear"))
        ndvi_arr = sentinel.ndvi(b08, b04)
        ndre_arr = sentinel.ndre(b08, b05)
    except Exception as blad:  # noqa: BLE001
        return {"scena": scena, "data": data, "pct": pct, "przyjete": {},
                "stats": {}, "ndvi": None, "scl": None,
                "blad": f"pasma po 3 próbach: {blad}"}

    stats, przyjete = {}, {}
    for ident, maska in maski.items():
        st = statystyki(ndvi_arr, ndre_arr, maska, scl_i)
        stats[ident] = st
        przyjete[ident] = prog_przyjecia(st)
    return {"scena": scena, "data": data, "pct": pct, "przyjete": przyjete,
            "stats": stats, "ndvi": ndvi_arr, "ndre": ndre_arr, "scl": scl_i, "blad": None}


def wybierz_dla_dzialki(sceny: list[dict], ident: str):
    """Jeden termin na okres: najczystsza scena; przy remisie wcześniejsza data."""
    kand = [s for s in sceny if s["przyjete"].get(ident)]
    out = []
    for nazwa, m1, m2 in OKRESY:
        k = [s for s in kand if m1 <= int(s["data"][5:7]) <= m2]
        if not k:
            out.append({"okres": nazwa, "data": None, "scena": None, "czyste_pct": 0.0,
                        "ndvi": None, "scl": None, "ndvi_srednia": None,
                        "brak": f"brak przyjętej sceny w okresie {nazwa}"})
            continue
        best = max(k, key=lambda s: (s["pct"][ident], -date.fromisoformat(s["data"]).toordinal()))
        out.append({"okres": nazwa, "data": best["data"], "scena": best["scena"],
                    "czyste_pct": best["pct"][ident], "ndvi": best["ndvi"],
                    "scl": best["scl"], "ndvi_srednia": best["stats"][ident]["ndvi_srednia"],
                    "brak": None})
    return out


def odcinki_krzywej(punkty: list[tuple[date, float]]):
    """Dzieli linię na odcinki: luka > 45 dni albo miesiąc bez przyjętej sceny."""
    if not punkty:
        return []
    miesiace = {(p[0].year, p[0].month) for p in punkty}
    odcinki = [[punkty[0]]]
    for poprzedni, biezacy in zip(punkty, punkty[1:]):
        luka = (biezacy[0] - poprzedni[0]).days
        brak_miesiaca = False
        rok, mies = poprzedni[0].year, poprzedni[0].month
        while (rok, mies) < (biezacy[0].year, biezacy[0].month):
            mies += 1
            if mies > 12:
                mies = 1
                rok += 1
            if (rok, mies) not in miesiace:
                brak_miesiaca = True
                break
        if luka > ZLACZE_DNI or brak_miesiaca:
            odcinki.append([biezacy])
        else:
            odcinki[-1].append(biezacy)
    return odcinki


# ────────────────────────────────────────────────────────────────────────────
# Teren
# ────────────────────────────────────────────────────────────────────────────

def punkty_terenowe(siatka, maska):
    """Piksele działki na siatce 10 m — dokładnie te same, co NDVI."""
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:32633", "EPSG:2180", always_xy=True)
    wiersze, kolumny = np.nonzero(maska)
    punkty = []
    for w, k in zip(wiersze.tolist(), kolumny.tolist()):
        x = siatka.transform.c + (k + 0.5) * siatka.transform.a
        y = siatka.transform.f + (w + 0.5) * siatka.transform.e
        x18, y18 = tr.transform(x, y)
        punkty.append({"w": w, "k": k, "x": x, "y": y,
                       "x2180": round(x18, 2), "y2180": round(y18, 2)})
    return punkty


def wczytaj_cache() -> dict:
    plik = DANE / "teren-cache.json"
    if not plik.exists():
        return {}
    try:
        return json.loads(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — uszkodzony cache nie może zabić przebiegu
        return {}


def wybierz_punkty_abc(wartosci, maska, centrum):
    """A/B/C tylko spośród pikseli, które mapa rysuje (maska + wysokość).

    S155b2: punkt C na 92/10 stał na pikselu, który był w masce, ale miał biały
    kolor (górny koniec skali `terrain`) i wyglądał jak tło. Zaostrzamy obie
    strony: wybór wyłącznie z maski (tu) i skala bez bieli (`mapy.CMAP_TEREN`).
    """
    rysowane = [p for p in wartosci if bool(maska[p["w"], p["k"]])]
    if not rysowane:
        return {}
    cx, cy = centrum
    a = min(rysowane, key=lambda p: p["h_m"])
    c = max(rysowane, key=lambda p: p["h_m"])
    b = min(rysowane, key=lambda p: (p["x"] - cx) ** 2 + (p["y"] - cy) ** 2)
    return {"A": a, "B": b, "C": c}


def zbierz_teren(g33, siatka, maski, watki: int = 10):
    cache = wczytaj_cache()
    wszystkie_punkty = {}
    for ident in DZIALKI:
        wszystkie_punkty[ident] = punkty_terenowe(siatka, maski[ident])

    unikalne = {}
    for ident, punkty in wszystkie_punkty.items():
        for p in punkty:
            unikalne[f"{p['x2180']:.2f},{p['y2180']:.2f}"] = (p["x2180"], p["y2180"])
    wejscie = list(unikalne.values())

    t0 = time.time()
    odczyty = teren.wysokosci_punktow(wejscie, watki=watki, proby=3, cache=cache)
    mapa = {f"{o['x2180']:.2f},{o['y2180']:.2f}": o for o in odczyty}
    print(f"  NMT: {len(odczyty)} punktów w {time.time() - t0:.1f} s, "
          f"ok={sum(1 for o in odczyty if o['status'] == 'ok')}, "
          f"zero={sum(1 for o in odczyty if o['status'] == 'zero')}, "
          f"pusto={sum(1 for o in odczyty if o['status'] == 'pusto')}, "
          f"blad={sum(1 for o in odczyty if o['status'] == 'blad')}")

    # cache zapisujemy tylko dla odpowiedzi, które są odpowiedzią serwisu
    for k, o in mapa.items():
        if o["status"] in ("ok", "zero", "pusto"):
            cache[k] = {"h_m": o["h_m"], "status": o["status"]}

    wynik = {}
    for ident, punkty in wszystkie_punkty.items():
        h_grid = np.full((siatka.wys, siatka.szer), np.nan, dtype=np.float32)
        wartosci = []
        for p in punkty:
            o = mapa.get(f"{p['x2180']:.2f},{p['y2180']:.2f}", {})
            if o.get("status") == "ok":
                h_grid[p["w"], p["k"]] = o["h_m"]
                wartosci.append({"x": p["x"], "y": p["y"], "h_m": o["h_m"],
                                 "w": p["w"], "k": p["k"]})
        n = len(punkty)
        n_ok = len(wartosci)
        brak_pct = 100.0 * (n - n_ok) / n if n else 100.0
        n_blad = sum(1 for p in punkty
                     if mapa.get(f"{p['x2180']:.2f},{p['y2180']:.2f}", {}).get("status") == "blad")
        status = status_terenu(n, n_ok, n_blad)
        if status == "BRAK_USLUGI":
            wynik[ident] = {"status": "BRAK_USLUGI", "n_punktow": n, "n_danych": 0,
                            "brak_pct": 100.0, "h_grid": h_grid, "punkty": {}}
            continue
        if status == "OK" and wartosci:
            bbox = g33[ident].bounds
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            wybrane = wybierz_punkty_abc(wartosci, maski[ident], (cx, cy))
            punkty_abc = {
                k: {"x": round(p["x"], 1), "y": round(p["y"], 1),
                    "h_m": round(p["h_m"], 2)}
                for k, p in wybrane.items()
            }
            h_min = round(min(p["h_m"] for p in wartosci), 2)
            h_max = round(max(p["h_m"] for p in wartosci), 2)
            roznica = round(h_max - h_min, 2)
        else:
            punkty_abc = {}
            h_min = h_max = roznica = None
        wynik[ident] = {"status": status, "n_punktow": n, "n_danych": n_ok,
                        "brak_pct": round(brak_pct, 1), "h_grid": h_grid,
                        "punkty": punkty_abc, "h_min_m": h_min, "h_max_m": h_max,
                        "roznica_m": roznica}

    (DANE / "teren-cache.json").write_text(
        json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    if any(v.get("status") == "BRAK_USLUGI" for v in wynik.values()):
        raise RuntimeError("GUGiK NMT nie odpowiedział po 3 próbach — to awaria usługi, "
                           "nie brak pokrycia; poprzedni wynik zostaje")
    return wynik


# ────────────────────────────────────────────────────────────────────────────
# Słabe miejsca
# ────────────────────────────────────────────────────────────────────────────

def _rangi(x: np.ndarray) -> np.ndarray:
    n = len(x)
    order = np.argsort(x, kind="stable")
    r = np.empty(n, dtype=np.float64)
    r[order] = np.arange(1, n + 1, dtype=np.float64)
    i = 0
    while i < n:
        j = i + 1
        while j < n and x[order[j]] == x[order[i]]:
            j += 1
        if j - i > 1:
            srednia = (i + 1 + j) / 2.0
            r[order[i:j]] = srednia
        i = j
    return r


def spearman(a: np.ndarray, b: np.ndarray):
    if len(a) < 3:
        return None
    ra, rb = _rangi(a), _rangi(b)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def analiza_slabe(terminy, ident, maska, h_grid):
    """Czy najsłabsze 25% wraca w ≥3 z 4 terminów — i ile daje przypadek."""
    dostepne = [t for t in terminy if t["ndvi"] is not None]
    if len(dostepne) < 4:
        return {"n_wspolnych": 0, "odsetek_w_3z4": None, "przypadek": None,
                "werdykt": "ZA MAŁO TERMINÓW", "terminy": [],
                "brak": f"przyjęte terminy: {len(dostepne)} z 4"}
    wspolna = maska.copy()
    for t in dostepne:
        wspolna &= np.isfinite(t["ndvi"])
    n = int(wspolna.sum())
    if n == 0:
        return {"n_wspolnych": 0, "odsetek_w_3z4": None, "przypadek": None,
                "werdykt": "ZA MAŁO PIKSELI", "terminy": [], "brak": "0 wspólnych pikseli"}

    wartosci = [t["ndvi"][wspolna].astype(np.float64) for t in dostepne]
    k = max(1, int(round(0.25 * n)))
    weak = np.zeros(n, dtype=np.int8)
    for v in wartosci:
        kolejnosc = np.argsort(v, kind="stable")
        weak[kolejnosc[:k]] += 1
    obserwowane = int((weak >= 3).sum())
    pct = 100.0 * obserwowane / n

    rng = np.random.default_rng(ZIARNO)
    null = []
    for _ in range(PERMUTACJE):
        licznik = np.zeros(n, dtype=np.int8)
        for v in wartosci:
            p = rng.permutation(v)
            idx = np.argpartition(p, k - 1)[:k]
            licznik[idx] += 1
        null.append(int((licznik >= 3).sum()))
    null_arr = np.asarray(null, dtype=np.float64)
    p95 = float(np.percentile(null_arr, PROG_PERCENTYL))
    p_value = (1 + int((null_arr >= obserwowane).sum())) / (PERMUTACJE + 1)

    h = h_grid[wspolna]
    korelacje = []
    for t, v in zip(dostepne, wartosci):
        dobra = np.isfinite(h) & np.isfinite(v)
        rho = spearman(h[dobra], v[dobra])
        korelacje.append({"data": t["data"], "okres": t["okres"], "n": int(dobra.sum()),
                          "rho": None if rho is None else round(rho, 4)})

    if n < MIN_PIKSELI_WERDYKT:
        werdykt = "ZA MAŁO PIKSELI"
    elif pct >= PROG_WRACA_PCT and pct > p95:
        werdykt = "WRACA"
    else:
        werdykt = "NIE WRACA"

    return {
        "n_wspolnych": n,
        "odsetek_w_3z4": round(pct, 1),
        "liczba_pikseli_w_3z4": obserwowane,
        "przypadek": {
            "permutacje": PERMUTACJE,
            "ziarno": ZIARNO,
            "srednia_pct": round(100.0 * float(null_arr.mean()) / n, 1),
            "p95_pct": round(100.0 * p95 / n, 1),
            "p_value": round(p_value, 4),
            "prog_pct": PROG_WRACA_PCT,
            "prog_percentyl": PROG_PERCENTYL,
        },
        "korelacja_wysokosc_ndvi": korelacje,
        "werdykt": werdykt,
        "regula": ("ZA MAŁO PIKSELI gdy n<100; WRACA gdy odsetek>=10% i > p95 przypadku; "
                   "w przeciwnym razie NIE WRACA"),
    }


# ────────────────────────────────────────────────────────────────────────────
# Zapis demo
# ────────────────────────────────────────────────────────────────────────────

def zapisz_atomowo(sciezka: Path, tekst: str):
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tmp = sciezka.with_suffix(sciezka.suffix + ".tmp")
    tmp.write_text(tekst, encoding="utf-8")
    os.replace(tmp, sciezka)


def _werdykt_slownie(kod: str):
    return {
        "WRACA": ("słabe miejsce wraca w co najmniej 3 z 4 terminów",
                  "the weak spot returns in at least 3 of 4 dates"),
        "NIE WRACA": ("słabe miejsce nie wraca częściej niż przypadek",
                      "the weak spot does not return more often than chance"),
        "ZA MAŁO PIKSELI": ("za mało pikseli, żeby orzec — nie zgadujemy",
                            "too few pixels to decide — no guess"),
        "ZA MAŁO TERMINÓW": ("za mało terminów, żeby orzec",
                             "too few dates to decide"),
    }.get(kod, (kod, kod))


def zbuduj_demo_js(dzialki, sezony, slabe, teren_wynik):
    out = {}
    for ident, dz in dzialki.items():
        wybor = sezony[ident]
        terminy = [{"data": t["data"], "czyste_pct": t["czyste_pct"],
                    "ndvi": t.get("ndvi_srednia")} for t in wybor]
        sl = slabe[ident]
        ter = teren_wynik.get(ident, {})
        kod = sl.get("werdykt", "ZA MAŁO PIKSELI")
        pl, en = _werdykt_slownie(kod)
        out[ident] = {
            "sezon_png": f"img/{dz.get('slug', ident.replace('/', '-'))}-sezon.png",
            "teren_png": f"img/{dz.get('slug', ident.replace('/', '-'))}-teren.png",
            "terminy": terminy,
            "werdykt": kod, "werdykt_pl": pl, "werdykt_en": en,
            "slabe": {k: sl.get(k) for k in ("n_wspolnych", "odsetek_w_3z4",
                                             "liczba_pikseli_w_3z4", "przypadek",
                                             "korelacja_wysokosc_ndvi")},
            "teren": {k: ter.get(k) for k in ("status", "n_punktow", "n_danych",
                                              "brak_pct", "h_min_m", "h_max_m",
                                              "roznica_m", "punkty")},
            "progi_ndvi": mapy.PROGI_NDVI,
        }
    tekst = "// S155a — dane zakładek Season i Terrain (generowane przez historia.py)\n"
    tekst += "const S155A = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n"
    zapisz_atomowo(DANE / "s155a.js", tekst)
    return out


# ────────────────────────────────────────────────────────────────────────────
# Główny przebieg
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bez-terenu", action="store_true", help="pomiń GUGiK NMT")
    p.add_argument("--watki", type=int, default=6)
    p.add_argument("--sucho", action="store_true", help="tylko sprawdź STAC, nic nie zapisuj")
    args = p.parse_args()

    t0 = time.time()
    DANE.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    dzialki = wczytaj_dzialki()
    g33, _g18 = geometrie(dzialki)
    siatka, maski = przygotuj_siatke(g33)
    print(f"Siatka: {siatka.szer}×{siatka.wys} px, 10 m, EPSG:32633; działek: {len(dzialki)}")

    bbox = [17.7684, 52.4096, 17.7761, 52.4127]
    try:
        sceny = szukaj_scen(bbox)
    except Exception as blad:  # noqa: BLE001
        print(f"BRAK: STAC nie odpowiedział po 3 próbach — {blad}")
        print("Nie nadpisuję poprzedniego wyniku.")
        return 2
    print(f"STAC: {len(sceny)} scen L2A, {START}..{KONIEC}")
    if args.sucho:
        return 0

    wyniki = []
    with sentinel.Przekierowanie() as px:
        with ThreadPoolExecutor(max_workers=max(1, args.watki)) as pula:
            zadania = {pula.submit(przetworz_scene, it, px, siatka, maski): it for it in sceny}
            for i, fut in enumerate(as_completed(zadania), 1):
                it = zadania[fut]
                try:
                    r = fut.result()
                except Exception as blad:  # noqa: BLE001
                    r = {"scena": it["id"], "data": sentinel.data_sceny(it), "pct": {},
                         "przyjete": {}, "stats": {}, "ndvi": None, "scl": None,
                         "blad": f"wyjątek: {type(blad).__name__}: {blad}"}
                wyniki.append(r)
                stan = "OK" if r.get("ndvi") is not None else "ODRZUCONA"
                print(f"[{i}/{len(sceny)}] {r['data']} {r['scena'][:34]:34s} {stan}", flush=True)

    bledy_sieci = [r for r in wyniki if r.get("blad") and "SCL" in r["blad"]]
    if len(bledy_sieci) > max(3, int(0.10 * len(wyniki))):
        print(f"BRAK: {len(bledy_sieci)} scen bez SCL po 3 próbach — nie nadpisuję wyniku.")
        return 2
    if not any(r.get("ndvi") is not None for r in wyniki):
        print("BRAK: żadna scena nie ma pasm po 3 próbach — nie nadpisuję wyniku.")
        return 2

    wyniki.sort(key=lambda r: (r["data"], r["scena"]))
    przyjete = [r for r in wyniki if r.get("ndvi") is not None]
    hist_dzialki = {}
    for ident in DZIALKI:
        przy = [r for r in przyjete if r["przyjete"].get(ident)]
        odrz = []
        for r in wyniki:
            if r["przyjete"].get(ident):
                continue
            if r.get("blad"):
                powod = r["blad"]
            else:
                powod = f"{r['pct'].get(ident, 0):.1f}% czystych < {PROG_CZYSTE_PCT:.0f}%"
            odrz.append({"data": r["data"], "scena": r["scena"],
                         "czyste_pct": r["pct"].get(ident), "powod": powod})
        hist_dzialki[ident] = {
            "sceny": [{"data": r["data"], "scena": r["scena"], **r["stats"][ident]}
                      for r in przy],
            "odrzucone": odrz,
            "n_przyjetych": len(przy),
            "n_odrzuconych": len(odrz),
        }
    historia = {
        "zakres": {"od": START, "do": KONIEC},
        "zrodlo": "Earth Search STAC, kolekcja sentinel-2-l2a",
        "prog_czystych_pct": PROG_CZYSTE_PCT,
        "scl_czyste": sorted(sentinel.SCL_CZYSTE),
        "siatka": {"szer": siatka.szer, "wys": siatka.wys, "res_m": 10, "epsg": "EPSG:32633"},
        "scen_w_stac": len(sceny),
        "dzialki": hist_dzialki,
    }
    zapisz_atomowo(DANE / "historia.json", json.dumps(historia, ensure_ascii=False, indent=1))
    progi = {
        "progi_ndvi": mapy.PROGI_NDVI,
        "klasy": mapy.KLASY_NDVI,
        "kolory": mapy.KOLORY_NDVI,
        "regula_terminow": "jeden termin na okres (kwiecień, maj/czerwiec, lipiec, październik); "
                           "najwyższy odsetek czystych; remis → wcześniejsza data",
        "prog_czystych_pct": PROG_CZYSTE_PCT,
        "zlacze_dni": ZLACZE_DNI,
        "werdykt": {"min_pikseli": MIN_PIKSELI_WERDYKT, "prog_pct": PROG_WRACA_PCT,
                    "prog_percentyl": PROG_PERCENTYL, "permutacje": PERMUTACJE,
                    "ziarno": ZIARNO},
    }
    zapisz_atomowo(DANE / "progi-klas.json", json.dumps(progi, ensure_ascii=False, indent=1))

    # ── terminy, mapy, krzywe
    sezony = {}
    slabe = {}
    teren_wynik = {}
    if not args.bez_terenu:
        print("NMT GUGiK — siatka 10 m w pikselach działek...")
        try:
            teren_wynik = zbierz_teren(g33, siatka, maski, watki=max(4, args.watki + 4))
        except RuntimeError as blad:
            print(f"BRAK: {blad}. Nie nadpisuję terenu ani słabych miejsc.")
            return 3

    for ident in DZIALKI:
        wybor = wybierz_dla_dzialki(przyjete, ident)
        sezony[ident] = wybor
        kadr_sl, extent = kadr(siatka, dzialki[ident]["bbox32633"])
        obrazy = []
        for t in wybor:
            if t["ndvi"] is None:
                obrazy.append(np.full((siatka.wys, siatka.szer), np.nan, dtype=np.float32))
            else:
                czyste = maski[ident] & np.isin(t["scl"], list(sentinel.SCL_CZYSTE))
                arr = np.where(czyste & np.isfinite(t["ndvi"]), t["ndvi"], np.nan)
                obrazy.append(arr[kadr_sl])
        maska_kadr = maski[ident][kadr_sl]
        sciezka = IMG / f"{ident.replace('/', '-')}-sezon.png"
        tytul = f"Parcel {ident} — season 2026, four dates"
        mapy.rysuj_sezon(sciezka, [o for o in obrazy], maska_kadr, extent, wybor, tytul)
        print(f"  MAPA {sciezka.name}")

        punkty = [(date.fromisoformat(s["data"]), s["stats"][ident]["ndvi_srednia"])
                  for s in przyjete if s["przyjete"].get(ident) and s["stats"][ident]["ndvi_srednia"] is not None]
        # średnia po dacie, gdy tego samego dnia są dwie sceny
        po_dacie = {}
        for d, v in punkty:
            po_dacie.setdefault(d, []).append(v)
        punkty = sorted((d, float(np.mean(v))) for d, v in po_dacie.items())
        odcinki = odcinki_krzywej(punkty)
        # Tylko cztery terminy z map — nie wszystkie przyjęte sceny (S155a).
        terminy_krzywej = [{"data": t["data"], "czyste_pct": t["czyste_pct"],
                            "ndvi": t["ndvi_srednia"]}
                           for t in wybor if t["data"] and t["ndvi_srednia"] is not None]
        sciezka_k = IMG / f"{ident.replace('/', '-')}-krzywa.png"
        mapy.rysuj_krzywa(sciezka_k, punkty, odcinki, terminy_krzywej,
                          f"Parcel {ident} — mean NDVI through season 2026")
        print(f"  KRZYWA {sciezka_k.name}")

        # słabe miejsca na czterech terminach mapy
        terminy_ndvi = []
        for t in wybor:
            if t["ndvi"] is None:
                arr = None
            else:
                czyste = maski[ident] & np.isin(t["scl"], list(sentinel.SCL_CZYSTE))
                arr = np.where(czyste & np.isfinite(t["ndvi"]), t["ndvi"], np.nan)
            terminy_ndvi.append({"data": t["data"] or "—", "okres": t["okres"],
                                 "ndvi": arr})
        h_grid = teren_wynik.get(ident, {}).get("h_grid")
        if h_grid is None:
            h_grid = np.full((siatka.wys, siatka.szer), np.nan, dtype=np.float32)
        slabe[ident] = analiza_slabe(terminy_ndvi, ident, maski[ident], h_grid)
        slabe[ident]["terminy"] = [{"data": t["data"], "czyste_pct": t["czyste_pct"]}
                                   for t in wybor]
        print(f"  WERDYKT {ident}: {slabe[ident]['werdykt']} "
              f"(n={slabe[ident]['n_wspolnych']})")

    # ── teren: mapy + JSON
    teren_json = {}
    for ident in DZIALKI:
        tr = teren_wynik.get(ident, {"status": "BRAK_USLUGI", "h_grid": None})
        kadr_sl, extent = kadr(siatka, dzialki[ident]["bbox32633"])
        if tr.get("h_grid") is None:
            tr["h_grid"] = np.full((siatka.wys, siatka.szer), np.nan, dtype=np.float32)
        arr = tr["h_grid"][kadr_sl]
        maska_kadr = maski[ident][kadr_sl]
        if tr["status"] == "OK":
            tytul = (f"Parcel {ident} — terrain {tr['h_min_m']:.1f}–{tr['h_max_m']:.1f} m, "
                     f"{tr['roznica_m']:.1f} m difference")
        else:
            tytul = f"Parcel {ident} — terrain: BRAK DANYCH"
        sciezka = IMG / f"{ident.replace('/', '-')}-teren.png"
        mapy.rysuj_teren(sciezka, arr, maska_kadr, extent, tytul, tr.get("punkty", {}),
                         tr["status"])
        teren_json[ident] = {
            "status": tr["status"], "odstep_m": 10,
            "n_punktow": tr.get("n_punktow"), "n_danych": tr.get("n_danych"),
            "brak_pct": tr.get("brak_pct"), "h_min_m": tr.get("h_min_m"),
            "h_max_m": tr.get("h_max_m"), "roznica_m": tr.get("roznica_m"),
            "punkty": tr.get("punkty", {}),
            "zrodlo": "GUGiK NMT GetHByXY (EPSG:2180)",
            "data_odczytu": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "png": f"img/{ident.replace('/', '-')}-teren.png",
            "uwaga": "0 albo pusta odpowiedź to brak danych, nie wysokość; >20% braków = BRAK DANYCH",
        }
        print(f"  TEREN {sciezka.name}: {tr['status']}")
    zapisz_atomowo(DANE / "teren-mapa.json", json.dumps(teren_json, ensure_ascii=False, indent=1))

    zapisz_atomowo(DANE / "slabe-miejsca.json", json.dumps({
        "progi": {"min_pikseli": MIN_PIKSELI_WERDYKT, "prog_pct": PROG_WRACA_PCT,
                  "prog_percentyl": PROG_PERCENTYL, "permutacje": PERMUTACJE,
                  "ziarno": ZIARNO},
        "regula": ("Najsłabsze 25% pikseli w każdym z 4 terminów; werdykt WRACA, gdy "
                   "odsetek pikseli słabych w ≥3 terminach wynosi ≥10% i przekracza 95. "
                   "percentyl permutacji (1000 prób, stałe ziarno); poniżej 100 wspólnych "
                   "pikseli → ZA MAŁO PIKSELI."),
        "dzialki": slabe,
    }, ensure_ascii=False, indent=1))

    # ── dane dla zakładek strony
    zbuduj_demo_js(dzialki, sezony, slabe, teren_wynik)

    print(f"\nGOTOWE w {time.time() - t0:.1f} s")
    for ident in DZIALKI:
        h = hist_dzialki[ident]
        print(f"  {ident:6s}: przyjęte {h['n_przyjetych']:3d}, odrzucone {h['n_odrzuconych']:3d}, "
              f"werdykt {slabe[ident]['werdykt']}, teren {teren_json[ident]['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
