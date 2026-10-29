"""Met à jour data.json à partir de la collection BoardGameGeek de Moissbatt.

Utilise l'API XML officielle de BGG avec le jeton BGG_TOKEN (secret GitHub).
Format de data.json : {"u": date ISO, "C": [catégories], "M": [mécaniques], "R": [lignes]}
ligne = [id, nom, année, note moyenne, complexité, extension 0/1, min joueurs, max joueurs,
         durée min, durée max, âge min, [indices C], [indices M], description, chemin d'image]
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

USER = "Moissbatt"
API = "https://boardgamegeek.com/xmlapi2/"
IMG = "https://cf.geekdo-images.com/"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.json")
TOKEN = os.environ.get("BGG_TOKEN", "").strip()


def get(path, tries=10):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + TOKEN,
                                                      "User-Agent": "ludotheque-moissbatt"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                if r.status == 202:  # BGG prépare la collection : on réessaie
                    time.sleep(5 + 3 * i)
                    continue
                return ET.fromstring(body)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(10 + 5 * i)
                continue
            if e.code == 401:
                sys.exit("BGG refuse le jeton (401) : vérifie le secret BGG_TOKEN.")
            raise
    sys.exit("BGG ne répond pas après plusieurs essais : " + path)


def num(v, cast=int):
    try:
        x = cast(v)
        return x if x else None
    except (TypeError, ValueError):
        return None


def val(el, tag):
    e = el.find(tag)
    return e.get("value") if e is not None else None


def collection():
    """{id: nom} des jeux possédés, extensions comprises."""
    out = {}
    for q in ("subtype=boardgame&excludesubtype=boardgameexpansion", "subtype=boardgameexpansion"):
        root = get(f"collection?username={USER}&own=1&{q}")
        for it in root.findall("item"):
            name = (it.findtext("name") or "").strip()
            out[int(it.get("objectid"))] = name
    return out


def things(ids):
    res = {}
    ids = list(ids)
    for i in range(0, len(ids), 20):
        root = get("thing?stats=1&id=" + ",".join(map(str, ids[i:i + 20])))
        for it in root.findall("item"):
            primary = next((n.get("value") for n in it.findall("name") if n.get("type") == "primary"), "")
            rat = it.find("statistics/ratings")
            res[int(it.get("id"))] = {
                "name": primary,
                "ext": 1 if it.get("type") == "boardgameexpansion" else 0,
                "year": num(val(it, "yearpublished")) or 0,
                "avg": round(float(val(rat, "average")), 2) if rat is not None and num(val(rat, "average"), float) else None,
                "weight": round(float(val(rat, "averageweight")), 2) if rat is not None and num(val(rat, "averageweight"), float) else None,
                "minp": num(val(it, "minplayers")), "maxp": num(val(it, "maxplayers")),
                "minpt": num(val(it, "minplaytime")), "maxpt": num(val(it, "maxplaytime")),
                "age": num(val(it, "minage")),
                "cats": [l.get("value") for l in it.findall("link") if l.get("type") == "boardgamecategory"
                         and l.get("value") != "Expansion for Base-game"],
                "mechs": [l.get("value") for l in it.findall("link") if l.get("type") == "boardgamemechanic"],
                "thumb": (it.findtext("thumbnail") or "").strip(),
            }
        time.sleep(5)  # rythme demandé par BGG
    return res


def main():
    if not TOKEN:
        sys.exit("Secret BGG_TOKEN absent.")
    data = json.load(open(DATA, encoding="utf-8"))
    C, M = data["C"], data["M"]
    old = {r[0]: r for r in data["R"]}

    owned = collection()
    if not owned:
        sys.exit("Collection vide renvoyée par BGG : rien n'est modifié par prudence.")
    info = things(owned)

    def ix(lst, v):
        if v not in lst:
            lst.append(v)
        return lst.index(v)

    rows = []
    for gid, cname in owned.items():
        t = info.get(gid)
        prev = old.get(gid)
        if t is None:
            if prev:
                rows.append(prev)
            continue
        desc = prev[13] if prev else ""
        img = prev[14] if prev and prev[14] else (t["thumb"][len(IMG):] if t["thumb"].startswith(IMG) else "")
        rows.append([gid, cname or t["name"], t["year"], t["avg"], t["weight"], t["ext"],
                     t["minp"], t["maxp"], t["minpt"], t["maxpt"], t["age"],
                     [ix(C, c) for c in t["cats"]], [ix(M, m) for m in t["mechs"]],
                     "" if t["ext"] else desc, img])
    rows.sort(key=lambda r: r[1].casefold())

    added = set(owned) - set(old)
    removed = set(old) - set(owned)
    if rows == sorted(data["R"], key=lambda r: r[1].casefold()) and C == data["C"] and M == data["M"]:
        print("Aucun changement.")
        return
    data.update(u=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                C=C, M=M, R=rows)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(rows)} entrées ; ajoutées : {len(added)} ; retirées : {len(removed)}")


if __name__ == "__main__":
    main()
