"""Scoring des prospects et textes personnalisés (accroche d'appel + e-mail).

Règles ERGOVA respectées : toujours « jusqu'à » et « sous conditions »,
jamais « vous allez toucher 8 235 € », jamais « de la part de l'Assurance Maladie ».
"""
import os

import config
from . import chemins



def scorer(p):
    s = config.POINTS_TRANCHE.get(p["tranche"], config.POINTS_TRANCHE_DEFAUT)
    if p.get("telephone"):
        s += 25
    if p.get("email"):
        s += 20
    if p.get("dirigeant"):
        s += 5
    if p.get("site"):
        s += 5
    nb = int(p.get("nb_etablissements_entreprise") or 1)
    if nb <= 3:
        s += 10  # entreprise locale : le gérant décide lui-même
    elif nb > 20:
        s -= 15  # chaîne nationale : décision prise au siège
    p["score"] = s
    p["priorite"] = "A" if s >= 65 else "B" if s >= 45 else "C"
    return p


def label_secteur(p):
    return config.SECTEURS.get(p["secteur"], {}).get("label", p["secteur"].lower())


def du_secteur(p):
    """« du bâtiment », « de l'industrie », « de la boucherie »…"""
    label = label_secteur(p)
    if label.startswith("l'"):
        return "de " + label
    if label in ("boucherie", "boulangerie-pâtisserie"):
        return "de la " + label
    if label == "commerce alimentaire":
        return "du commerce alimentaire"
    return "du " + label


def accroche_appel(p):
    qui = p["dirigeant"] if p.get("dirigeant") else "le gérant"
    return (f"Bonjour, [Prénom] d'ERGOVA. Je voudrais parler à {qui}, s'il vous plaît. "
            f"C'est au sujet de l'aide prévention de l'Assurance Maladie pour les entreprises "
            f"{du_secteur(p)}. Elle peut aller jusqu'à 8 235 €, sous conditions.")


def _lire_modele(nom):
    with open(chemins.modele(nom), encoding="utf-8") as f:
        texte = f.read()
    premiere, _, corps = texte.partition("\n")
    objet = premiere.replace("Objet:", "").replace("Objet :", "").strip()
    return objet, corps.strip()


def email_prospection(p, signature):
    objet, corps = _lire_modele("email_prospection.txt")
    valeurs = {
        "entreprise": p["entreprise"],
        "bonjour": f"Bonjour {p['dirigeant']}," if p.get("dirigeant") else "Bonjour,",
        "du_secteur": du_secteur(p),
        "effectif": p.get("effectif") or "",
        "ville": (p.get("ville") or "").title(),
        **signature,
    }
    return objet.format(**valeurs), corps.format(**valeurs)
