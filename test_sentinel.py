"""Testy modułów prawdziwych: Sentinel (NDVI/NDRE, chmury) i rzeźba (brak ≠ płasko).

Uruchomienie: python test_sentinel.py
Kod 0 = wszystkie sprawdzenia zielone. Zero sieci: funkcje liczące dostają syntetyczne
tablice, a brak danych w NMT jest symulowany przez podmianę `teren.wysokosc`.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sentinel as S  # noqa: E402
import teren  # noqa: E402

WYNIKI: list[tuple[str, bool, str]] = []


def sprawdz(nazwa: str, warunek: bool, opis: str = "") -> None:
    WYNIKI.append((nazwa, bool(warunek), opis))


def test_odbicie() -> None:
    a = S.odbicie(np.array([[0, 10000, 5000]], dtype=np.uint16))
    sprawdz("odbicie: DN=0 → nan", math.isnan(float(a[0, 0])), str(a[0, 0]))
    sprawdz("odbicie: DN=10000 → 1,0", abs(float(a[0, 1]) - 1.0) < 1e-6, str(a[0, 1]))
    sprawdz("odbicie: DN=5000 → 0,5", abs(float(a[0, 2]) - 0.5) < 1e-6, str(a[0, 2]))


def test_indeksy() -> None:
    nir = np.array([0.4, 0.4, 0.0], dtype=np.float32)
    red = np.array([0.2, 0.2, 0.0], dtype=np.float32)
    re = np.array([0.1, 0.3, 0.0], dtype=np.float32)
    ndvi = S.ndvi(nir, red)
    ndre = S.ndre(nir, re)
    sprawdz("NDVI: (0,4-0,2)/(0,4+0,2)=0,333", abs(float(ndvi[0]) - 1 / 3) < 1e-6, str(ndvi[0]))
    sprawdz("NDVI: mianownik 0 → nan", math.isnan(float(ndvi[2])), str(ndvi[2]))
    sprawdz("NDRE: (0,4-0,1)/(0,4+0,1)=0,6", abs(float(ndre[0]) - 0.6) < 1e-6, str(ndre[0]))
    sprawdz("NDRE: ujemne (0,4-0,3)/(0,7)=0,143", abs(float(ndre[1]) - 1 / 7) < 1e-6, str(ndre[1]))


def test_statystyki_i_chmury() -> None:
    maska = np.array([[True, True], [True, False]])
    scl = np.array([[4, 9], [5, 9]], dtype=float)   # 3 piksele pola: 2 czyste, 1 chmura
    ndvi = np.array([[0.5, 0.9], [0.3, 0.9]], dtype=np.float32)
    ndre = np.array([[0.2, 0.9], [0.1, 0.9]], dtype=np.float32)
    st = S.statystyki(maska, scl, ndvi, ndre, "T", 0.0003)
    sprawdz("statystyki: piksele pola", st.piksele_pola == 3, str(st.piksele_pola))
    sprawdz("statystyki: użyte 2", st.piksele_uzyte == 2, str(st.piksele_uzyte))
    sprawdz("statystyki: chmury 33,3%", abs(st.chmury_pct - 33.3) < 0.1, str(st.chmury_pct))
    sprawdz("statystyki: średnia NDVI 0,4", abs(st.ndvi_srednia - 0.4) < 1e-6, str(st.ndvi_srednia))
    sprawdz("statystyki: CI rośnie z rozrzutem", st.ci95_ndvi > 0, str(st.ci95_ndvi))
    ch = S.chmury_nad_dzialka(maska, scl)
    sprawdz("chmury: czyste 66,7%", abs(ch["czyste_pct"] - 66.7) < 0.1, str(ch["czyste_pct"]))
    sprawdz("chmury: chmury 33,3%", abs(ch["chmury_pct"] - 33.3) < 0.1, str(ch["chmury_pct"]))

    try:
        S.statystyki(maska, np.full((2, 2), 9.0), ndvi, ndre, "T", 0.0003)
    except ValueError as e:
        sprawdz("statystyki: same chmury → jawny błąd", "0 pikseli" in str(e), str(e))
    else:
        sprawdz("statystyki: same chmury → jawny błąd", False, "brak wyjątku")


def test_brak_nmt_nie_jest_plasko() -> None:
    from shapely.geometry import box
    g = box(0, 0, 50, 50)
    oryginal = teren.wysokosc
    try:
        teren.wysokosc = lambda x, y, proby=3: None
        p = teren.profil_dzialki(g, odstep=20)
        sprawdz("NMT: brak danych → brak_danych=True", p["brak_danych"] is True, str(p["brak_danych"]))
        sprawdz("NMT: brak danych → różnica None, nie 0",
                p["roznica_m"] is None, str(p["roznica_m"]))
        teren.wysokosc = lambda x, y, proby=3: 175.0
        p2 = teren.profil_dzialki(g, odstep=20)
        sprawdz("NMT: dane → brak_danych=False", p2["brak_danych"] is False, str(p2["brak_danych"]))
        sprawdz("NMT: równe wysokości → różnica 0 (to już pomiar)",
                p2["roznica_m"] == 0.0, str(p2["roznica_m"]))
    finally:
        teren.wysokosc = oryginal


def test_siatka() -> None:
    from shapely.geometry import box
    s = S.zrob_siatek(box(688300, 5810300, 688500, 5810400), res=10, margines=30)
    sprawdz("siatka: dodatnie wymiary", s.szer > 0 and s.wys > 0, f"{s.szer}x{s.wys}")
    sprawdz("siatka: res 10", s.res == 10, str(s.res))
    # 260 x 160 m po marginesach → 26 x 16 px
    sprawdz("siatka: wymiary z marginesem", (s.szer, s.wys) == (26, 16), f"{s.szer}x{s.wys}")


def main() -> int:
    for t in (test_odbicie, test_indeksy, test_statystyki_i_chmury,
              test_brak_nmt_nie_jest_plasko, test_siatka):
        try:
            t()
        except Exception as e:  # noqa: BLE001
            sprawdz(t.__name__ + " — wyjątek", False, f"{type(e).__name__}: {e}")
    for nazwa, ok, opis in WYNIKI:
        print(f"{'OK ' if ok else 'BŁĄD'} | {nazwa} | {opis}")
    zle = [x for x in WYNIKI if not x[1]]
    print(f"\nWYNIK: {len(WYNIKI) - len(zle)}/{len(WYNIKI)} OK, {len(zle)} czerwonych")
    return 0 if not zle else 1


if __name__ == "__main__":
    sys.exit(main())
