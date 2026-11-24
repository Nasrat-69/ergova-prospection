"""Enrichissement gratuit via OpenStreetMap (API Overpass) :
téléphone, site web et e-mail des commerces et entreprises cartographiés.
"""
import json
import math
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher

import requests

import config

from . import chemins

CACHE_DIR = chemins.CACHE


NON_ENTREPRISES = {"car_sharing", "parking", "bicycle_rental", "charging_station", "bus_station",
                   "school", "townhall", "post_box", "toilets", "place_of_worship", "kindergarten",
                   "college", "university", "library", "social_facility", "fuel"}


def normaliser(txt):
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    txt = re.sub(r"\b(sarl|sas|sasu|eurl|sa|sci|snc|ets|etablissements|ste|societe|et fils|et cie|l|la|le|les|de|du|des|d)\b", " ", txt)
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _lieux_depuis(elements):
    lieux = []
    for e in elements:
        t = e.get("tags", {})
        if (t.get("amenity") in NON_ENTREPRISES or "public_transport" in t
                or "highway" in t or "railway" in t):
            continue
        lieux.append({
            "id": f"{e.get('type')}{e.get('id')}",
            "nom": t.get("name", ""),
            "nom_norm": normaliser(t.get("name", "")),
            "telephone": t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or "",
            "site": t.get("website") or t.get("contact:website") or "",
            "email": t.get("email") or t.get("contact:email") or "",
            "lat": e.get("lat") or (e.get("center") or {}).get("lat"),
            "lon": e.get("lon") or (e.get("center") or {}).get("lon"),
        })
    return lieux


CLES_CONTACT = ["phone", "contact:phone", "contact:mobile", "website", "contact:website",
                "email", "contact:email"]


def _requete_carre(b, log):
    """Une petite requête par type d'info (les serveurs bloquent sur les grosses requêtes)."""
    bb = ",".join(f"{x:.4f}" for x in b)
    elements = []
    for cle in CLES_CONTACT:
        res = _requete(f'[out:json][timeout:60];nwr({bb})["name"]["{cle}"];out tags center;', log)
        if res is None:
            return None
        elements += res
    return elements


def _requete(requete, log):
    for tour in range(3):
        # le dernier serveur qui a répondu passe en premier
        for serveur in sorted(config.OVERPASS_SERVEURS, key=lambda s: s != _SERVEUR_OK[0]):
            if serveur in _SERVEURS_MORTS:
                continue
            try:
                r = requests.post(serveur, data={"data": requete}, timeout=(6, 60),
                                  headers={"User-Agent": config.OSM_USER_AGENT})
                if r.status_code == 200:
                    _SERVEUR_OK[0] = serveur
                    return r.json().get("elements", [])
            except requests.ConnectionError:
                _SERVEURS_MORTS.add(serveur)  # injoignable : on ne le réessaie plus
            except (requests.RequestException, ValueError):
                pass
        if len(_SERVEURS_MORTS) == len(config.OVERPASS_SERVEURS):
            return None
        log(f"   OpenStreetMap : serveurs occupés, nouvel essai dans {10 * (tour + 1)} s…")
        time.sleep(10 * (tour + 1))
    return None


_SERVEURS_MORTS = set()
_SERVEUR_OK = [""]


def charger_osm(code_zone, bbox, log=print, taille_carre=0.15):
    """Récupère tous les lieux nommés avec téléphone/site/e-mail dans la zone.

    bbox = (sud, ouest, nord, est). La zone est découpée en carrés d environ 15 km,
    chacun gardé en cache 30 jours : si un serveur échoue, on ne perd pas le reste.
    """
    dossier = os.path.join(CACHE_DIR, f"osm_{code_zone}")
    os.makedirs(dossier, exist_ok=True)
    sud, ouest, nord, est = bbox
    carres = []
    lat = sud
    while lat < nord:
        lon = ouest
        while lon < est:
            carres.append((lat, lon, min(lat + taille_carre, nord), min(lon + taille_carre, est)))
            lon += taille_carre
        lat += taille_carre

    lieux, manquants = {}, 0
    for i, c in enumerate(carres, 1):
        fichier = os.path.join(dossier, "_".join(f"{x:.3f}" for x in c) + ".json")
        if os.path.exists(fichier) and time.time() - os.path.getmtime(fichier) < 30 * 86400:
            with open(fichier, encoding="utf-8") as f:
                elements = json.load(f)
        else:
            log(f"   OpenStreetMap : zone {i}/{len(carres)}…")
            elements = _requete_carre(c, log)
            if elements is None:
                manquants += 1
                continue
            with open(fichier, "w", encoding="utf-8") as f:
                json.dump(elements, f, ensure_ascii=False)
        for l in _lieux_depuis(elements):
            lieux[l["id"]] = l
    if manquants:
        log(f"   OpenStreetMap : {manquants} zone(s) non chargée(s) — relance plus tard pour compléter.")
    log(f"   OpenStreetMap : {len(lieux)} lieux avec coordonnées de contact")
    return list(lieux.values())


def _autour(p):
    """Lieux avec contact dans un rayon de 150 m autour d'un prospect (avec cache)."""
    dossier = os.path.join(CACHE_DIR, "osm_autour")
    fichier = os.path.join(dossier, f"{p['siret']}.json")
    if os.path.exists(fichier) and time.time() - os.path.getmtime(fichier) < 30 * 86400:
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    pos = f"around:150,{p['latitude']:.6f},{p['longitude']:.6f}"
    requete = ("[out:json][timeout:25];("
               + "".join(f'nwr({pos})["name"]["{k}"];' for k in CLES_CONTACT)
               + ");out tags center;")
    elements = _requete(requete, lambda m: None)
    if elements is None:
        return None
    os.makedirs(dossier, exist_ok=True)
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(elements, f, ensure_ascii=False)
    return elements


def chercher_autour(prospects, log=print, fils=4):
    """Pour les grandes zones (Paris, département…) : une petite recherche par adresse
    au lieu de télécharger toute la carte. Renvoie {siret: lieu}."""
    from concurrent.futures import ThreadPoolExecutor
    a_chercher = [p for p in prospects if p.get("latitude") and p.get("longitude")]
    trouves, fait = {}, 0
    log(f"   OpenStreetMap : recherche autour de {len(a_chercher)} adresses…")
    with ThreadPoolExecutor(max_workers=fils) as pool:
        for p, elements in zip(a_chercher, pool.map(_autour, a_chercher)):
            fait += 1
            if fait % 25 == 0:
                log(f"   OpenStreetMap : {fait}/{len(a_chercher)} adresses vérifiées")
            if elements:
                lieu = associer(p, _lieux_depuis(elements))
                if lieu:
                    trouves[p["siret"]] = lieu
    return trouves


def _distance_m(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    rad = math.pi / 180
    dlat, dlon = (lat2 - lat1) * rad, (lon2 - lon1) * rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def _similarite(a, b):
    if not a or not b:
        return 0
    if a == b:
        return 1
    court, long_ = sorted((a, b), key=len)
    if len(court) >= 4 and court in long_ and len(court) >= 0.6 * len(long_):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def associer(prospect, lieux):
    """Cherche le lieu OSM correspondant au prospect (nom proche + position proche)."""
    ville = normaliser(prospect.get("ville", ""))
    def sans_ville(n):
        n = normaliser(n)
        return re.sub(rf"{re.escape(ville)}", " ", n).strip() if ville else n
    noms = {sans_ville(prospect["entreprise"]), sans_ville(prospect["raison_sociale"])}
    noms |= {sans_ville(n) for n in prospect["enseignes"].split(" | ") if n}
    noms = {n for n in noms if len(n) >= 3}
    meilleur, meilleur_score = None, 0
    for lieu in lieux:
        nom_lieu = re.sub(rf"{re.escape(ville)}", " ", lieu["nom_norm"]).strip() if ville else lieu["nom_norm"]
        sim = max((_similarite(n, nom_lieu) for n in noms), default=0)
        if sim < 0.75:
            continue
        d = _distance_m(prospect["latitude"], prospect["longitude"], lieu["lat"], lieu["lon"])
        if d is not None and d > 400 and sim < 0.95:
            continue  # même nom mais trop loin : probablement un autre établissement
        score = sim + (0.2 if d is not None and d < 150 else 0)
        if score > meilleur_score:
            meilleur, meilleur_score = lieu, score
    return meilleur
