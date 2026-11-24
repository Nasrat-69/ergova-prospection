"""Base de données locale (SQLite) : garde tous les prospects, leurs statuts
et l'historique des e-mails envoyés, d'une exécution à l'autre."""
import os
import sqlite3
from datetime import date, datetime

from . import chemins


COLONNES = [
    "siret", "siren", "entreprise", "raison_sociale", "enseignes", "secteur", "naf",
    "tranche", "effectif", "dirigeant", "qualite_dirigeant", "adresse", "code_postal",
    "ville", "latitude", "longitude", "date_creation", "nb_etablissements_entreprise",
    "telephone", "email", "site", "source_contact", "score", "priorite", "zone",
]
SUIVI = ["statut", "rappel_le", "notes", "email_envoye_le", "selectionne", "suivi_maj_le"]


def connexion():
    fichier = chemins.base_de_donnees()
    os.makedirs(os.path.dirname(fichier), exist_ok=True)
    c = sqlite3.connect(fichier)
    c.row_factory = sqlite3.Row
    cols = ", ".join(f"{k} TEXT" for k in COLONNES[1:] + SUIVI)
    c.execute(f"CREATE TABLE IF NOT EXISTS prospects (siret TEXT PRIMARY KEY, {cols}, maj_le TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS envois (siret TEXT, email TEXT, envoye_le TEXT, objet TEXT)")
    # mise à niveau des anciennes bases
    existantes = {r[1] for r in c.execute("PRAGMA table_info(prospects)")}
    for col in COLONNES[1:] + SUIVI:
        if col not in existantes:
            c.execute(f"ALTER TABLE prospects ADD COLUMN {col} TEXT")
    c.commit()
    return c


def enregistrer(c, prospects):
    """Ajoute ou met à jour les prospects sans écraser le suivi (statut, notes…)."""
    maintenant = datetime.now().isoformat(timespec="seconds")
    for p in prospects:
        valeurs = [p.get(k) for k in COLONNES]
        maj = ", ".join(f"{k}=excluded.{k}" for k in COLONNES[1:])
        c.execute(
            f"INSERT INTO prospects ({', '.join(COLONNES)}, statut, selectionne, maj_le) "
            f"VALUES ({', '.join('?' * len(COLONNES))}, 'À contacter', ?, ?) "
            f"ON CONFLICT(siret) DO UPDATE SET {maj}, selectionne=excluded.selectionne, maj_le=excluded.maj_le",
            valeurs + [p.get("selectionne", "1"), maintenant],
        )
    c.commit()


def mettre_a_jour_suivi(c, siret, **champs):
    if not champs:
        return
    sets = ", ".join(f"{k}=?" for k in champs)
    c.execute(f"UPDATE prospects SET {sets} WHERE siret=?", list(champs.values()) + [siret])
    c.commit()


def envois_aujourdhui(c):
    return c.execute("SELECT COUNT(*) FROM envois WHERE envoye_le LIKE ?",
                     (date.today().isoformat() + "%",)).fetchone()[0]


def noter_envoi(c, siret, email, objet):
    maintenant = datetime.now().isoformat(timespec="seconds")
    c.execute("INSERT INTO envois VALUES (?, ?, ?, ?)", (siret, email, maintenant, objet))
    c.execute("UPDATE prospects SET email_envoye_le=?, statut=CASE WHEN statut='À contacter' "
              "THEN 'E-mail envoyé' ELSE statut END WHERE siret=?", (maintenant, siret))
    c.commit()
