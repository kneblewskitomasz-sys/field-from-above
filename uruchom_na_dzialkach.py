"""S152c: prawdziwy łańcuch `uruchom_lancuch()` na pięciu działkach + test zachmurzenia.

Wejście: cache z `piaskownica/s152c` (Sentinel-2 2026-10-26, maski ULDK, SCL 2026-10-28).
Wyjście: `raport_lancuch.json` — status każdej działki i zgodność NDRE z osobnym
obliczeniem `sentinel.statystyki()`. Dwa niezależne przebiegi muszą dać tę samą liczbę;
jeśli nie dadzą, to jest błąd, nie „zaokrąglenie”.

Uruchomienie (z katalogu hackathon/pole-z-gory):
    python uruchom_na_dzialkach.py <katalog_cache> <sceny.json> <indeksy_26.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from adapter import BrakDzialki, SegmentatorULDK, ZrodloZPlikow, wczytaj_powierzchnie
from lancuch import (  # noqa: E402
    STATUS_CHMURY, STATUS_OK, AtrapaOpis, uruchom_lancuch,
)

DZIALKI = ["90/8", "90/12", "92/6", "92/10", "92/11"]
OBREB = "300310_5.0016"
BRAK = "90/1"


def main() -> int:
    cache = Path(sys.argv[1] if len(sys.argv) > 1 else "../../piaskownica/s152c/cache")
    sceny = Path(sys.argv[2] if len(sys.argv) > 2 else "../../piaskownica/s152c/sceny.json")
    indeksy = Path(sys.argv[3] if len(sys.argv) > 3 else "../../piaskownica/s152c/indeksy_26.json")
    d_ind = json.load(open(indeksy, encoding="utf-8"))
    siatka = d_ind.get("siatka")
    if siatka is None:
        # build_druga.py nie zapisuje siatki; ta sama siatka jest w pliku z 23.10
        alt = indeksy.parent / "indeksy_23.json"
        siatka = json.load(open(alt, encoding="utf-8"))["siatka"]
    powierzchnie = wczytaj_powierzchnie(sceny)

    zrodlo = ZrodloZPlikow(cache / "indeksy26.npz", siatka["szer"], siatka["wys"], "2026-10-26")
    segmentator = SegmentatorULDK(cache / "maski.npz", powierzchnie)

    wynik = {"data": "2026-10-26", "scena": d_ind["scena"], "dzialki": {}, "zgodnosc": {},
             "test_chmur": {}}
    ok = True
    for d in DZIALKI:
        ident = f"{OBREB}.{d}"
        w = uruchom_lancuch(ident, zrodlo, segmentator, AtrapaOpis())
        ref = d_ind["wyniki"].get(ident, {})
        zgodne = (w.wskaznik is not None and ref
                  and abs(w.wskaznik.ndre_srednia - ref["ndre_srednia"]) < 1e-6
                  and w.wskaznik.piksele_uzyte == ref["piksele_uzyte"])
        ok = ok and w.status == STATUS_OK and zgodne
        wynik["dzialki"][d] = {
            "status": w.status,
            "ndre_srednia": round(w.wskaznik.ndre_srednia, 6) if w.wskaznik else None,
            "piksele": w.wskaznik.piksele_uzyte if w.wskaznik else 0,
            "pokrycie": round(w.wskaznik.pokrycie_pola, 6) if w.wskaznik else None,
            "opis_model": w.opis.model if w.opis else None,
        }
        wynik["zgodnosc"][d] = {
            "zgodne": zgodne,
            "ndre_lancuch": round(w.wskaznik.ndre_srednia, 6) if w.wskaznik else None,
            "ndre_statystyki": ref.get("ndre_srednia"),
        }
        print(f"{d:6s} {w.status:8s} NDRE={w.wskaznik.ndre_srednia:.6f} "
              f"px={w.wskaznik.piksele_uzyte} zgodne={zgodne}")

    # 90/1 — nazwany brak, nie wyjątek na cały przebieg
    try:
        uruchom_lancuch(f"{OBREB}.{BRAK}", zrodlo, segmentator, AtrapaOpis())
    except BrakDzialki as e:
        wynik["dzialki"][BRAK] = {"status": "BRAK_ULDK", "komunikat": str(e)}
        print(f"{BRAK:6s} BRAK_ULDK {e}")
    except Exception as e:  # noqa: BLE001
        wynik["dzialki"][BRAK] = {"status": "BLAD", "komunikat": f"{type(e).__name__}: {e}"}
        print(f"{BRAK:6s} BLAD {type(e).__name__}: {e}")

    # test zachmurzenia: ta sama scena + SCL z 28.10.2026 (100% chmur nad działkami)
    zrodlo28 = ZrodloZPlikow(cache / "indeksy26.npz", siatka["szer"], siatka["wys"],
                             "2026-10-28", scl_npz=cache / "scl28.npy")
    w28 = uruchom_lancuch(f"{OBREB}.90/8", zrodlo28, segmentator, AtrapaOpis())
    wynik["test_chmur"] = {"status": w28.status, "komunikat": w28.komunikat,
                           "wskaznik": w28.wskaznik is not None}
    print("TEST28", w28.status, "|", w28.komunikat)
    ok = ok and w28.status == STATUS_CHMURY and w28.wskaznik is None

    json.dump(wynik, open("raport_lancuch.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("ZAPISANO raport_lancuch.json;", "OK" if ok else "SĄ ROZBIEŻNOŚCI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
