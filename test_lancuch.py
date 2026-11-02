"""Test szkieletu łańcucha „Pole z góry" — cztery przypadki ze zlecenia S145j.

Uruchomienie:

    python hackathon/pole-z-gory/test_lancuch.py

Kod 0 = 4/4, kod 1 = któryś przypadek czerwony. Zero sieci, zero GPU,
zero płatnego API: wszystkie cztery kroki mają atrapy.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

# Windows: domyślna konsola cp1250 nie umie wydrukować „≈” ani „→”.
# Bez tego test kończy się wyjątkiem kodowania, mimo że sprawdzenia są zielone.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Test ma działać także z katalogu repo, nie tylko z hackathon/pole-z-gory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lancuch import (  # noqa: E402 — ścieżka ustawiona wyżej, celowo
    STATUS_BEZ_OPISU,
    STATUS_CHMURY,
    STATUS_OK,
    AtrapaKafla,
    AtrapaOpis,
    AtrapaOpisAwaria,
    AtrapaSam,
    PustyObszar,
    uruchom_lancuch,
)

WYNIKI: list[tuple[str, bool, str]] = []


def sprawdz(nazwa: str, warunek: bool, opis: str) -> None:
    WYNIKI.append((nazwa, bool(warunek), opis))


def test_1_poprawny_kafel() -> None:
    """Poprawny kafel: liczby + opis, status OK."""
    wynik = uruchom_lancuch("T-1", AtrapaKafla(ndre=0.42), AtrapaSam(), AtrapaOpis())

    sprawdz("1. poprawny kafel — status", wynik.status == STATUS_OK, wynik.status)
    sprawdz("1. poprawny kafel — jest wskaźnik", wynik.wskaznik is not None, "wskaznik")
    if wynik.wskaznik is not None:
        blisko = math.isclose(wynik.wskaznik.ndre_srednia, 0.42, abs_tol=0.01)
        sprawdz("1. poprawny kafel — NDRE ≈ 0,42", blisko,
                f"{wynik.wskaznik.ndre_srednia:.4f}")
        sprawdz("1. poprawny kafel — min ≤ średnia ≤ max",
                wynik.wskaznik.ndre_min <= wynik.wskaznik.ndre_srednia <= wynik.wskaznik.ndre_max,
                "zakres")
        sprawdz("1. poprawny kafel — pokrycie > 0",
                wynik.wskaznik.pokrycie_pola > 0, f"{wynik.wskaznik.pokrycie_pola:.2f}")
    sprawdz("1. poprawny kafel — jest opis",
            wynik.opis is not None and "NDRE" in wynik.opis.tekst,
            wynik.opis.tekst[:60] if wynik.opis else "brak")


def test_2_chmury() -> None:
    """Kafel w chmurach: komunikat zamiast liczb, bez opisu."""
    wynik = uruchom_lancuch("T-2", AtrapaKafla(chmury=1.0), AtrapaSam(), AtrapaOpis())

    sprawdz("2. chmury — status CHMURY", wynik.status == STATUS_CHMURY, wynik.status)
    sprawdz("2. chmury — brak liczby", wynik.wskaznik is None, "wskaznik")
    sprawdz("2. chmury — brak opisu", wynik.opis is None, "opis")
    sprawdz("2. chmury — komunikat mówi o chmurach",
            "chmur" in wynik.komunikat.lower(), wynik.komunikat)
    sprawdz("2. chmury — komunikat nie udaje pomiaru",
            "NDRE" not in wynik.komunikat, wynik.komunikat)


def test_3_awaria_opisu() -> None:
    """Awaria modelu opisu: zostaje wynik liczbowy, bez zdania."""
    wynik = uruchom_lancuch("T-3", AtrapaKafla(ndre=0.31), AtrapaSam(), AtrapaOpisAwaria())

    sprawdz("3. awaria opisu — status BEZ_OPISU",
            wynik.status == STATUS_BEZ_OPISU, wynik.status)
    sprawdz("3. awaria opisu — wynik liczbowy zostaje",
            wynik.wskaznik is not None, "wskaznik")
    if wynik.wskaznik is not None:
        sprawdz("3. awaria opisu — NDRE jest skończone",
                math.isfinite(wynik.wskaznik.ndre_srednia),
                f"{wynik.wskaznik.ndre_srednia:.4f}")
    sprawdz("3. awaria opisu — brak zdania", wynik.opis is None, "opis")
    sprawdz("3. awaria opisu — komunikat nazywa przyczynę",
            "opis" in wynik.komunikat.lower(), wynik.komunikat)


def test_4_pusty_obszar() -> None:
    """Pusty obszar: jawny błąd, nie zero i nie pusty wynik."""
    try:
        uruchom_lancuch("T-4", AtrapaKafla(), AtrapaSam(puste=True), AtrapaOpis())
    except PustyObszar as blad:
        sprawdz("4. pusty obszar — PustyObszar", True, "wyjątek")
        sprawdz("4. pusty obszar — komunikat jasny",
                "pusty" in str(blad).lower(), str(blad))
    except Exception as blad:  # noqa: BLE001 — chcemy nazwać każdy inny wyjątek
        sprawdz("4. pusty obszar — PustyObszar", False, f"{type(blad).__name__}: {blad}")
    else:
        sprawdz("4. pusty obszar — PustyObszar", False, "brak wyjątku")


def main() -> int:
    testy = [
        test_1_poprawny_kafel,
        test_2_chmury,
        test_3_awaria_opisu,
        test_4_pusty_obszar,
    ]
    for test in testy:
        try:
            test()
        except Exception as blad:  # noqa: BLE001 — raportujemy, nie ukrywamy
            sprawdz(f"{test.__name__} — wyjątek", False, f"{type(blad).__name__}: {blad}")

    for nazwa, ok, opis in WYNIKI:
        print(f"{'OK ' if ok else 'BŁĄD'} | {nazwa} | {opis}")

    przypadki = {nazwa.split(" — ")[0].split(".")[0] for nazwa, _, _ in WYNIKI}
    czerwone = {nazwa.split(" — ")[0].split(".")[0] for nazwa, ok, _ in WYNIKI if not ok}
    zdane = len(przypadki - czerwone)
    print(f"\nWYNIK: {zdane}/{len(przypadki)} przypadków zielonych "
          f"({len(WYNIKI)} sprawdzeń, {len(czerwone)} przypadków czerwonych)")
    return 0 if not czerwone and len(przypadki) == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
