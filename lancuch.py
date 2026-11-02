"""Szkielet łańcucha „Pole z góry" — od kafla Sentinel-2 do zdania dla rolnika.

Cztery kroki, każdy z jasnym wejściem i wyjściem:

    1. wczytaj_kafel()   kafel Sentinel-2 (B04, B05, B08, SCL)   -> Kafel
    2. maski_pol()       segmentacja SAM 3.1                     -> lista[Pole]
    3. policz_ndre()     NDRE w granicach pola                   -> Wskaznik
    4. opis_rolnika()    zdanie po polsku                        -> Opis

Zasady, które ten szkielet celowo trzyma:

* **Każdy krok ma atrapę** (klasy `Atrapa*`). Testy i demo działają bez sieci,
  bez GPU i bez płatnego API.
* **Chmury to wynik, nie wyjątek.** Gdy nad polem nie ma dość czystych pikseli,
  łańcuch zwraca status `CHMURY` i komunikat — nigdy liczbę udającą pomiar.
* **Awaria modelu opisu nie zabija pomiaru.** Status `BEZ_OPISU` zostawia
  policzone NDRE; brak zdania to brak zdania, a nie brak wyniku.
* **Pusty obszar to jawny błąd** (`PustyObszar`) — nie „puste pole" z zerem.
* Prawdziwych modeli tu nie ma: `ZrodloSentinel2`, `Sam31` i `ModelMeta`
  rzucają `NieWdrozone`. To jest szkielet, nie produkt.

Pochodzenie kodu NDVI (wzorzec, nie kopia): `ndvi_raport.py:212-254`
(`policz_ndvi`, maska SCL, `_dopasuj`, pokrycie pola). Ten plik liczy NDRE,
więc potrzebuje pasma B05 (red edge 1, 705 nm), którego tamten kod nie pobiera.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

# ────────────────────────────────────────────────────────────────────────────
# 0. Stałe i typy wyników
# ────────────────────────────────────────────────────────────────────────────

PROG_CHMUR = 0.30          # maks. udział chmur nad polem, żeby uznać pomiar
PROG_NDRE_SLABY = 0.35     # roboczy próg „słabo"; do kalibracji z rolnikiem

# SCL (Scene Classification Layer) Sentinel-2: 4 roślinność, 5 gleba, 6 woda, 7 niesklasyfikowane.
# Chmury (8, 9, 10), cień (3) i śnieg (11) odsiewamy — tak samo jak w ndvi_raport.py:221.
SCL_CZYSTE = frozenset({4, 5, 6, 7})

STATUS_OK = "OK"
STATUS_CHMURY = "CHMURY"
STATUS_BEZ_OPISU = "BEZ_OPISU"
STATUS_PUSTY = "PUSTY_OBSZAR"


class BladLancucha(Exception):
    """Błąd, który wolno pokazać użytkownikowi (nie stack trace)."""


class PustyObszar(BladLancucha):
    """W kaflu nie ma ani jednego pola albo maska pola jest pusta."""


class BrakPomiaru(BladLancucha):
    """Pola nie da się zmierzyć (chmury, brak ważnych pikseli)."""


class AwariaModelu(BladLancucha):
    """Model opisu nie odpowiedział. Łańcuch zostaje przy liczbach."""


class NieWdrozone(BladLancucha):
    """Adapter prawdziwego modelu/źródła w tym szkielecie nie istnieje."""


@dataclass(frozen=True)
class Kafel:
    """Wycinek sceny Sentinel-2 nad jednym polem.

    `pasma` to płaskie listy odbiciowości (0..1), wiersz po wierszu. `scl` to
    klasy sceny dla tych samych pikseli. Wartości `nan` oznaczają brak danych.
    """

    ident: str
    data: str                        # ISO, np. "2026-10-27"
    szer: int
    wys: int
    pasma: dict[str, tuple[float, ...]]
    scl: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.szer <= 0 or self.wys <= 0:
            raise ValueError("kafel musi mieć dodatnie wymiary")
        ile = self.szer * self.wys
        if len(self.scl) != ile:
            raise ValueError(f"SCL ma {len(self.scl)} pikseli, oczekiwano {ile}")
        for nazwa in ("B04", "B05", "B08"):
            if nazwa not in self.pasma:
                raise ValueError(f"brak pasma {nazwa} (NDRE wymaga B05 i B08)")
            if len(self.pasma[nazwa]) != ile:
                raise ValueError(f"pasmo {nazwa} ma {len(self.pasma[nazwa])} pikseli, oczekiwano {ile}")


@dataclass(frozen=True)
class Pole:
    """Jedno pole wycięte przez SAM. `maska` jest w układzie kafla."""

    ident: str
    maska: tuple[bool, ...]
    powierzchnia_ha: float

    def __post_init__(self) -> None:
        if self.powierzchnia_ha <= 0:
            raise ValueError("pole musi mieć dodatnią powierzchnię")


@dataclass(frozen=True)
class Wskaznik:
    """Policzone NDRE. Każda liczba ma jednostkę: NDRE jest bezwymiarowe."""

    pole_id: str
    ndre_srednia: float
    ndre_min: float
    ndre_max: float
    piksele_uzyte: int
    pokrycie_pola: float            # użyte piksele / piksele pola, 0..1
    udzial_czystych: float          # czyste piksele / piksele pola, 0..1


@dataclass(frozen=True)
class Opis:
    """Zdanie dla rolnika. `model` mówi, co je napisało — także „atrapa"."""

    tekst: str
    model: str


@dataclass(frozen=True)
class Wynik:
    """Wynik całego łańcucha. Pusta lista pól = błąd, nie ten obiekt."""

    status: str
    kafel_id: str
    pole: Pole | None
    wskaznik: Wskaznik | None
    opis: Opis | None
    komunikat: str

    def do_dict(self) -> dict:
        """Do JSON-a: maska pola jako liczba pikseli, nie 64 wartości true/false."""
        dane = asdict(self)
        if dane["pole"] is not None:
            maska = dane["pole"].pop("maska")
            dane["pole"]["piksele"] = sum(1 for w in maska if w)
        return dane


# ────────────────────────────────────────────────────────────────────────────
# 1. Źródło kafla — Sentinel-2
# ────────────────────────────────────────────────────────────────────────────

class ZrodloKafla(Protocol):
    def pobierz(self, ident: str) -> Kafel: ...


class ZrodloSentinel2:
    """Prawdziwe źródło: STAC Copernicus + rasterio. W tym szkielecie NIE wdrożone.

    Co musi zrobić wdrożenie (na wzór `ndvi_raport.py:172-196`):
    * znaleźć scenę po dacie i chmurach (`znajdz_sceny`),
    * wczytać wycinek B04, B05 (red edge 1), B08 i SCL,
    * wyrównać rozdzielczości (`_dopasuj`: SCL 20 m vs pasma 10 m).
    """

    def pobierz(self, ident: str) -> Kafel:
        raise NieWdrozone(
            "źródło Sentinel-2 nie jest podłączone; użyj AtrapaKafla albo "
            "wdróż STAC/rasterio według ndvi_raport.py:172-196"
        )


def wczytaj_kafel(zrodlo: ZrodloKafla, ident: str) -> Kafel:
    """Krok 1. Wejście: identyfikator kafla. Wyjście: Kafel z B04/B05/B08/SCL."""
    kafel = zrodlo.pobierz(ident)
    if not isinstance(kafel, Kafel):
        raise BladLancucha(f"źródło zwróciło {type(kafel).__name__}, oczekiwano Kafel")
    return kafel


# ────────────────────────────────────────────────────────────────────────────
# 2. Segmentacja pól — SAM 3.1
# ────────────────────────────────────────────────────────────────────────────

class SegmentatorPol(Protocol):
    def segmentuj(self, kafel: Kafel) -> Sequence[Pole]: ...


class Sam31:
    """Prawdziwy SAM 3.1 (wagi ~3,5 GB, licencja SAM, bramkowane na HF).

    Prompt tekstowy w rodzaju „agricultural field" zwraca maski. Wdrożenie musi
    odsiać maski mniejsze niż kilka pikseli i połączyć nakładające się.
    """

    def segmentuj(self, kafel: Kafel) -> Sequence[Pole]:
        raise NieWdrozone(
            "SAM 3.1 nie jest podłączony; użyj AtrapaSam albo wdróż "
            "facebookresearch/sam3 (wagi gated, licencja SAM)"
        )


def maski_pol(kafel: Kafel, segmentator: SegmentatorPol) -> list[Pole]:
    """Krok 2. Wejście: Kafel. Wyjście: niepusta lista pól.

    Pusty wynik jest błędem `PustyObszar`, a nie pustą listą — inaczej krok 3
    policzyłby NDRE z niczego.
    """
    pola = list(segmentator.segmentuj(kafel))
    if not pola:
        raise PustyObszar(
            f"kafel {kafel.ident}: SAM nie znalazł żadnego pola (pusty obszar)"
        )
    ile = kafel.szer * kafel.wys
    for pole in pola:
        if not isinstance(pole, Pole):
            raise BladLancucha(f"segmentator zwrócił {type(pole).__name__}, oczekiwano Pole")
        if len(pole.maska) != ile:
            raise BladLancucha(
                f"pole {pole.ident}: maska ma {len(pole.maska)} pikseli, kafel {ile}"
            )
        if not any(pole.maska):
            raise PustyObszar(f"pole {pole.ident}: maska jest pusta")
    return pola


# ────────────────────────────────────────────────────────────────────────────
# 3. Wskaźnik NDRE
# ────────────────────────────────────────────────────────────────────────────

def _ndre_piksel(nir: float, red_edge: float) -> float:
    """NDRE = (B08 - B05) / (B08 + B05). Zwraca nan, gdy mianownik się nie nadaje."""
    if not (math.isfinite(nir) and math.isfinite(red_edge)):
        return math.nan
    mianownik = nir + red_edge
    if mianownik <= 0:
        return math.nan
    return (nir - red_edge) / mianownik


def policz_ndre(kafel: Kafel, pole: Pole, prog_chmur: float = PROG_CHMUR) -> Wskaznik:
    """Krok 3. Wejście: Kafel + Pole. Wyjście: Wskaznik.

    Rzuca `BrakPomiaru`, gdy nad polem jest więcej chmur niż `prog_chmur` albo
    gdy nie zostaje ani jeden ważny piksel. Liczb nie zaokrąglamy po cichu.
    """
    if len(pole.maska) != kafel.szer * kafel.wys:
        raise BladLancucha(f"pole {pole.ident} nie pasuje do kafla {kafel.ident}")

    nir = kafel.pasma["B08"]
    red_edge = kafel.pasma["B05"]
    w_polu = 0
    czyste = 0
    wartosci: list[float] = []

    for i, w_mask in enumerate(pole.maska):
        if not w_mask:
            continue
        w_polu += 1
        if kafel.scl[i] not in SCL_CZYSTE:
            continue
        czyste += 1
        wartosc = _ndre_piksel(nir[i], red_edge[i])
        if math.isfinite(wartosc):
            wartosci.append(wartosc)

    if w_polu == 0:
        raise PustyObszar(f"pole {pole.ident}: maska nie obejmuje żadnego piksela")

    udzial_czystych = czyste / w_polu
    if udzial_czystych < (1.0 - prog_chmur):
        raise BrakPomiaru(
            f"nad polem {pole.ident} jest {round((1.0 - udzial_czystych) * 100)}% chmur "
            f"(próg {round(prog_chmur * 100)}%) — pomiaru nie ma, jest komunikat"
        )
    if not wartosci:
        raise BrakPomiaru(
            f"pole {pole.ident}: brak ważnych pikseli NDRE (same nan albo zerowe odbicie)"
        )

    return Wskaznik(
        pole_id=pole.ident,
        ndre_srednia=sum(wartosci) / len(wartosci),
        ndre_min=min(wartosci),
        ndre_max=max(wartosci),
        piksele_uzyte=len(wartosci),
        pokrycie_pola=len(wartosci) / w_polu,
        udzial_czystych=udzial_czystych,
    )


# ────────────────────────────────────────────────────────────────────────────
# 4. Opis dla rolnika — model Meta
# ────────────────────────────────────────────────────────────────────────────

class ModelOpisu(Protocol):
    def opisz(self, wskaznik: Wskaznik, pole: Pole) -> Opis: ...


class ModelMeta:
    """Muse Spark 1.3 / Muse Glimmer 30B przez Meta Model API albo lokalnie.

    Wdrożenie ma dostać gotowe liczby i napisać 2–4 zdania po polsku. Nie wolno
    mu przeliczać NDRE ani dopisywać zaleceń nawozowych — to nie jest doradztwo
    agronomiczne (CLAUDE.md: nie udajemy uprawnień ŚOR).
    """

    def opisz(self, wskaznik: Wskaznik, pole: Pole) -> Opis:
        raise NieWdrozone(
            "model opisu nie jest podłączony; użyj AtrapaOpis albo podłącz "
            "Meta Model API (Muse Spark) / lokalny Muse Glimmer"
        )


def opis_rolnika(wskaznik: Wskaznik, pole: Pole, model: ModelOpisu) -> Opis | None:
    """Krok 4. Wejście: Wskaznik + Pole. Wyjście: Opis albo None.

    `AwariaModelu` i `TimeoutError` znaczą „brak zdania", nie „brak pomiaru" —
    dlatego zwracamy `None`, a nie przerywamy łańcucha. Inne wyjątki lecą dalej:
    to błąd programu, nie awaria modelu.
    """
    try:
        opis = model.opisz(wskaznik, pole)
    except (AwariaModelu, TimeoutError):
        return None
    if not isinstance(opis, Opis):
        raise BladLancucha(f"model opisu zwrócił {type(opis).__name__}, oczekiwano Opis")
    if not opis.tekst.strip():
        raise BladLancucha("model opisu zwrócił pusty tekst")
    return opis


# ────────────────────────────────────────────────────────────────────────────
# 5. Cały łańcuch
# ────────────────────────────────────────────────────────────────────────────

def uruchom_lancuch(
    ident: str,
    zrodlo: ZrodloKafla,
    segmentator: SegmentatorPol,
    model_opisu: ModelOpisu,
    prog_chmur: float = PROG_CHMUR,
) -> Wynik:
    """Cztery kroki po kolei. Domyślnie bierze pierwsze pole z segmentacji.

    Rozszerzenie na wiele pól: wołaj `policz_ndre`/`opis_rolnika` dla każdego
    pola i zwróć listę `Wynik` — ten szkielet świadomie trzyma jeden wynik.
    """
    kafel = wczytaj_kafel(zrodlo, ident)
    pola = maski_pol(kafel, segmentator)
    pole = pola[0]

    try:
        wskaznik = policz_ndre(kafel, pole, prog_chmur=prog_chmur)
    except BrakPomiaru as blad:
        return Wynik(
            status=STATUS_CHMURY,
            kafel_id=kafel.ident,
            pole=pole,
            wskaznik=None,
            opis=None,
            komunikat=str(blad),
        )

    opis = opis_rolnika(wskaznik, pole, model_opisu)
    if opis is None:
        return Wynik(
            status=STATUS_BEZ_OPISU,
            kafel_id=kafel.ident,
            pole=pole,
            wskaznik=wskaznik,
            opis=None,
            komunikat=(
                "model opisu nie odpowiedział — zostaje sam wynik liczbowy "
                f"(NDRE {wskaznik.ndre_srednia:.3f}); brak zdania to brak zdania"
            ),
        )

    return Wynik(
        status=STATUS_OK,
        kafel_id=kafel.ident,
        pole=pole,
        wskaznik=wskaznik,
        opis=opis,
        komunikat="łańcuch przeszedł cztery kroki",
    )


# ────────────────────────────────────────────────────────────────────────────
# 6. Atrapy — każdy krok ma swoją
# ────────────────────────────────────────────────────────────────────────────

class AtrapaKafla:
    """Krok 1 bez sieci: syntetyczny kafel o znanym NDRE.

    Domyślnie 8×8 pikseli, całe pole „zielone" o NDRE 0,42, bez chmur.
    `chmury=1.0` oznacza całe pole w chmurach (SCL=9).
    """

    def __init__(
        self,
        ndre: float = 0.42,
        chmury: float = 0.0,
        szer: int = 8,
        wys: int = 8,
        data: str = "2026-10-27",
        ziarno: int = 145,
    ) -> None:
        if not -1.0 < ndre < 1.0:
            raise ValueError("NDRE atrapy musi być w (-1, 1)")
        if not 0.0 <= chmury <= 1.0:
            raise ValueError("udział chmur musi być w [0, 1]")
        self.ndre = ndre
        self.chmury = chmury
        self.szer = szer
        self.wys = wys
        self.data = data
        self.ziarno = ziarno

    def pobierz(self, ident: str) -> Kafel:
        rng = random.Random(self.ziarno)
        ile = self.szer * self.wys
        # B08 = 0,40; B05 wyliczone tak, żeby (B08-B05)/(B08+B05) = ndre.
        nir = 0.40
        red_edge = nir * (1.0 - self.ndre) / (1.0 + self.ndre)
        pasma = {
            "B04": tuple(0.05 + rng.random() * 0.01 for _ in range(ile)),
            "B05": tuple(red_edge + rng.random() * 0.001 for _ in range(ile)),
            "B08": tuple(nir + rng.random() * 0.001 for _ in range(ile)),
        }
        w_chmurach = round(ile * self.chmury)
        scl = tuple(9 if i < w_chmurach else 4 for i in range(ile))
        return Kafel(ident=ident, data=self.data, szer=self.szer, wys=self.wys,
                     pasma=pasma, scl=scl)


class AtrapaSam:
    """Krok 2 bez modelu: wycina środkowy prostokąt kafla jako jedno pole.

    `puste=True` zwraca pustą listę — test sprawdza, że łańcuch mówi
    `PustyObszar`, a nie liczy NDRE z niczego.
    """

    def __init__(self, margines: int = 2, puste: bool = False, ident: str = "P-1") -> None:
        self.margines = margines
        self.puste = puste
        self.ident = ident

    def segmentuj(self, kafel: Kafel) -> Sequence[Pole]:
        if self.puste:
            return []
        maska = []
        for y in range(kafel.wys):
            for x in range(kafel.szer):
                w_srodku = (
                    self.margines <= x < kafel.szer - self.margines
                    and self.margines <= y < kafel.wys - self.margines
                )
                maska.append(w_srodku)
        if not any(maska):
            raise PustyObszar("atrapa SAM: margines zjada cały kafel")
        # 1 piksel Sentinel-2 = 10 m × 10 m = 0,01 ha.
        powierzchnia = sum(maska) * 0.01
        return [Pole(ident=self.ident, maska=tuple(maska), powierzchnia_ha=powierzchnia)]


class AtrapaOpis:
    """Krok 4 bez modelu: zdanie z liczb, które dostał. Nie przelicza NDRE."""

    def __init__(self, model: str = "atrapa-opis") -> None:
        self.model = model

    def opisz(self, wskaznik: Wskaznik, pole: Pole) -> Opis:
        stan = "powyżej" if wskaznik.ndre_srednia >= PROG_NDRE_SLABY else "poniżej"
        tekst = (
            f"Pole {pole.ident}: NDRE średnio {wskaznik.ndre_srednia:.2f} "
            f"(od {wskaznik.ndre_min:.2f} do {wskaznik.ndre_max:.2f}) — "
            f"{stan} progu roboczego {PROG_NDRE_SLABY:.2f}. "
            f"Zmierzono {wskaznik.piksele_uzyte} pikseli. "
            "To szkic, nie zalecenie nawozowe."
        )
        return Opis(tekst=tekst, model=self.model)


class AtrapaOpisAwaria:
    """Krok 4 z awarią: model nie odpowiada."""

    def opisz(self, wskaznik: Wskaznik, pole: Pole) -> Opis:
        raise AwariaModelu("atrapa: model opisu nie odpowiada (timeout)")


# ────────────────────────────────────────────────────────────────────────────
# 7. Demo z linii poleceń (cztery warianty = cztery przypadki testowe)
# ────────────────────────────────────────────────────────────────────────────

def _demo(wariant: str) -> int:
    if wariant == "ok":
        zrodlo, sam, model = AtrapaKafla(), AtrapaSam(), AtrapaOpis()
    elif wariant == "chmury":
        zrodlo, sam, model = AtrapaKafla(chmury=1.0), AtrapaSam(), AtrapaOpis()
    elif wariant == "awaria-opisu":
        zrodlo, sam, model = AtrapaKafla(), AtrapaSam(), AtrapaOpisAwaria()
    elif wariant == "pusty":
        zrodlo, sam, model = AtrapaKafla(), AtrapaSam(puste=True), AtrapaOpis()
    else:
        raise SystemExit(f"nieznany wariant: {wariant}")

    try:
        wynik = uruchom_lancuch("DEMO", zrodlo, sam, model)
    except PustyObszar as blad:
        print(json.dumps({"status": STATUS_PUSTY, "komunikat": str(blad)},
                         ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(wynik.do_dict(), ensure_ascii=False, indent=2))
    return 0 if wynik.status == STATUS_OK else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Szkielet łańcucha Pole z góry (atrapy)")
    parser.add_argument("--atrapa", choices=["ok", "chmury", "awaria-opisu", "pusty"],
                        default="ok", help="który wariant demo uruchomić")
    args = parser.parse_args()
    return _demo(args.atrapa)


if __name__ == "__main__":
    raise SystemExit(main())
