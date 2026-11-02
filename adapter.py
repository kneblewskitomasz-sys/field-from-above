"""Adaptery prawdziwych danych do szkieletu `lancuch.py` (bez sieci — czyta cache).

Ten plik spina to, co zostało policzone z Sentinel-2 i ULDK, z czterema krokami
szkieletu. Dzięki temu `uruchom_lancuch()` przechodzi na prawdziwych działkach,
a nie tylko na atrapie. Opis może być atrapą albo zapisanym tekstem modelu —
to jest osobna warstwa, którą podmienia się jednym argumentem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lancuch import (  # noqa: E402
    Kafel, Opis, Pole, Wskaznik, BladLancucha,
)


class BrakDzialki(BladLancucha):
    """Działki nie ma w ULDK — nazwany brak, nie zero i nie pusta maska."""


@dataclass
class ZrodloZPlikow:
    """Kafel z gotowych tablic (npz): B04/B05/B08 w odbiciu, SCL w klasach."""
    npz: Path
    szer: int
    wys: int
    data: str
    scl_npz: Path | None = None

    def __post_init__(self) -> None:
        z = np.load(self.npz)
        self._b04 = z["b04"].astype(np.float32)
        self._b05 = z["b05"].astype(np.float32)
        self._b08 = z["b08"].astype(np.float32)
        self._scl = np.nan_to_num(z["scl"], nan=0.0).astype(int)
        if self.scl_npz is not None:
            self._scl = np.nan_to_num(np.load(self.scl_npz), nan=0.0).astype(int)

    def pobierz(self, ident: str) -> Kafel:
        pasma = {
            "B04": tuple(self._b04.ravel().tolist()),
            "B05": tuple(self._b05.ravel().tolist()),
            "B08": tuple(self._b08.ravel().tolist()),
        }
        return Kafel(ident=ident, data=self.data, szer=self.szer, wys=self.wys,
                     pasma=pasma, scl=tuple(self._scl.ravel().tolist()))


@dataclass
class SegmentatorULDK:
    """Maska działki z ULDK na siatce kafla — to granica urzędowa, nie SAM."""
    maski_npz: Path
    powierzchnie: dict[str, float]

    def __post_init__(self) -> None:
        self._z = np.load(self.maski_npz)

    def segmentuj(self, kafel: Kafel) -> list[Pole]:
        klucz = kafel.ident.replace("/", "_")
        if klucz not in self._z:
            raise BrakDzialki(f"działka {kafel.ident}: brak maski ULDK w {self.maski_npz}")
        m = self._z[klucz].astype(bool)
        return [Pole(ident=kafel.ident, maska=tuple(m.ravel().tolist()),
                     powierzchnia_ha=self.powierzchnie[kafel.ident])]


@dataclass
class ModelZapisany:
    """Opis już wygenerowany (lokalnie albo przez API) — do porównania liczb, nie do udawania modelu."""
    teksty: dict[str, str]
    model: str = "zapisany opis"

    def opisz(self, wskaznik: Wskaznik, pole: Pole) -> Opis:
        if pole.ident not in self.teksty:
            raise BladLancucha(f"brak zapisanego opisu dla {pole.ident}")
        return Opis(tekst=self.teksty[pole.ident], model=self.model)


def wczytaj_powierzchnie(sceny_json: Path) -> dict[str, float]:
    d = json.load(open(sceny_json, encoding="utf-8"))
    return {i: z["powierzchnia_ha"] for i, z in d["dzialki"].items() if z["status"] == "OK"}
