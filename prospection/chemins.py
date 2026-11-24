"""Où sont rangés les fichiers de chaque compte.

Chaque compte a son propre dossier : donnees/comptes/<identifiant>/
    prospects.db            ses prospects, statuts et envois
    parametres_envoi.ini    son adresse Gmail et son mot de passe d'application
    desinscrits.txt         les adresses « STOP »
    modeles/                son modèle d'e-mail et son script d'appel
    sorties/                ses fichiers Excel

Le compte actif est donné :
  - dans l'interface : par la connexion (une valeur par requête) ;
  - en ligne de commande : par la variable d'environnement ERGOVA_COMPTE_DIR.
Sans compte, on utilise le dossier de l'application (ancien fonctionnement).
"""
import os
import shutil
import threading

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONNEES = os.path.join(APP, "donnees")
COMPTES = os.path.join(DONNEES, "comptes")
MODELES_DEFAUT = os.path.join(APP, "modeles")
CACHE = os.path.join(DONNEES, "cache")  # cache des cartes : commun à tous les comptes

_local = threading.local()


def utiliser(dossier):
    """Fixe le dossier du compte pour le fil d'exécution en cours."""
    _local.dossier = dossier


def racine():
    d = getattr(_local, "dossier", None) or os.environ.get("ERGOVA_COMPTE_DIR")
    return d or APP


def base_de_donnees():
    if racine() == APP:  # ancien fonctionnement, sans compte
        return os.path.join(DONNEES, "prospects.db")
    return os.path.join(racine(), "prospects.db")


def parametres():
    return os.path.join(racine(), "parametres_envoi.ini")


def desinscrits():
    return os.path.join(racine(), "desinscrits.txt")


def sorties(*morceaux):
    d = os.path.join(racine(), "sorties")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, *morceaux)


def modele(nom):
    """Modèle du compte s'il existe, sinon le modèle par défaut de l'application."""
    perso = os.path.join(racine(), "modeles", nom)
    return perso if os.path.exists(perso) else os.path.join(MODELES_DEFAUT, nom)


def modele_a_ecrire(nom):
    d = os.path.join(racine(), "modeles")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, nom)


def preparer_compte(dossier):
    """Crée le dossier d'un nouveau compte avec les modèles par défaut."""
    os.makedirs(os.path.join(dossier, "modeles"), exist_ok=True)
    os.makedirs(os.path.join(dossier, "sorties"), exist_ok=True)
    for nom in ("email_prospection.txt", "script_appel.txt"):
        cible = os.path.join(dossier, "modeles", nom)
        if not os.path.exists(cible):
            shutil.copy(os.path.join(MODELES_DEFAUT, nom), cible)
