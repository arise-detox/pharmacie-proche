#!/usr/bin/env python3
"""Génère les tuiles de pharmacies (data/p/*.json) à partir d'OpenStreetMap.

Une tuile = une case de 0,2° de côté (environ 22 km x 15 km), nommée "<ligne>_<colonne>"
avec ligne = floor(latitude*5) et colonne = floor(longitude*5) : le navigateur n'a donc
besoin d'aucun index pour savoir quels fichiers charger.

Sortie : <dossier>/p/*.json et <dossier>/meta.json (par défaut _site/data).
Si les données en cache ont moins de 6 jours, elles sont réutilisées (sauf FORCE_REFRESH=1).
"""
import csv, datetime as dt, io, json, math, os, re, shutil, sys, time
import requests

OUT = sys.argv[1] if len(sys.argv) > 1 else "_site/data"
CACHE = os.environ.get("PHARMA_CACHE", ".cache")
OVERPASS = [u for u in os.environ.get("PHARMA_OVERPASS", "https://overpass.openstreetmap.fr/api/interpreter,https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter").split(",") if u]
GEO = os.environ.get("PHARMA_GEO", "https://data.geopf.fr/geocodage")
MIN_COUNT = int(os.environ.get("PHARMA_MIN", "8000"))
FAST = os.environ.get("PHARMA_FAST") == "1"
ENRICH_BUDGET = int(os.environ.get("PHARMA_ENRICH_SECONDS", "720"))
HEADERS = {"User-Agent": "pharmacie-proche/1.0 (+https://github.com/arise-detox/pharmacie-proche)"}
TILE = 5  # cases par degré


def log(*a):
    print(*a, flush=True)


def pause(s):
    if not FAST:
        time.sleep(s)


def tile_key(lat, lon):
    return "%d_%d" % (math.floor(lat * TILE), math.floor(lon * TILE))


# ---------- 1. OpenStreetMap ----------
def overpass(s, w, n, e, depth=0):
    q = '[out:json][timeout:150];nwr["amenity"="pharmacy"](%s,%s,%s,%s);out center tags;' % (s, w, n, e)
    last = None
    for attempt in range(6):
        url = OVERPASS[attempt % len(OVERPASS)]
        try:
            r = requests.post(url, data={"data": q}, headers=HEADERS, timeout=(10, 180))
            if r.status_code == 200:
                j = r.json()
                rem = j.get("remark", "")
                if "elements" in j and not re.search(r"timed out|out of memory|runtime error", rem, re.I):
                    return j["elements"]
                last = "remark: " + rem
            else:
                last = "HTTP %d" % r.status_code
        except Exception as ex:  # réseau, JSON invalide, délai dépassé...
            last = repr(ex)[:120]
        log("  essai %d (%s) : %s" % (attempt + 1, url.split("/")[2], last))
        pause(4 * (attempt + 1))
    if depth < 2:  # zone trop lourde : on la découpe en quatre
        log("  découpage de la zone", (s, w, n, e))
        my, mx = (s + n) / 2.0, (w + e) / 2.0
        out = []
        for (a, b, c, d) in [(s, w, my, mx), (s, mx, my, e), (my, w, n, mx), (my, mx, n, e)]:
            out += overpass(a, b, c, d, depth + 1)
        return out
    raise RuntimeError("Overpass indisponible pour la zone %s : %s" % ((s, w, n, e), last))


def normalise(el):
    t = el.get("tags") or {}
    c = el.get("center") or el
    if c.get("lat") is None or c.get("lon") is None or t.get("dispensing") == "no":
        return None
    if t.get("disused:amenity") or t.get("opening_hours") == "off":
        return None
    street = " ".join(x for x in [t.get("addr:housenumber"), t.get("addr:street")] if x)
    city = " ".join(x for x in [t.get("addr:postcode"), t.get("addr:city")] if x)
    it = {
        "i": el["type"][0] + str(el["id"]),
        "y": round(c["lat"], 5), "x": round(c["lon"], 5),
        "n": (t.get("name") or t.get("brand") or "").strip(),
        "t": (t.get("phone") or t.get("contact:phone") or "").strip(),
        "h": (t.get("opening_hours") or "").strip(),
        "a": street, "c": city,
        "v": t.get("check_date:opening_hours") or t.get("check_date") or "",
        "w": t.get("website") or t.get("contact:website") or "",
    }
    return it


def fetch_all():
    items = {}
    for s in range(41, 53, 2):
        for w in range(-6, 10, 2):
            log("zone", s, w)
            for el in overpass(s, w, s + 2, w + 2):
                it = normalise(el)
                if it:
                    items[it["i"]] = it
            pause(2)
    return items


# ---------- 2. adresses manquantes (géocodage inverse en lot, IGN) ----------
def enrich(items):
    path = os.path.join(CACHE, "addr.json")
    try:
        known = json.load(open(path, encoding="utf-8"))
    except Exception:
        known = {}
    todo = []
    for it in items.values():
        if it["a"] and it["c"]:
            continue
        k = "%s,%s" % (it["y"], it["x"])
        hit = known.get(it["i"])
        if hit and hit.get("k") == k:
            it["a"] = it["a"] or hit.get("a", "")
            it["c"] = it["c"] or hit.get("c", "")
        else:
            todo.append(it)
    log("adresses à compléter :", len(todo))
    t0, done = time.time(), 0
    for i in range(0, len(todo), 1000):
        if time.time() - t0 > ENRICH_BUDGET:
            log("budget de temps atteint, la suite sera traitée au prochain passage")
            break
        part = todo[i:i + 1000]
        buf = io.StringIO()
        wr = csv.writer(buf)
        wr.writerow(["id", "lat", "lon"])
        for it in part:
            wr.writerow([it["i"], it["y"], it["x"]])
        try:
            r = requests.post(GEO + "/reverse/csv", files={"data": ("p.csv", buf.getvalue().encode("utf-8"), "text/csv")}, headers=HEADERS, timeout=(10, 300))
            r.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        except Exception as ex:
            log("  lot ignoré :", repr(ex)[:160])
            continue
        byid = {it["i"]: it for it in part}
        for row in rows:
            it = byid.get(row.get("id"))
            if not it:
                continue
            if row.get("result_status") not in (None, "", "ok"):
                continue
            try:
                if row.get("result_distance") and float(row["result_distance"]) > 100:
                    continue
            except ValueError:
                pass
            street = " ".join(x for x in [row.get("result_housenumber"), row.get("result_street") or row.get("result_name")] if x).strip()
            city = " ".join(x for x in [row.get("result_postcode"), row.get("result_city")] if x).strip()
            k = "%s,%s" % (it["y"], it["x"])
            known[it["i"]] = {"k": k, "a": street, "c": city}
            it["a"] = it["a"] or street
            it["c"] = it["c"] or city
            done += 1
        os.makedirs(CACHE, exist_ok=True)
        json.dump(known, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        pause(1)
    log("adresses ajoutées :", done)


# ---------- 3. écriture ----------
def write(items, out):
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "p"))
    tiles = {}
    for it in items.values():
        tiles.setdefault(tile_key(it["y"], it["x"]), []).append(it)
    for k, lst in tiles.items():
        lst.sort(key=lambda z: z["i"])
        with open(os.path.join(out, "p", k + ".json"), "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, separators=(",", ":"))
    meta = {"built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "count": len(items), "tiles": len(tiles)}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), separators=(",", ":"))
    return meta


def main():
    cached = os.path.join(CACHE, "data")
    force = os.environ.get("FORCE_REFRESH") == "1"
    try:
        m = json.load(open(os.path.join(cached, "meta.json")))
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(m["built"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)).days
        if not force and age < 6:
            log("données en cache (%d j, %d pharmacies) : réutilisées" % (age, m["count"]))
            if os.path.abspath(cached) != os.path.abspath(OUT):
                if os.path.isdir(OUT):
                    shutil.rmtree(OUT)
                shutil.copytree(cached, OUT)
            return
    except Exception:
        pass
    items = fetch_all()
    log("pharmacies trouvées :", len(items))
    if len(items) < MIN_COUNT:
        log("Trop peu de résultats (%d < %d) : on ne publie pas ces données." % (len(items), MIN_COUNT))
        sys.exit(1)
    enrich(items)
    meta = write(items, OUT)
    log("tuiles écrites :", meta)
    if os.path.abspath(cached) != os.path.abspath(OUT):
        if os.path.isdir(cached):
            shutil.rmtree(cached)
        shutil.copytree(OUT, cached)


if __name__ == "__main__":
    main()
