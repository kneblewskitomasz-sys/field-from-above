"""Testy S155a na atrapach — bez sieci, bez GUGiK, bez STAC.

Sprawdzają miejsca, w których wynik może kłamać po cichu:
* próg 80% czystych (scena 50% nie wchodzi),
* NMT zwracające 0 daje BRAK DANYCH, nie płaski teren,
* reguła wyboru czterech terminów,
* przerwy w krzywej (luka > 45 dni i miesiąc bez sceny),
* werdykt słabych miejsc i stałe ziarno permutacji,
* progi zapisane w kodzie przed przebiegiem.
"""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import numpy as np

import historia
import mapy
import sentinel
import teren


class TestProgCzystych(unittest.TestCase):
    def test_scena_50_proc_nie_wchodzi(self):
        maska = np.ones((10, 10), dtype=bool)
        scl = np.full((10, 10), 4, dtype=np.uint8)
        scl[:5, :] = 8  # połowa działki w chmurze
        ndvi = np.full((10, 10), 0.5, dtype=np.float32)
        ndre = np.full((10, 10), 0.3, dtype=np.float32)
        st = historia.statystyki(ndvi, ndre, maska, scl)
        self.assertEqual(st["czyste_pct"], 50.0)
        self.assertEqual(st["piksele_czyste"], 50)
        self.assertEqual(st["piksele_uzyte"], 50)
        self.assertFalse(historia.prog_przyjecia(st),
                         "scena z 50% czystych nie może wejść do wyniku")

    def test_scena_80_proc_wchodzi(self):
        maska = np.ones((10, 10), dtype=bool)
        scl = np.full((10, 10), 5, dtype=np.uint8)
        scl[:2, :] = 9  # 80% czystych
        ndvi = np.full((10, 10), 0.4, dtype=np.float32)
        ndre = np.full((10, 10), 0.2, dtype=np.float32)
        st = historia.statystyki(ndvi, ndre, maska, scl)
        self.assertEqual(st["czyste_pct"], 80.0)
        self.assertTrue(historia.prog_przyjecia(st))


class TestNMT(unittest.TestCase):
    def test_zero_to_brak_danych_nie_plaski_teren(self):
        with patch.object(teren, "_get", return_value="0"):
            odczyt = teren.odczyt(416000.0, 505700.0)
        self.assertEqual(odczyt["status"], "zero")
        self.assertIsNone(odczyt["h_m"])
        self.assertEqual(historia.status_terenu(100, 0, 0), "BRAK DANYCH")
        self.assertNotEqual(historia.status_terenu(100, 0, 0), "OK")

    def test_prog_20_proc(self):
        self.assertEqual(historia.status_terenu(100, 80, 0), "OK")
        self.assertEqual(historia.status_terenu(100, 79, 0), "BRAK DANYCH")
        self.assertEqual(historia.status_terenu(100, 0, 100), "BRAK_USLUGI")

    def test_pusty_odczyt_to_brak_danych(self):
        with patch.object(teren, "_get", return_value=""):
            odczyt = teren.odczyt(416000.0, 505700.0)
        self.assertEqual(odczyt["status"], "pusto")
        self.assertIsNone(odczyt["h_m"])

    def test_rownolegly_odczyt_listy_punktow(self):
        with patch.object(teren, "odczyt",
                          side_effect=lambda x, y, proby=3: {"h_m": 171.5, "status": "ok"}):
            wynik = teren.wysokosci_punktow([(416000.0, 505700.0),
                                             (416012.0, 505712.0)], watki=2)
        self.assertEqual(len(wynik), 2)
        self.assertTrue(all(o["h_m"] == 171.5 for o in wynik))

    def test_nmt_siec_po_trzech_probach(self):
        """GUGiK niedostępny: 3 próby, status `blad`, a nie wysokość 0."""
        with patch.object(teren, "_get", side_effect=ConnectionError("brak sieci")):
            with patch.object(teren.time, "sleep", return_value=None):
                odczyt = teren.odczyt(416000.0, 505700.0, proby=3)
        self.assertEqual(odczyt["status"], "blad")
        self.assertIsNone(odczyt["h_m"])
        self.assertEqual(historia.status_terenu(100, 0, 100), "BRAK_USLUGI")

    def test_mapa_brak_danych_zamiast_koloru(self):
        # Bez TemporaryDirectory: pod sandboxem harnessu katalog tymczasowy
        # dostaje ACL, w którym zapis jest odmawiany (S155a, 02.11.2026).
        # Piszemy do istniejącego demo/img i sprzątamy w `finally`.
        from pathlib import Path
        from PIL import Image
        arr = np.full((4, 4), np.nan, dtype=np.float32)
        maska = np.ones((4, 4), dtype=bool)
        p = Path(__file__).resolve().parent / "demo" / "img" / "_test-teren-brak-danych.png"
        try:
            mapy.rysuj_teren(p, arr, maska, (0, 40, 0, 40), "test — BRAK DANYCH",
                             {}, "BRAK DANYCH")
            with Image.open(p) as im:
                opis = im.info.get("Description", "")
        finally:
            p.unlink(missing_ok=True)
        self.assertEqual(opis, "status=BRAK DANYCH")


class TestAwariaZaleznosci(unittest.TestCase):
    def test_trzy_proby_i_nazwany_brak(self):
        licznik = {"n": 0}

        def padnij():
            licznik["n"] += 1
            raise ConnectionError("brak sieci")

        with self.assertRaises(RuntimeError) as ctx:
            historia.z_proba(padnij, "STAC test", proby=3)
        self.assertEqual(licznik["n"], 3)
        self.assertIn("po 3 próbach", str(ctx.exception))


def _scena(data, pct, ndvi=0.5):
    st = {"czyste_pct": pct, "piksele_pola": 100, "piksele_czyste": pct,
          "piksele_uzyte": pct, "ndvi_srednia": ndvi, "ndre_srednia": 0.3}
    return {"data": data, "scena": f"S2_{data}", "pct": {"90/8": pct},
            "przyjete": {"90/8": True}, "stats": {"90/8": st},
            "ndvi": np.full((2, 2), ndvi, dtype=np.float32),
            "scl": np.full((2, 2), 4, dtype=np.uint8)}


class TestTerminy(unittest.TestCase):
    def test_najczystsza_i_remis_wczesniejsza(self):
        sceny = [
            _scena("2026-04-05", 90.0), _scena("2026-04-20", 90.0),
            _scena("2026-04-10", 80.0),
            _scena("2026-05-15", 70.0), _scena("2026-06-01", 95.0),
            _scena("2026-07-10", 60.0), _scena("2026-10-20", 99.0),
        ]
        wybor = historia.wybierz_dla_dzialki(sceny, "90/8")
        self.assertEqual([t["okres"] for t in wybor],
                         ["April", "May/June", "July", "October"])
        self.assertEqual(wybor[0]["data"], "2026-04-05", "remis → wcześniejsza data")
        self.assertEqual(wybor[1]["data"], "2026-06-01", "maj/czerwiec to jeden okres")
        self.assertEqual(wybor[3]["data"], "2026-10-20")

    def test_brak_okresu_jest_nazwany(self):
        wybor = historia.wybierz_dla_dzialki([_scena("2026-04-05", 90.0)], "90/8")
        self.assertIsNone(wybor[1]["data"])
        self.assertIn("brak przyjętej sceny", wybor[1]["brak"])


class TestKrzywa(unittest.TestCase):
    def test_luka_45_dni(self):
        p = [(date(2026, 6, 1), 0.5), (date(2026, 7, 20), 0.6)]  # 49 dni
        self.assertEqual(len(historia.odcinki_krzywej(p)), 2)

    def test_krotka_luka_ciagla(self):
        p = [(date(2026, 6, 1), 0.5), (date(2026, 7, 10), 0.6)]  # 39 dni
        self.assertEqual(len(historia.odcinki_krzywej(p)), 1)

    def test_miesiac_bez_sceny_przerywa(self):
        p = [(date(2026, 3, 25), 0.5), (date(2026, 5, 2), 0.6)]  # brak kwietnia
        self.assertEqual(len(historia.odcinki_krzywej(p)), 2)


class TestSlabeMiejsca(unittest.TestCase):
    def _dane(self, n=120):
        shape = (10, 12) if n == 120 else (5, 10)
        maska = np.ones(shape, dtype=bool)
        baza = np.full(n, 0.75, dtype=np.float32)
        baza[:max(1, n // 4)] = 0.20
        arrs = [baza.reshape(shape) + i * 0.001 for i in range(4)]
        h = np.linspace(170.0, 173.0, n).reshape(shape).astype(np.float32)
        terminy = [{"data": f"2026-0{i + 4}-15", "okres": str(i), "ndvi": a}
                   for i, a in enumerate(arrs)]
        return terminy, maska, h

    def test_wraca_i_stale_ziarno(self):
        terminy, maska, h = self._dane()
        a = historia.analiza_slabe(terminy, "x", maska, h)
        b = historia.analiza_slabe(terminy, "x", maska, h)
        self.assertEqual(a["n_wspolnych"], 120)
        self.assertEqual(a["werdykt"], "WRACA")
        self.assertEqual(a["przypadek"]["p_value"], b["przypadek"]["p_value"])
        self.assertEqual(a["przypadek"]["permutacje"], 1000)
        self.assertEqual(len(a["korelacja_wysokosc_ndvi"]), 4)

    def test_za_malo_pikseli(self):
        terminy, maska, h = self._dane(n=50)
        a = historia.analiza_slabe(terminy, "x", maska, h)
        self.assertEqual(a["werdykt"], "ZA MAŁO PIKSELI")


class TestProgiIZrodla(unittest.TestCase):
    def test_progi_zapisane(self):
        self.assertEqual(mapy.PROGI_NDVI, [0.20, 0.35, 0.50, 0.70])
        self.assertEqual(mapy.KLASY_NDVI,
                         ["very low", "low", "medium", "good", "very good"])
        self.assertEqual(historia.PROG_CZYSTE_PCT, 80.0)
        self.assertEqual(historia.MIN_PIKSELI_WERDYKT, 100)

    def test_piec_dzialek_bez_sieci(self):
        dz = historia.wczytaj_dzialki()
        self.assertEqual(set(historia.DZIALKI), set(dz))

    def test_ndvi_ndre(self):
        nir = np.array([0.5, 0.4], dtype=np.float32)
        red = np.array([0.1, 0.2], dtype=np.float32)
        red_edge = np.array([0.2, 0.1], dtype=np.float32)
        ndvi = sentinel.ndvi(nir, red)
        ndre = sentinel.ndre(nir, red_edge)
        self.assertAlmostEqual(float(ndvi[0]), 0.6666667, places=5)
        self.assertAlmostEqual(float(ndre[0]), 0.4285714, places=5)
        self.assertTrue(np.isnan(sentinel.ndvi(np.array([0.0]), np.array([0.0]))[0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
