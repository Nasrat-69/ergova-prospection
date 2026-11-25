"""Outil de prospection ERGOVA — collecte, enrichissement et export.

Exemples :
    python prospecter.py --ville Dijon --limite 200
    python prospecter.py --departement 21 --limite 2000
    python prospecter.py --ville Dijon --secteurs "BTP,Garage" --limite 100
"""
import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import config
from prospection import base, chemins, export, messages, osm, rge, sirene, statuts, web

ICI = os.path.dirname(os.path.abspath(__file__))


def formater_tel(tel):
    """« +33 3 80 12 34 56 » / « 0380123456 » -> « 03 80 12 34 56 »."""
    tel = tel.split(";")[0]
    return _format_un(tel)


def ranger_telephones(p, *sources):
    """Ajoute des numéros (séparés par « ; ») : garde le 1er numéro et le 1er mobile."""
    for src in sources:
        for t in (src or "").replace(",", ";").split(";"):
            t = _format_un(t)
            if len(re.sub(r"\D", "", t)) < 10:
                continue
            if not p.get("telephone"):
                p["telephone"] = t
            if not p.get("mobile") and statuts.est_mobile(t):
                p["mobile"] = t


def _format_un(tel):
    chiffres = re.sub(r"\D", "", tel)
    if chiffres.startswith("33") and len(chiffres) == 11:
        chiffres = "0" + chiffres[2:]
    if len(chiffres) == 10 and chiffres.startswith("0"):
        return " ".join(chiffres[i:i + 2] for i in range(0, 10, 2))
    return tel.strip()


def log(msg):
    print(msg, flush=True)


def selectionner(prospects, limite):
    """Garde les meilleurs prospects en équilibrant les secteurs."""
    par_secteur = {}
    for p in sorted(prospects, key=lambda p: p["score"], reverse=True):
        par_secteur.setdefault(p["secteur"], []).append(p)
    if not par_secteur:
        return []
    quota = max(1, limite // len(par_secteur))
    choisis = []
    for lot in par_secteur.values():
        choisis += lot[:quota]
    reste = sorted((p for p in prospects if p not in choisis), key=lambda p: p["score"], reverse=True)
    choisis += reste[: max(0, limite - len(choisis))]
    return sorted(choisis[:limite], key=lambda p: (-p["score"], p["secteur"]))


def main():
    ap = argparse.ArgumentParser(description="Prospection ERGOVA")
    zone = ap.add_mutually_exclusive_group(required=True)
    zone.add_argument("--ville", help="ex : Dijon")
    zone.add_argument("--departement", help="ex : 21")
    ap.add_argument("--limite", type=int, default=200, help="nombre de prospects à garder")
    ap.add_argument("--secteurs", help="liste séparée par des virgules (par défaut : tous les secteurs actifs)")
    ap.add_argument("--nouveaux", action="store_true", help="ignorer les entreprises déjà en base")
    args = ap.parse_args()

    if args.ville:
        code, nom_zone, dep = sirene.trouver_commune(args.ville)
        zone_api, code_osm = {"code_commune": ",".join(sirene.codes_communes(code))}, code
    else:
        nom_zone = f"Departement_{args.departement}"
        zone_api, code_osm = {"departement": args.departement}, args.departement
    log(f"\n=== Prospection ERGOVA : {nom_zone} — objectif {args.limite} prospects ===\n")

    secteurs = {k: v for k, v in config.SECTEURS.items() if v.get("actif")}
    if args.secteurs:
        voulus = [s.strip().lower() for s in args.secteurs.split(",")]
        secteurs = {k: v for k, v in config.SECTEURS.items()
                    if any(s in k.lower() for s in voulus)}

    # 1. Collecte
    log("1) Recherche des entreprises employeuses (base Sirene / INSEE)")
    tous = []
    # plafond par secteur : évite de parcourir des dizaines de milliers d'entreprises à Paris
    maximum = max(250, 4 * args.limite // max(1, len(secteurs)))
    for nom, regle in secteurs.items():
        tous += sirene.collecter_secteur(nom, regle, zone_api, maximum=maximum,
                                         log=lambda m: print(m, end="\r", flush=True))
        log("")
    vus = set()
    tous = [p for p in tous if not (p["siret"] in vus or vus.add(p["siret"]))]
    conn = base.connexion()
    if args.nouveaux:
        deja = {r[0] for r in conn.execute("SELECT siret FROM prospects")}
        tous = [p for p in tous if p["siret"] not in deja]
    log(f"   → {len(tous)} entreprises avec au moins 1 salarié trouvées\n")
    if not tous:
        sys.exit("Aucune entreprise trouvée.")

    # 2. Enrichissement OpenStreetMap
    log("2) Recherche des téléphones / sites / e-mails (OpenStreetMap)")
    for p in tous:
        p.update({"telephone": "", "mobile": "", "email": "", "site": "", "source_contact": ""})
    lats = sorted(p["latitude"] for p in tous if p["latitude"])
    lons = sorted(p["longitude"] for p in tous if p["longitude"])
    if lats:
        # on ignore les 2 % de positions extrêmes (adresses mal géolocalisées)
        k = len(lats) // 50
        bbox = (lats[k] - 0.01, lons[k] - 0.01, lats[-1 - k] + 0.01, lons[-1 - k] + 0.01)
        surface = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    else:
        bbox, surface = None, 0
    grande_zone = surface > 0.02 or len(tous) > 800  # Paris, grandes villes, départements
    if bbox and not grande_zone:
        lieux = osm.charger_osm(code_osm, bbox, log=log)
        trouves_osm = {p["siret"]: l for p in tous if (l := osm.associer(p, lieux))}
    else:
        # grande zone : on cherche seulement autour des meilleurs candidats
        for p in tous:
            messages.scorer(p)
        trouves_osm = osm.chercher_autour(selectionner(tous, args.limite * 2), log=log)
    for p in tous:
        lieu = trouves_osm.get(p["siret"])
        if lieu:
            p["site"], p["email"] = lieu["site"], lieu["email"]
            ranger_telephones(p, lieu["telephone"])
            p["source_contact"] = "OpenStreetMap"
    log(f"   → {len(trouves_osm)} entreprises trouvées sur la carte")

    # 2b. Liste RGE de l'ADEME (BTP) : correspondance exacte par SIRET
    fiches_rge = rge.charger_rge([p["code_postal"] for p in tous], log=log)
    n_rge = 0
    for p in tous:
        f = fiches_rge.get(p["siret"])
        if not f:
            continue
        n_rge += 1
        ranger_telephones(p, f["telephone"])
        p["email"] = p["email"] or f["email"]
        p["site"] = p["site"] or f["site"]
        p["source_contact"] = (p["source_contact"] + " + RGE").strip(" +")
    for p in tous:
        messages.scorer(p)
    log(f"   → {n_rge} entreprises complétées grâce à la liste RGE\n")

    # 3. Pré-sélection puis visite des sites web pour trouver les e-mails
    candidats = selectionner(tous, args.limite * 2)
    # on visite aussi les sites quand il manque un mobile
    a_visiter = [p for p in candidats if p["site"] and (not p["email"] or not p["mobile"])]
    log(f"3) Visite de {len(a_visiter)} sites web pour trouver e-mails et mobiles…")
    with ThreadPoolExecutor(max_workers=10) as pool:
        for p, res in zip(a_visiter, pool.map(lambda p: web.explorer_site(p["site"]), a_visiter)):
            if res["email"] and not p["email"]:
                p["email"] = res["email"]
                p["source_contact"] = (p["source_contact"] + " + site web").strip(" +")
            ranger_telephones(p, res["telephone"])
    for p in candidats:
        messages.scorer(p)
    log(f"   → {sum(1 for p in candidats if p['email'])} e-mails et "
        f"{sum(1 for p in candidats if p['mobile'])} mobiles trouvés\n")

    # 4. Sélection finale + sauvegarde
    finaux = selectionner(candidats, args.limite)
    for p in finaux:
        p["selectionne"] = "1"
        p["zone"] = nom_zone
    chemin_xlsx = chemins.sorties(f"prospects_{nom_zone}.xlsx")
    n = export.relire_suivi(chemin_xlsx, conn)
    if n:
        log(f"   (suivi relu depuis l'Excel existant : {n} lignes)")
    # les anciens prospects de cette zone jamais contactés sortent de la liste
    # (ceux qui ont un suivi en cours restent visibles)
    conn.execute("UPDATE prospects SET selectionne='0' WHERE zone=? AND "
                 "COALESCE(statut, ?)=? AND email_envoye_le IS NULL "
                 "AND COALESCE(notes, '')='' AND COALESCE(rappel_le, '')=''",
                 (nom_zone, statuts.DEFAUT, statuts.DEFAUT))
    base.enregistrer(conn, finaux)

    # recharge depuis la base pour récupérer statuts / notes
    sirets = [p["siret"] for p in finaux]
    lignes = {r["siret"]: dict(r) for r in conn.execute(
        f"SELECT * FROM prospects WHERE siret IN ({','.join('?' * len(sirets))})", sirets)}
    finaux = [lignes[s] for s in sirets]

    with open(chemins.modele("script_appel.txt"), encoding="utf-8") as f:
        script = f.read()
    try:
        export.ecrire(chemin_xlsx, finaux, script)
    except PermissionError:
        chemin_xlsx = chemin_xlsx.replace(".xlsx", f"_{date.today().isoformat()}.xlsx")
        export.ecrire(chemin_xlsx, finaux, script)
        log("   (l'Excel était ouvert : nouveau fichier créé)")

    tel = sum(1 for p in finaux if p["telephone"])
    mail = sum(1 for p in finaux if p["email"])
    log("=== Terminé ===")
    log(f"{len(finaux)} prospects | {tel} avec téléphone dont "
        f"{sum(1 for p in finaux if p['mobile'])} mobiles | {mail} avec e-mail | "
        f"{sum(1 for p in finaux if p['priorite'] == 'A')} en priorité A")
    log(f"Fichier : {chemin_xlsx}")


if __name__ == "__main__":
    main()
