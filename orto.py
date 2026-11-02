"""Ortofoto GUGiK (WMS) + data zdjęcia z WFS Skorowidze.

Pułapka źródła, sprawdzona w S147o i trzymana tutaj: WMS **1.3.0** z `CRS=EPSG:2180`
zwracał biały obraz (wszystkie piksele 255), a ten sam obszar w WMS **1.1.1**
z `SRS=EPSG:2180` zwracał prawdziwe zdjęcie. Dlatego pytamy 1.1.1 i **sprawdzamy,
czy obraz nie jest jednolity** — biały obraz to awaria źródła, nie „puste pole".

Data zdjęcia nie jest w WMS. Bierzemy ją z publicznego skorowidza WFS
(`PZGIK/ORTO/WFS/Skorowidze`, warstwa `gugik:SkorowidzOrtofomapy<rok>`), pole
`akt_data/gml:timePosition`. Data dotyczy arkusza, który obejmuje bbox — nie każdego
piksela z osobna; tak jest zapisane w wyniku.
"""

from __future__ import annotations

import io
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np

WMS = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/HighResolution"
WFS = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WFS/Skorowidze"
NS = {"gugik": "http://www.gugik.gov.pl", "gml": "http://www.opengis.net/gml/3.2"}


def _get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pole-z-gory/1.0"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def pobierz_ortofoto(bbox2180: tuple[float, float, float, float], szer: int = 2048,
                     wys: int = 777) -> dict:
    """PNG ortofoto dla bbox w EPSG:2180. Sprawdza, czy obraz nie jest jednolity."""
    q = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "LAYERS": "Raster", "STYLES": "", "FORMAT": "image/png",
        "SRS": "EPSG:2180", "BBOX": ",".join(f"{x:.2f}" for x in bbox2180),
        "WIDTH": str(szer), "HEIGHT": str(wys),
    }
    t0 = time.time()
    dane = _get(WMS + "?" + urllib.parse.urlencode(q))
    czas = time.time() - t0
    from PIL import Image
    im = Image.open(io.BytesIO(dane)).convert("RGB")
    a = np.asarray(im)
    jednolity = bool(a.std() < 1.0)
    if jednolity:
        raise ValueError(
            f"WMS zwrócił jednolity obraz (średnia {a.mean():.0f}, odchylenie {a.std():.2f}) — "
            "to awaria źródła/parametrów, nie puste pole")
    return {"png": dane, "szer": im.width, "wys": im.height, "czas_s": round(czas, 2),
            "srgb": [round(float(a[:, :, i].mean()), 1) for i in range(3)],
            "kolory": int(len(np.unique(a.reshape(-1, 3), axis=0))),
            "bbox2180": list(bbox2180), "wms_wersja": "1.1.1", "srs": "EPSG:2180"}


def skorowidz(bbox2180: tuple[float, float, float, float], rok: int = 2025) -> tuple[list[dict], float]:
    """Wiersze skorowidza ortofoto dla bbox: arkusz, data zdjęcia, piksel, nr zgłoszenia."""
    q = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": f"gugik:SkorowidzOrtofomapy{rok}", "COUNT": "20",
        "SRSNAME": "EPSG:2180",
        "BBOX": ",".join(f"{x:.2f}" for x in bbox2180) + ",EPSG:2180",
    }
    t0 = time.time()
    xml = _get(WFS + "?" + urllib.parse.urlencode(q))
    korzen = ET.fromstring(xml)
    wynik = []
    for el in korzen.iter():
        if el.tag.endswith(f"SkorowidzOrtofomapy{rok}"):
            w = {"rok_warstwy": rok}
            for pole in ("godlo", "akt_rok", "piksel", "kolor", "zrodlo_danych", "nr_zglosz",
                         "czy_ark_wypelniony", "uklad_xy"):
                x = el.find(f"gugik:{pole}", NS)
                if x is not None:
                    w[pole] = (x.text or "").strip()
            d = el.find("gugik:akt_data/gml:timePosition", NS)
            if d is not None:
                w["data_zdjecia"] = (d.text or "").strip()
            wynik.append(w)
    return wynik, round(time.time() - t0, 2)


def bbox_z_geometrii(geometrie, margines: float = 0.0) -> tuple[float, float, float, float]:
    from shapely.ops import unary_union
    g = unary_union(list(geometrie))
    minx, miny, maxx, maxy = g.bounds
    return (minx - margines, miny - margines, maxx + margines, maxy + margines)
