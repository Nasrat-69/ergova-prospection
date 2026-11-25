"""Envoi des e-mails de prospection ERGOVA (max 500 par jour).

    python envoyer_emails.py              -> APERÇU : rien n'est envoyé, 5 exemples dans sorties/apercus
    python envoyer_emails.py --envoyer    -> envoi réel
    python envoyer_emails.py --envoyer --max 50

Avant le premier envoi : remplis parametres_envoi.ini (créé automatiquement).
Pour bloquer quelqu'un : ajoute son e-mail dans desinscrits.txt (une adresse par ligne)
ou mets son statut à « STOP / ne plus contacter » dans l'Excel.
"""
import argparse
import configparser
import json
import os
import random
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import config
from prospection import base, chemins, export, messages, statuts

ICI = os.path.dirname(os.path.abspath(__file__))
STATUTS_BLOQUANTS = statuts.BLOQUANTS_EMAIL

MODELE_PARAMS = """[expediteur]
# Ton adresse Gmail (ou autre) qui envoie les e-mails
email = ton.adresse@gmail.com
# Mot de passe d'APPLICATION Gmail (pas ton mot de passe habituel) :
# https://myaccount.google.com/apppasswords  (la validation en 2 étapes doit être activée)
mot_de_passe_application =
prenom_nom = Prénom Nom
telephone = 06 00 00 00 00

[serveur]
smtp = smtp.gmail.com
port = 465
"""


def lire_parametres():
    if not os.path.exists(chemins.parametres()):
        with open(chemins.parametres(), "w", encoding="utf-8") as f:
            f.write(MODELE_PARAMS)
    cp = configparser.ConfigParser()
    cp.read(chemins.parametres(), encoding="utf-8")
    return cp


def verifier_mot_de_passe(email, mdp):
    """Renvoie un message d'erreur si ce n'est visiblement pas un mot de passe d'application."""
    mdp = mdp.replace(" ", "")
    if email.lower().endswith(("@gmail.com", "@googlemail.com")) and not (len(mdp) == 16 and mdp.isalpha()):
        return ("le mot de passe enregistré n'est pas un mot de passe d'application Gmail "
                f"({len(mdp)} caractères au lieu de 16 lettres). Gmail refuse ton mot de passe "
                "habituel pour les applications. Crée un mot de passe d'application sur "
                "https://myaccount.google.com/apppasswords (validation en 2 étapes obligatoire), "
                "puis colle-le dans l'onglet Réglages.")
    return ""


def connecter(srv, exp, contexte):
    """Connexion au serveur d'envoi : port 465 (SSL), puis 587 (STARTTLS) si besoin."""
    mdp = exp["mot_de_passe_application"].replace(" ", "")
    try:
        smtp = smtplib.SMTP_SSL(srv.get("smtp"), srv.getint("port", 465), context=contexte, timeout=30)
        smtp.login(exp["email"], mdp)
        return smtp
    except smtplib.SMTPAuthenticationError:
        raise
    except (smtplib.SMTPException, OSError):
        smtp = smtplib.SMTP(srv.get("smtp"), 587, timeout=30)
        smtp.starttls(context=contexte)
        smtp.login(exp["email"], mdp)
        return smtp


def lire_desinscrits():
    if not os.path.exists(chemins.desinscrits()):
        open(chemins.desinscrits(), "w", encoding="utf-8").close()
    with open(chemins.desinscrits(), encoding="utf-8") as f:
        return {l.strip().lower() for l in f if "@" in l}


def destinataires_possibles(conn, zone=None):
    """Prospects qui peuvent recevoir un e-mail : jamais contactés par e-mail, pas STOP,
    pas de statut bloquant, une seule fois par adresse. Triés par score."""
    deja = {r[0].lower() for r in conn.execute("SELECT email FROM envois")}
    bloques = lire_desinscrits()
    sql = ("SELECT * FROM prospects WHERE selectionne='1' AND email!='' AND email IS NOT NULL")
    params = []
    if zone:
        sql += " AND zone=?"
        params.append(zone)
    res, vus = [], set()
    for r in conn.execute(sql + " ORDER BY CAST(score AS INTEGER) DESC", params):
        p = dict(r)
        mail = p["email"].lower()
        if mail in deja or mail in bloques or mail in vus or p["statut"] in STATUTS_BLOQUANTS:
            continue
        vus.add(mail)  # une seule fois par adresse (plusieurs magasins = même e-mail)
        res.append(p)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envoyer", action="store_true", help="envoi réel (sinon simple aperçu)")
    ap.add_argument("--max", type=int, default=config.EMAILS_PAR_JOUR_MAX)
    ap.add_argument("--selection", help="fichier JSON : liste des SIRET choisis")
    args = ap.parse_args()

    cp = lire_parametres()
    exp = cp["expediteur"]
    signature = {"prenom_nom": exp.get("prenom_nom", ""), "telephone": exp.get("telephone", "")}

    conn = base.connexion()
    # on relit d'abord les statuts saisis dans les fichiers Excel
    dossier_sorties = chemins.sorties()
    if os.path.isdir(dossier_sorties):
        for nom in os.listdir(dossier_sorties):
            if nom.endswith(".xlsx") and not nom.startswith("~$"):
                export.relire_suivi(os.path.join(dossier_sorties, nom), conn)

    a_envoyer = destinataires_possibles(conn)
    if args.selection:
        # uniquement les prospects cochés dans l'application
        with open(args.selection, encoding="utf-8") as f:
            choisis = set(json.load(f))
        a_envoyer = [p for p in a_envoyer if p["siret"] in choisis]
        args.max = min(args.max, len(a_envoyer))

    restant = config.EMAILS_PAR_JOUR_MAX - base.envois_aujourdhui(conn)
    lot = a_envoyer[: max(0, min(args.max, restant))]
    print(f"{len(a_envoyer)} e-mails prêts | déjà envoyés aujourd'hui : "
          f"{config.EMAILS_PAR_JOUR_MAX - restant} | ce lot : {len(lot)}")

    if not args.envoyer:
        dossier = chemins.sorties("apercus")
        os.makedirs(dossier, exist_ok=True)
        for p in lot[:5]:
            objet, corps = messages.email_prospection(p, signature)
            nom = "".join(c for c in p["entreprise"] if c.isalnum() or c in " -")[:40]
            with open(os.path.join(dossier, f"{nom}.txt"), "w", encoding="utf-8") as f:
                f.write(f"À : {p['email']}\nObjet : {objet}\n\n{corps}\n")
        print(f"APERÇU uniquement : 5 exemples écrits dans {dossier}")
        print("Pour envoyer pour de vrai : python envoyer_emails.py --envoyer")
        return

    if not exp.get("mot_de_passe_application") or "ton.adresse" in exp.get("email", ""):
        sys.exit(f"Remplis d'abord {chemins.parametres()} (adresse + mot de passe d'application).")
    probleme = verifier_mot_de_passe(exp.get("email", ""), exp["mot_de_passe_application"])
    if probleme:
        sys.exit("ERREUR : " + probleme)
    if not lot:
        sys.exit("Aucun e-mail à envoyer.")

    srv = cp["serveur"]
    contexte = ssl.create_default_context()
    try:
        smtp = connecter(srv, exp, contexte)
    except smtplib.SMTPAuthenticationError:
        sys.exit("ERREUR : Gmail refuse l'adresse ou le mot de passe d'application. "
                 "Vérifie l'adresse et recrée un mot de passe d'application sur "
                 "https://myaccount.google.com/apppasswords")
    except (smtplib.SMTPException, OSError) as e:
        sys.exit(f"ERREUR : connexion à Gmail impossible ({e}). Vérifie ta connexion Internet "
                 "et que ton antivirus ne bloque pas l'envoi d'e-mails.")
    envoyes = 0
    try:
        for i, p in enumerate(lot, 1):
            objet, corps = messages.email_prospection(p, signature)
            msg = EmailMessage()
            msg["From"] = formataddr((f"{signature['prenom_nom']} — ERGOVA", exp["email"]))
            msg["To"] = p["email"]
            msg["Subject"] = objet
            msg["Message-ID"] = make_msgid()
            msg["List-Unsubscribe"] = f"<mailto:{exp['email']}?subject=STOP>"
            msg.set_content(corps)
            try:
                smtp.send_message(msg)
            except smtplib.SMTPServerDisconnected:
                smtp = connecter(srv, exp, contexte)
                smtp.send_message(msg)
            except smtplib.SMTPRecipientsRefused:
                print(f"  [{i}/{len(lot)}] adresse refusée : {p['email']}")
                continue
            base.noter_envoi(conn, p["siret"], p["email"], objet)
            envoyes += 1
            print(f"  [{i}/{len(lot)}] envoyé à {p['entreprise']} <{p['email']}>", flush=True)
            if i < len(lot):
                time.sleep(random.uniform(*config.PAUSE_ENTRE_EMAILS_SECONDES))
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    finally:
        smtp.quit()
    print(f"Terminé : {envoyes} e-mails envoyés.")


if __name__ == "__main__":
    main()
