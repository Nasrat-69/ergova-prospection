"""Comptes utilisateurs de l'application (stockés sur ce PC uniquement).

Les mots de passe ne sont jamais enregistrés en clair : seule une empreinte
PBKDF2-SHA256 avec sel aléatoire est gardée dans donnees/comptes.json.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
from datetime import datetime

from . import chemins

FICHIER = os.path.join(chemins.DONNEES, "comptes.json")
ITERATIONS = 200_000
_verrou = threading.Lock()


def _lire():
    if not os.path.exists(FICHIER):
        return {}
    with open(FICHIER, encoding="utf-8") as f:
        return json.load(f)


def _ecrire(comptes):
    os.makedirs(chemins.DONNEES, exist_ok=True)
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(comptes, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FICHIER)


def _empreinte(mot_de_passe, sel):
    return hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), bytes.fromhex(sel), ITERATIONS).hex()


def identifiant_valide(ident):
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,30}", ident or ""))


def liste():
    return [{"identifiant": k, "nom": v.get("nom", k)} for k, v in sorted(_lire().items())]


def existe_au_moins_un():
    return bool(_lire())


def dossier(ident):
    return os.path.join(chemins.COMPTES, ident)


def creer(ident, nom, mot_de_passe):
    ident = (ident or "").strip().lower()
    if not identifiant_valide(ident):
        raise ValueError("Identifiant : 2 à 31 caractères, lettres minuscules, chiffres, point ou tiret (ex : karim).")
    if len(mot_de_passe or "") < 6:
        raise ValueError("Le mot de passe doit faire au moins 6 caractères.")
    with _verrou:
        comptes = _lire()
        if ident in comptes:
            raise ValueError("Cet identifiant existe déjà.")
        premier = not comptes
        sel = secrets.token_hex(16)
        comptes[ident] = {"nom": (nom or ident).strip()[:60], "sel": sel,
                          "empreinte": _empreinte(mot_de_passe, sel),
                          "cree_le": datetime.now().isoformat(timespec="seconds")}
        d = dossier(ident)
        chemins.preparer_compte(d)
        if premier:
            migrer_anciennes_donnees(d)
        _ecrire(comptes)
    return ident


def verifier(ident, mot_de_passe):
    ident = (ident or "").strip().lower()
    c = _lire().get(ident)
    if not c:
        hmac.compare_digest("x", "y")  # même temps de réponse
        return None
    if hmac.compare_digest(c["empreinte"], _empreinte(mot_de_passe or "", c["sel"])):
        return ident
    return None


def changer_mot_de_passe(ident, ancien, nouveau):
    if not verifier(ident, ancien):
        raise ValueError("Mot de passe actuel incorrect.")
    if len(nouveau or "") < 6:
        raise ValueError("Le nouveau mot de passe doit faire au moins 6 caractères.")
    with _verrou:
        comptes = _lire()
        sel = secrets.token_hex(16)
        comptes[ident].update(sel=sel, empreinte=_empreinte(nouveau, sel))
        _ecrire(comptes)


def nom(ident):
    return _lire().get(ident, {}).get("nom", ident)


def migrer_anciennes_donnees(d):
    """Le tout premier compte récupère les données d'avant les comptes."""
    app = chemins.APP
    deplacements = [
        (os.path.join(chemins.DONNEES, "prospects.db"), os.path.join(d, "prospects.db")),
        (os.path.join(app, "parametres_envoi.ini"), os.path.join(d, "parametres_envoi.ini")),
        (os.path.join(app, "desinscrits.txt"), os.path.join(d, "desinscrits.txt")),
    ]
    for source, cible in deplacements:
        if os.path.exists(source) and not os.path.exists(cible):
            shutil.move(source, cible)
    anciennes_sorties = os.path.join(app, "sorties")
    if os.path.isdir(anciennes_sorties):
        os.makedirs(os.path.join(d, "sorties"), exist_ok=True)
        for nom_f in os.listdir(anciennes_sorties):
            cible = os.path.join(d, "sorties", nom_f)
            if not os.path.exists(cible):
                shutil.move(os.path.join(anciennes_sorties, nom_f), cible)
        try:
            os.rmdir(anciennes_sorties)
        except OSError:
            pass
    # modèles personnalisés : on garde ceux de l'application, qui ont pu être modifiés
    for nom_f in ("email_prospection.txt", "script_appel.txt"):
        source = os.path.join(chemins.MODELES_DEFAUT, nom_f)
        if os.path.exists(source):
            shutil.copy(source, os.path.join(d, "modeles", nom_f))
