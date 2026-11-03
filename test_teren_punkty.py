#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S155b2 — test punktów A/B/C na mapie terenu.

Pilnuje dwóch rzeczy, które razem dały „punkt C poza kolorowym obszarem”:
  * wybór A/B/C wyłącznie spośród pikseli w masce działki,
  * najwyższy kolor skali nie jest biały (biały piksel zlewał się z tłem).

Uruchomienie: python test_teren_punkty.py
"""
from __future__ import annotations

import unittest

import numpy as np

import historia
import mapy


def punkt(x, y, h, w, k):
    return {"x": x, "y": y, "h_m": h, "w": w, "k": k}


class TestWyborPunktow(unittest.TestCase):
    def test_a_b_c_tylko_z_maski(self):
        maska = np.ones((4, 4), dtype=bool)
        maska[0, 0] = False          # piksel spoza działki, a ma najwyższą wartość
        wartosci = [
            punkt(5, 35, 170.0, 0, 1),
            punkt(15, 25, 172.0, 1, 1),
            punkt(25, 15, 173.0, 2, 2),
            punkt(0, 40, 999.0, 0, 0),   # poza maską — nie wolno go wybrać
        ]
        wybrane = historia.wybierz_punkty_abc(wartosci, maska, (20, 20))
        self.assertEqual(set(wybrane), {"A", "B", "C"})
        for klucz, p in wybrane.items():
            self.assertTrue(maska[p["w"], p["k"]],
                            "%s wybrany spoza maski: %s" % (klucz, p))
        self.assertEqual(wybrane["C"]["h_m"], 173.0,
                         "C nie może być pikselem spoza maski, nawet najwyższym")
        self.assertEqual(wybrane["A"]["h_m"], 170.0)

    def test_brak_pikseli_w_masce(self):
        maska = np.zeros((2, 2), dtype=bool)
        self.assertEqual(historia.wybierz_punkty_abc(
            [punkt(1, 1, 1.0, 0, 0)], maska, (0, 0)), {})


class TestPunktPozaRysowanym(unittest.TestCase):
    def setUp(self):
        self.arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        self.maska = np.ones((2, 2), dtype=bool)
        self.maska[1, 1] = False     # prawy dolny piksel nie jest rysowany
        self.extent = (0.0, 20.0, 0.0, 20.0)

    def test_poprawny_punkt_przechodzi(self):
        # x=5,y=15 -> wiersz 0, kolumna 0
        self.assertTrue(mapy.sprawdz_punkty_na_mapie(
            {"A": {"x": 5.0, "y": 15.0}}, self.arr, self.maska, self.extent))

    def test_punkt_poza_maska_czerwieni(self):
        # x=15,y=5 -> wiersz 1, kolumna 1: maska False
        with self.assertRaises(ValueError) as ctx:
            mapy.sprawdz_punkty_na_mapie(
                {"C": {"x": 15.0, "y": 5.0}}, self.arr, self.maska, self.extent)
        self.assertIn("poza maską", str(ctx.exception))

    def test_punkt_poza_kadrem_czerwieni(self):
        with self.assertRaises(ValueError) as ctx:
            mapy.sprawdz_punkty_na_mapie(
                {"C": {"x": 99.0, "y": 5.0}}, self.arr, self.maska, self.extent)
        self.assertIn("poza kadrem", str(ctx.exception))


class TestKolorSkali(unittest.TestCase):
    def test_najwyzszy_piksel_nie_jest_bialy(self):
        r, g, b = mapy.kolor_terenu(1.0)
        odleglosc = (255 - r) + (255 - g) + (255 - b)
        self.assertGreater(odleglosc, 80,
                           "górny kolor skali jest zbyt blisko bieli: %s" % ((r, g, b),))
        self.assertLess(odleglosc, 600, "górny kolor nie może być czarny")

    def test_dolny_piksel_nie_jest_bialy(self):
        r, g, b = mapy.kolor_terenu(0.0)
        self.assertGreater((255 - r) + (255 - g) + (255 - b), 80)


if __name__ == "__main__":
    unittest.main(verbosity=2)
