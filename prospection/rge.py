"""Source officielle gratuite pour le BTP : liste des entreprises RGE (ADEME, open data).
Contient téléphone, e-mail et site web, avec le SIRET -> correspondance exacte.
"""
import time

import requests

import config

API = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"


def charger_rge(codes_postaux, log=print):
    """Renvoie {siret: {telephone, email, site}} pour les codes postaux donnés."""
    resultat = {}
    for cp in sorted(set(c for c in codes_postaux if c)):
        url, params = API, {"size": 1000, "qs": f"code_postal:{cp}",
                            "select": "siret,telephone,email,site_internet"}
        while url:
            try:
                r = requests.get(url, params=params, timeout=30,
                                 headers={"User-Agent": config.USER_AGENT})
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException, ValueError):
                break
            for ligne in data.get("results", []):
                siret = ligne.get("siret")
                if not siret:
                    continue
                fiche = resultat.setdefault(siret, {"telephone": "", "email": "", "site": ""})
                fiche["telephone"] = fiche["telephone"] or (ligne.get("telephone") or "")
                fiche["email"] = fiche["email"] or (ligne.get("email") or "").strip().lower()
                fiche["site"] = fiche["site"] or (ligne.get("site_internet") or "")
            url, params = data.get("next"), None
            time.sleep(0.2)
    log(f"   Liste RGE (ADEME) : {len(resultat)} entreprises avec coordonnées")
    return resultat
