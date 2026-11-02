"""Rzeźba terenu z GUGiK — odczyt wysokości w punktach działki.

Granica, której ten moduł pilnuje: **brak danych to nie „teren płaski"**. Usługa
NMT GUGiK potrafi odpowiedzieć `200` i zwrócić `0` albo pustą treść — wtedy wynik
mówi `brak_danych: true`, a nie „różnica 0 m". Wysokość `0` nie jest wysokością
terenu w Mąkownicy (około 175 m n.p.m.), więc traktujemy ją jako brak odpowiedzi.

Źródło: `https://services.gugik.gov.pl/nmt/` (GetHByXY, EPSG:2180). Odczyt ma datę.
To jest NMT (model terenu, bez budynków i roślinności), nie pomiar GPS i nie
badanie gleby.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request

SERWIS = "https://services.gugik.gov.pl/nmt/"


def _get(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "pole-z-gory/1.0"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace").strip()


def wysokosc(x2180: float, y2180: float, proby: int = 3) -> float | None:
    """Wysokość w jednym punkcie albo None (brak danych / odpowiedź nie liczbowa / 0)."""
    q = urllib.parse.urlencode({"request": "GetHByXY", "x": f"{x2180:.2f}", "y": f"{y2180:.2f}",
                                "crs": "EPSG:2180"})
    for proba in range(proby):
        try:
            t = _get(SERWIS + "?" + q)
        except Exception:
            t = ""
        if re.fullmatch(r"-?\d+(?:[.,]\d+)?", t or ""):
            h = float(t.replace(",", "."))
            if h > 0:  # 0 = brak danych, nie teren na poziomie morza
                return h
        time.sleep(0.3 * (proba + 1))
    return None


def punkty_w_dzialce(geom2180, odstep: float = 20.0, maks: int = 25) -> list[tuple[float, float]]:
    """Siatka punktów wewnątrz obrysu działki (min 1 punkt — reprezentatywny)."""
    from shapely.geometry import Point

    minx, miny, maxx, maxy = geom2180.bounds
    punkty: list[tuple[float, float]] = []
    y = miny + odstep / 2
    while y < maxy and len(punkty) < maks:
        x = minx + odstep / 2
        while x < maxx and len(punkty) < maks:
            p = Point(x, y)
            if geom2180.contains(p):
                punkty.append((round(x, 2), round(y, 2)))
            x += odstep
        y += odstep
    if not punkty:
        p = geom2180.representative_point()
        punkty.append((round(p.x, 2), round(p.y, 2)))
    return punkty


def profil_dzialki(geom2180, odstep: float = 25.0) -> dict:
    """Wysokości w siatce punktów + statystyka. `brak_danych` jest osobnym polem."""
    t0 = time.time()
    punkty = punkty_w_dzialce(geom2180, odstep=odstep)
    odczyty = []
    for x, y in punkty:
        h = wysokosc(x, y)
        odczyty.append({"x2180": x, "y2180": y, "h_m": h})
    wartosci = [o["h_m"] for o in odczyty if o["h_m"] is not None]
    brak = len(wartosci) == 0
    wynik = {
        "zrodlo": "GUGiK NMT GetHByXY (EPSG:2180)",
        "data_odczytu": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "punkty": odczyty,
        "n_punktow": len(odczyty),
        "n_danych": len(wartosci),
        "brak_danych": brak,
        "czas_s": round(time.time() - t0, 2),
    }
    if brak:
        wynik.update({"h_min_m": None, "h_max_m": None, "h_srednia_m": None,
                      "roznica_m": None,
                      "komunikat": "GUGiK nie zwrócił wysokości w żadnym punkcie — to brak danych, nie teren płaski"})
    else:
        wynik.update({
            "h_min_m": round(min(wartosci), 2),
            "h_max_m": round(max(wartosci), 2),
            "h_srednia_m": round(sum(wartosci) / len(wartosci), 2),
            "roznica_m": round(max(wartosci) - min(wartosci), 2),
            "komunikat": f"NMT w {len(wartosci)} z {len(odczyty)} punktów",
        })
    return wynik
