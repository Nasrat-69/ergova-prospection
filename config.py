"""Configuration de l'outil de prospection ERGOVA.

Modifie ce fichier pour changer les secteurs, les tailles d'entreprise ciblées
ou les réglages d'envoi d'e-mails.
"""

# ---------------------------------------------------------------------------
# Secteurs ciblés  ->  codes NAF (nomenclature INSEE)
# "label" sert dans les messages : « les entreprises du [label] »
# Mets "actif": False pour désactiver un secteur.
# ---------------------------------------------------------------------------
SECTEURS = {
    "BTP": {
        "label": "bâtiment",
        "sections": ["F"],  # toute la section F = construction (41, 42, 43)
        "naf": [],
        "actif": True,
    },
    "Transport": {
        "label": "transport",
        "sections": [],
        "naf": ["49.31Z", "49.32Z", "49.39A", "49.39B", "49.41A", "49.41B",
                "49.41C", "49.42Z", "52.10B", "52.29A", "52.29B", "53.20Z"],
        "actif": True,
    },
    "Industrie / Usine": {
        "label": "l'industrie",
        "sections": ["C"],  # industrie manufacturière (10 à 33)
        # codes déjà couverts par Boulangerie / Boucherie : exclus ici
        "exclure_naf": ["10.71B", "10.71C", "10.71D", "10.13B"],
        "naf": [],
        "actif": True,
    },
    "Supérette": {
        "label": "commerce alimentaire",
        "sections": [],
        "naf": ["47.11B", "47.11C"],
        "actif": True,
    },
    "Fleuriste": {
        "label": "fleuriste",
        "sections": [],
        "naf": ["47.76Z"],
        "actif": True,
    },
    "Garage": {
        "label": "garage automobile",
        "sections": [],
        "naf": ["45.20A", "45.20B"],
        "actif": True,
    },
    "Boulangerie / Pâtisserie": {
        "label": "boulangerie-pâtisserie",
        "sections": [],
        "naf": ["10.71B", "10.71C", "10.71D", "47.24Z"],
        "actif": True,
    },
    "Boucherie": {
        "label": "boucherie",
        "sections": [],
        "naf": ["47.22Z", "10.13B"],
        "actif": True,
    },
    # Présent dans la cible ERGOVA, désactivé par défaut
    "Immobilier": {
        "label": "l'immobilier",
        "sections": [],
        "naf": ["68.31Z", "68.32A"],
        "actif": False,
    },
}

# ---------------------------------------------------------------------------
# Taille d'entreprise (tranches d'effectif INSEE de l'établissement)
# ERGOVA : au moins 1 salarié, idéal 3 ou plus.
# ---------------------------------------------------------------------------
TRANCHES = {
    "01": "1-2 salariés",
    "02": "3-5 salariés",
    "03": "6-9 salariés",
    "11": "10-19 salariés",
    "12": "20-49 salariés",
    "21": "50-99 salariés",
    "22": "100-199 salariés",
    "31": "200-249 salariés",
    "32": "250-499 salariés",
    "41": "500-999 salariés",
    "42": "1000-1999 salariés",
    "51": "2000-4999 salariés",
    "52": "5000-9999 salariés",
    "53": "10000+ salariés",
}
# Points ajoutés au score selon la taille (3 à 49 salariés = cible idéale)
POINTS_TRANCHE = {
    "01": 10, "02": 30, "03": 35, "11": 35, "12": 30,
    "21": 15, "22": 10,
}
POINTS_TRANCHE_DEFAUT = 5  # 200 salariés et plus : ont souvent déjà un service HSE

# ---------------------------------------------------------------------------
# Envoi d'e-mails
# ---------------------------------------------------------------------------
EMAILS_PAR_JOUR_MAX = 500
PAUSE_ENTRE_EMAILS_SECONDES = (20, 60)  # pause aléatoire entre deux envois

# Serveurs OpenStreetMap (le premier qui répond est utilisé)
OVERPASS_SERVEURS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OutilProspection/1.0"

# Identifiant envoyé aux serveurs OpenStreetMap (ils refusent les faux navigateurs)
OSM_USER_AGENT = "OutilProspection/1.0 (prospection B2B locale)"
