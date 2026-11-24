"""Collecte des entreprises via l'API publique et gratuite « Recherche d'entreprises »
(data.gouv.fr / INSEE Sirene). Aucune clé nécessaire. Limite : ~7 requêtes/seconde.
"""
import time

import requests

import config

API = "https://recherche-entreprises.api.gouv.fr/search"
GEO = "https://geo.api.gouv.fr/communes"


def trouver_commune(nom_ville):
    """Renvoie (code_insee, nom, département) de la ville la plus peuplée portant ce nom."""
    r = requests.get(GEO, params={"nom": nom_ville, "fields": "code,nom,codeDepartement,population",
                                  "boost": "population", "limit": 1}, timeout=20)
    r.raise_for_status()
    res = r.json()
    if not res:
        raise SystemExit(f"Ville introuvable : {nom_ville}")
    c = res[0]
    return c["code"], c["nom"], c["codeDepartement"]


# Paris, Lyon et Marseille : les entreprises sont enregistrées par arrondissement
ARRONDISSEMENTS = {
    "75056": [f"751{i:02d}" for i in range(1, 21)],   # Paris 1er à 20e
    "69123": [f"6938{i}" for i in range(1, 10)],       # Lyon 1er à 9e
    "13055": [f"132{i:02d}" for i in range(1, 17)],   # Marseille 1er à 16e
}


def codes_communes(code):
    """Liste des codes INSEE à interroger pour une ville."""
    return ARRONDISSEMENTS.get(code, [code])


def _get(params, essais=5):
    for i in range(essais):
        try:
            r = requests.get(API, params=params, timeout=30,
                             headers={"User-Agent": config.USER_AGENT})
            if r.status_code == 429:
                time.sleep(2 + i * 2)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(2 + i * 2)
    return {"results": [], "total_pages": 0}


def _nom_affiche(ul, etab):
    """Nom court et lisible : 1re enseigne, sans forme juridique ni parenthèses."""
    import re
    nom = _nom_brut(ul, etab)
    nom = nom.split(" / ")[0].split("(")[0]
    nom = re.sub(r"^(Sarl|Sas|Sasu|Eurl|Sa|Snc|Ste|Societe|Ets)\s+|\s+(Sarl|Sas|Sasu|Eurl)$", "",
                 nom.strip(), flags=re.I)
    return nom.strip() or _nom_brut(ul, etab)


def _nom_brut(ul, etab):
    enseignes = etab.get("liste_enseignes") or []
    nom_commercial = etab.get("nom_commercial")
    if enseignes:
        return enseignes[0].title()
    if nom_commercial:
        return nom_commercial.title()
    return (ul.get("nom_complet") or ul.get("nom_raison_sociale") or "").title()


def _dirigeant(ul):
    for d in ul.get("dirigeants") or []:
        formes = {"SARL", "SAS", "SASU", "EURL", "SA", "SCI", "SNC", "HOLDING", "STE", "SOCIETE"}
        if (d.get("type_dirigeant") == "personne physique" and d.get("nom") and d.get("prenoms")
                and not (set((d["prenoms"] + " " + d["nom"]).upper().split()) & formes)):
            prenom = (d.get("prenoms") or "").split(" ")[0].title()
            nom = d["nom"].split("(")[0].strip().title()
            return f"{prenom} {nom}".strip(), (d.get("qualite") or "")
    return "", ""


def collecter_secteur(nom_secteur, regle, zone, log=print, maximum=None):
    """Les entreprises employeuses d'un secteur dans la zone.

    zone = {"code_commune": "21231"} ou {"departement": "21"}
    maximum = on s'arrête après ce nombre d'établissements (grandes villes).
    """
    tranches = ",".join(k for k in config.TRANCHES)
    filtres = []
    if regle.get("naf"):
        filtres.append({"activite_principale": ",".join(regle["naf"])})
    for s in regle.get("sections", []):
        filtres.append({"section_activite_principale": s})

    exclus = set(regle.get("exclure_naf", []))
    trouves = {}
    for filtre in filtres:
        page, total_pages = 1, 1
        while page <= total_pages:
            if maximum and len(trouves) >= maximum:
                break
            params = {"etat_administratif": "A", "tranche_effectif_salarie": tranches,
                      "per_page": 25, "page": page, **filtre, **zone}
            data = _get(params)
            total_pages = data.get("total_pages", 0) or 0
            for ul in data.get("results", []):
                for etab in ul.get("matching_etablissements") or []:
                    # on vérifie l'établissement lui-même (pas seulement le siège)
                    if etab.get("etat_administratif") != "A":
                        continue
                    if "code_commune" in zone and etab.get("commune") not in zone["code_commune"].split(","):
                        continue
                    naf = etab.get("activite_principale") or ""
                    if naf in exclus:
                        continue
                    tranche = etab.get("tranche_effectif_salarie") or ""
                    if tranche not in config.TRANCHES:
                        continue
                    if etab.get("statut_diffusion_etablissement") not in (None, "O"):
                        continue  # diffusion restreinte : on respecte le choix de l'entreprise
                    dirigeant, qualite = _dirigeant(ul)
                    siret = etab.get("siret")
                    trouves[siret] = {
                        "siret": siret,
                        "siren": ul.get("siren"),
                        "entreprise": _nom_affiche(ul, etab),
                        "raison_sociale": ul.get("nom_raison_sociale") or ul.get("nom_complet") or "",
                        "enseignes": " | ".join(etab.get("liste_enseignes") or []),
                        "secteur": nom_secteur,
                        "naf": naf,
                        "tranche": tranche,
                        "effectif": config.TRANCHES.get(tranche, ""),
                        "dirigeant": dirigeant,
                        "qualite_dirigeant": qualite,
                        "adresse": etab.get("adresse") or "",
                        "code_postal": etab.get("code_postal") or "",
                        "ville": etab.get("libelle_commune") or "",
                        "latitude": float(etab["latitude"]) if etab.get("latitude") else None,
                        "longitude": float(etab["longitude"]) if etab.get("longitude") else None,
                        "date_creation": etab.get("date_creation") or "",
                        "nb_etablissements_entreprise": ul.get("nombre_etablissements_ouverts") or 1,
                    }
            log(f"   {nom_secteur} : page {page}/{max(total_pages, 1)} — {len(trouves)} établissements")
            page += 1
            time.sleep(0.2)
    return list(trouves.values())
