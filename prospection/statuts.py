"""Statuts de suivi des prospects : liste, couleurs (application + Excel) et règles."""

DEFAUT = "À appeler"

# nom : (fond, texte) — mêmes couleurs dans l'application et dans l'Excel
COULEURS = {
    "À appeler":                ("E8EAED", "3C4043"),
    "Pas de réponse":           ("C6DBE1", "2F4F5A"),
    "Rappeler":                 ("FFE5A0", "473821"),
    "Intéressé":                ("11734B", "FFFFFF"),
    "RDV pris":                 ("BFE1F6", "0A53A8"),
    "Pas intéressé":            ("B10202", "FFFFFF"),
    "Numéro erroné":            ("FFCFC9", "8A1C0B"),
    "E-mail envoyé":            ("E6CFF2", "5A3286"),
    "Client":                   ("0A53A8", "FFFFFF"),
    "STOP / ne plus contacter": ("3C4043", "FFFFFF"),
}
LISTE = list(COULEURS)

# anciens statuts -> nouveaux (mise à niveau automatique des bases existantes)
ANCIENS = {
    "À contacter": "À appeler",
    "Appelé - pas joignable": "Pas de réponse",
    "Messagerie laissée": "Pas de réponse",
    "Formulaire envoyé": "Intéressé",
    "Formulaire rempli": "Intéressé",
    "Pas éligible": "Pas intéressé",
}

# ces prospects ne reçoivent plus d'e-mail de prospection
BLOQUANTS_EMAIL = {"STOP / ne plus contacter", "Pas intéressé", "Client", "Intéressé", "RDV pris"}

# statuts qui ne comptent pas comme « à rappeler »
TERMINES = {"Pas intéressé", "Client", "STOP / ne plus contacter", "Numéro erroné"}


def est_mobile(tel):
    """Numéro de mobile français : 06 / 07 (ou +33 6 / +33 7)."""
    chiffres = "".join(c for c in (tel or "") if c.isdigit())
    if chiffres.startswith("33") and len(chiffres) == 11:
        chiffres = "0" + chiffres[2:]
    return len(chiffres) == 10 and chiffres[:2] in ("06", "07")
