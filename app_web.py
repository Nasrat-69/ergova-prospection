"""Interface graphique de l'outil de prospection ERGOVA.

Lance un petit serveur local (uniquement sur ce PC) et ouvre le navigateur :
    python app_web.py
Puis http://127.0.0.1:8765
"""
import configparser
import http.cookies
import json
import secrets
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import config
import envoyer_emails
from prospection import base, chemins, comptes, export, messages, statuts

ICI = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
COOKIE = "ergova_session"
SESSIONS = {}  # jeton -> identifiant du compte (en mémoire : reconnexion après redémarrage)

# ---------------------------------------------------------------------------
# Tâche en arrière-plan (recherche ou envoi) : une seule à la fois
# ---------------------------------------------------------------------------
TACHE = {"type": None, "en_cours": False, "lignes": [], "code": None, "debut": None,
         "fichier": None, "zone": None, "compte": None}
VERROU = threading.Lock()


def lancer_tache(type_, args, compte, zone=None):
    with VERROU:
        if TACHE["en_cours"]:
            return False
        TACHE.update(type=type_, en_cours=True, lignes=[], code=None, fichier=None, zone=zone,
                     compte=compte, debut=datetime.now().isoformat(timespec="seconds"))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
               ERGOVA_COMPTE_DIR=comptes.dossier(compte))

    def tourner():
        proc = subprocess.Popen([sys.executable, "-u"] + args, cwd=ICI, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tampon = ""
        while True:
            morceau = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
            if not morceau:
                break
            tampon += morceau.decode("utf-8", "replace")
            while re.search(r"[\r\n]", tampon):
                m = re.search(r"[\r\n]", tampon)
                ligne, sep, tampon = tampon[:m.start()], m.group(), tampon[m.end():]
                ligne = ligne.rstrip()
                if not ligne:
                    continue
                with VERROU:
                    # une ligne de progression « page x/y » remplace la précédente
                    # (même secteur uniquement)
                    if TACHE["lignes"] and re.search(r"page \d+/\d+", ligne) and \
                            re.search(r"page \d+/\d+", TACHE["lignes"][-1]) and \
                            ligne.split(" : page")[0] == TACHE["lignes"][-1].split(" : page")[0]:
                        TACHE["lignes"][-1] = ligne
                    else:
                        TACHE["lignes"].append(ligne)
                    if ligne.startswith("Fichier :"):
                        TACHE["fichier"] = ligne.split(":", 1)[1].strip()
        proc.wait()
        with VERROU:
            TACHE.update(en_cours=False, code=proc.returncode)

    threading.Thread(target=tourner, daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
def prospects(zone=None):
    conn = base.connexion()
    sql = "SELECT * FROM prospects WHERE selectionne='1'"
    params = []
    if zone:
        sql += " AND zone=?"
        params.append(zone)
    lignes = [dict(r) for r in conn.execute(sql + " ORDER BY CAST(score AS INTEGER) DESC", params)]
    conn.close()
    for p in lignes:
        p["accroche"] = messages.accroche_appel(p)
    return lignes


def zones():
    conn = base.connexion()
    res = [{"zone": r[0], "nb": r[1], "maj": r[2]} for r in conn.execute(
        "SELECT zone, COUNT(*), MAX(maj_le) FROM prospects WHERE selectionne='1' AND zone IS NOT NULL "
        "GROUP BY zone ORDER BY MAX(maj_le) DESC")]
    conn.close()
    return res


def stats_envois():
    conn = base.connexion()
    aujourdhui = base.envois_aujourdhui(conn)
    total = conn.execute("SELECT COUNT(*) FROM envois").fetchone()[0]
    prets = len(envoyer_emails.destinataires_possibles(conn))
    derniers = [dict(siret=r[0], email=r[1], envoye_le=r[2], objet=r[3]) for r in conn.execute(
        "SELECT * FROM envois ORDER BY envoye_le DESC LIMIT 50")]
    conn.close()
    return {"aujourdhui": aujourdhui, "total": total, "prets": prets,
            "max_jour": config.EMAILS_PAR_JOUR_MAX, "derniers": derniers}


def lire_parametres():
    cp = configparser.ConfigParser()
    if os.path.exists(chemins.parametres()):
        cp.read(chemins.parametres(), encoding="utf-8")
    e = cp["expediteur"] if cp.has_section("expediteur") else {}
    return {
        "email": e.get("email", "") if "ton.adresse" not in e.get("email", "") else "",
        "prenom_nom": e.get("prenom_nom", "") if e.get("prenom_nom", "") != "Prénom Nom" else "",
        "telephone": e.get("telephone", "") if e.get("telephone", "") != "06 00 00 00 00" else "",
        "mot_de_passe_defini": bool(e.get("mot_de_passe_application", "")),
        "probleme_mot_de_passe": envoyer_emails.verifier_mot_de_passe(
            e.get("email", ""), e.get("mot_de_passe_application", "")) if e.get("mot_de_passe_application") else "",
    }


def ecrire_parametres(d):
    cp = configparser.ConfigParser()
    if os.path.exists(chemins.parametres()):
        cp.read(chemins.parametres(), encoding="utf-8")
    if not cp.has_section("expediteur"):
        cp.add_section("expediteur")
    if not cp.has_section("serveur"):
        cp.add_section("serveur")
        cp["serveur"]["smtp"] = "smtp.gmail.com"
        cp["serveur"]["port"] = "465"
    for cle in ("email", "prenom_nom", "telephone"):
        if cle in d:
            cp["expediteur"][cle] = d[cle].strip()
    if d.get("mot_de_passe_application"):
        cp["expediteur"]["mot_de_passe_application"] = d["mot_de_passe_application"].replace(" ", "")
    with open(chemins.parametres(), "w", encoding="utf-8") as f:
        cp.write(f)


def signature():
    p = lire_parametres()
    return {"prenom_nom": p["prenom_nom"] or "[Prénom Nom]", "telephone": p["telephone"] or "[téléphone]"}


def exporter_excel(zone):
    lignes = prospects(zone)
    with open(chemins.modele("script_appel.txt"), encoding="utf-8") as f:
        script = f.read()
    chemin = chemins.sorties(f"prospects_{zone}.xlsx")
    try:
        export.ecrire(chemin, lignes, script)
    except PermissionError:
        chemin = chemin.replace(".xlsx", f"_{datetime.now():%Y-%m-%d_%Hh%M}.xlsx")
        export.ecrire(chemin, lignes, script)
    return chemin


# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------
class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, data, code=200):
        corps = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _corps(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _origine_locale(self):
        # protège contre les requêtes envoyées par d'autres sites web
        origine = self.headers.get("Origin")
        return origine in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    # ------------------------------------------------------------- comptes
    def _jeton(self):
        c = http.cookies.SimpleCookie(self.headers.get("Cookie") or "")
        return c[COOKIE].value if COOKIE in c else None

    def _identifier(self):
        """Fixe le compte de la requête ; renvoie False si personne n'est connecté."""
        self.compte = SESSIONS.get(self._jeton() or "")
        chemins.utiliser(comptes.dossier(self.compte) if self.compte else None)
        return bool(self.compte)

    def _ouvrir_session(self, ident):
        jeton = secrets.token_urlsafe(32)
        SESSIONS[jeton] = ident
        corps = json.dumps({"ok": True, "nom": comptes.nom(ident)}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", f"{COOKIE}={jeton}; HttpOnly; SameSite=Strict; Path=/")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        chemin = url.path
        connecte = self._identifier()
        if chemin == "/api/session":
            return self._json({"connecte": connecte, "identifiant": self.compte,
                               "nom": comptes.nom(self.compte) if connecte else None,
                               "comptes_existent": comptes.existe_au_moins_un()})
        if chemin.startswith("/api/") and not connecte:
            return self._json({"erreur": "Connecte-toi d'abord.", "connexion": True}, 401)
        if chemin in ("/", "/index.html"):
            with open(os.path.join(ICI, "interface", "index.html"), "rb") as f:
                corps = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
        elif chemin == "/api/etat":
            self._json({
                "compte": {"identifiant": self.compte, "nom": comptes.nom(self.compte)},
                "secteurs": [{"nom": k, "actif": v.get("actif", False)} for k, v in config.SECTEURS.items()],
                "zones": zones(), "statuts": statuts.LISTE, "couleurs_statuts": statuts.COULEURS,
                "statut_defaut": statuts.DEFAUT, "statuts_termines": sorted(statuts.TERMINES),
                "parametres": lire_parametres(), "envois": stats_envois(),
            })
        elif chemin == "/api/prospects":
            self._json(prospects(q.get("zone")))
        elif chemin == "/api/destinataires":
            conn = base.connexion()
            liste = envoyer_emails.destinataires_possibles(conn, q.get("zone") or None)
            conn.close()
            cles = ("siret", "entreprise", "secteur", "email", "dirigeant", "priorite", "zone", "statut", "effectif")
            self._json([{k: p.get(k) for k in cles} for p in liste])
        elif chemin == "/api/tache":
            with VERROU:
                if TACHE["compte"] == self.compte:
                    self._json(dict(TACHE, lignes=TACHE["lignes"][-300:]))
                else:  # la tâche d'un autre compte reste privée
                    self._json({"type": None, "en_cours": False, "autre_en_cours": TACHE["en_cours"]})
        elif chemin == "/api/apercu":
            conn = base.connexion()
            r = conn.execute("SELECT * FROM prospects WHERE siret=?", (q.get("siret"),)).fetchone()
            conn.close()
            if not r:
                return self._json({"erreur": "introuvable"}, 404)
            objet, corps = messages.email_prospection(dict(r), signature())
            self._json({"a": r["email"], "objet": objet, "corps": corps})
        elif chemin == "/api/modeles":
            with open(chemins.modele("email_prospection.txt"), encoding="utf-8") as f:
                email = f.read()
            with open(chemins.modele("script_appel.txt"), encoding="utf-8") as f:
                script = f.read()
            self._json({"email": email, "script": script})
        elif chemin == "/api/telecharger":
            zone = q.get("zone") or ""
            if not zone:
                return self._json({"erreur": "zone manquante"}, 400)
            try:
                fichier = exporter_excel(zone)  # toujours à jour avec les derniers statuts
                with open(fichier, "rb") as f:
                    corps = f.read()
            except Exception as e:
                return self._json({"erreur": f"Création de l'Excel impossible : {e}"}, 500)
            nom = f"prospects_{zone}_{date.today():%Y-%m-%d}.xlsx"
            nom_ascii = "".join(c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in nom)
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition",
                             f"attachment; filename=\"{nom_ascii}\"; filename*=UTF-8''{quote(nom)}")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corps)
        else:
            self._json({"erreur": "inconnu"}, 404)

    def do_POST(self):
        if not self._origine_locale():
            return self._json({"erreur": "origine refusée"}, 403)
        chemin = urlparse(self.path).path
        d = self._corps()
        connecte = self._identifier()
        if chemin == "/api/connexion":
            ident = comptes.verifier(d.get("identifiant"), d.get("mot_de_passe"))
            if not ident:
                return self._json({"erreur": "Identifiant ou mot de passe incorrect."}, 401)
            return self._ouvrir_session(ident)
        if chemin == "/api/inscription":
            try:
                ident = comptes.creer(d.get("identifiant"), d.get("nom"), d.get("mot_de_passe"))
            except ValueError as e:
                return self._json({"erreur": str(e)}, 400)
            return self._ouvrir_session(ident)
        if chemin == "/api/deconnexion":
            SESSIONS.pop(self._jeton() or "", None)
            return self._json({"ok": True})
        if not connecte:
            return self._json({"erreur": "Connecte-toi d'abord.", "connexion": True}, 401)
        if chemin == "/api/mot_de_passe":
            try:
                comptes.changer_mot_de_passe(self.compte, d.get("ancien"), d.get("nouveau"))
            except ValueError as e:
                return self._json({"erreur": str(e)}, 400)
            return self._json({"ok": True})
        if chemin == "/api/rechercher":
            ville = (d.get("ville") or "").strip()
            dep = (d.get("departement") or "").strip()
            if not ville and not dep:
                return self._json({"erreur": "Indique une ville ou un département."}, 400)
            args = ["prospecter.py"] + (["--ville", ville] if ville else ["--departement", dep])
            args += ["--limite", str(int(d.get("limite") or 200))]
            if d.get("secteurs"):
                args += ["--secteurs", ",".join(d["secteurs"])]
            if d.get("nouveaux"):
                args.append("--nouveaux")
            ok = lancer_tache("recherche", args, self.compte, zone=ville or f"Departement_{dep}")
            self._json({"ok": ok} if ok else {"erreur": "Une tâche est déjà en cours."}, 200 if ok else 409)
        elif chemin == "/api/suivi":
            champs = {k: d[k] for k in ("statut", "rappel_le", "notes") if k in d}
            champs["suivi_maj_le"] = datetime.now().isoformat(timespec="seconds")
            conn = base.connexion()
            base.mettre_a_jour_suivi(conn, d["siret"], **champs)
            if d.get("statut") == "STOP / ne plus contacter":
                r = conn.execute("SELECT email FROM prospects WHERE siret=?", (d["siret"],)).fetchone()
                if r and r[0]:
                    with open(chemins.desinscrits(), "a", encoding="utf-8") as f:
                        f.write(r[0].lower() + "\n")
            conn.close()
            self._json({"ok": True})
        elif chemin == "/api/envoyer":
            p = lire_parametres()
            if not (p["email"] and p["mot_de_passe_defini"] and p["prenom_nom"]):
                return self._json({"erreur": "Remplis d'abord l'onglet Réglages (adresse, nom, mot de passe d'application)."}, 400)
            if p["probleme_mot_de_passe"]:
                return self._json({"erreur": "Mot de passe : " + p["probleme_mot_de_passe"]}, 400)
            sirets = [str(s) for s in d.get("sirets") or []]
            if not sirets:
                return self._json({"erreur": "Coche au moins un destinataire."}, 400)
            stats = stats_envois()
            reste = stats["max_jour"] - stats["aujourdhui"]
            if len(sirets) > reste:
                return self._json({"erreur": f"Limite du jour : il reste {reste} e-mail(s) possibles aujourd'hui."}, 400)
            fichier = os.path.join(chemins.racine(), "selection_envoi.json")
            with open(fichier, "w", encoding="utf-8") as f:
                json.dump(sirets, f)
            ok = lancer_tache("envoi", ["envoyer_emails.py", "--envoyer", "--max", str(len(sirets)),
                                        "--selection", fichier], self.compte)
            self._json({"ok": ok} if ok else {"erreur": "Une tâche est déjà en cours."}, 200 if ok else 409)
        elif chemin == "/api/parametres":
            mdp = (d.get("mot_de_passe_application") or "").strip()
            if mdp:
                probleme = envoyer_emails.verifier_mot_de_passe(d.get("email", ""), mdp)
                if probleme:
                    return self._json({"erreur": "Ce n'est pas un mot de passe d'application : il doit faire 16 lettres (ex : abcd efgh ijkl mnop). Crée-le sur myaccount.google.com/apppasswords."}, 400)
            ecrire_parametres(d)
            self._json({"ok": True, "parametres": lire_parametres()})
        elif chemin == "/api/modeles":
            if "email" in d:
                if not d["email"].lstrip().lower().startswith("objet"):
                    return self._json({"erreur": "La 1re ligne doit commencer par « Objet: »."}, 400)
                try:
                    test = {"entreprise": "X", "bonjour": "Bonjour,", "du_secteur": "du bâtiment",
                            "effectif": "", "ville": "", "prenom_nom": "", "telephone": ""}
                    d["email"].format(**test)
                except (KeyError, IndexError, ValueError) as e:
                    return self._json({"erreur": f"Variable inconnue dans le modèle : {e}"}, 400)
                with open(chemins.modele_a_ecrire("email_prospection.txt"), "w", encoding="utf-8") as f:
                    f.write(d["email"])
            if "script" in d:
                with open(chemins.modele_a_ecrire("script_appel.txt"), "w", encoding="utf-8") as f:
                    f.write(d["script"])
            self._json({"ok": True})
        elif chemin == "/api/excel":
            chemin_x = exporter_excel(d["zone"])
            os.startfile(chemin_x)
            self._json({"ok": True, "fichier": chemin_x})
        elif chemin == "/api/ouvrir":
            cible = {"sorties": chemins.sorties(), "dossier": chemins.racine()}.get(d.get("quoi"))
            if cible:
                os.makedirs(cible, exist_ok=True)
                os.startfile(cible)
            self._json({"ok": True})
        else:
            self._json({"erreur": "inconnu"}, 404)


def main():
    serveur = ThreadingHTTPServer(("127.0.0.1", PORT), Gestionnaire)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Application ERGOVA ouverte sur {url}")
    print("Laisse cette fenêtre ouverte pendant que tu utilises l'application.")
    print("Pour arrêter : ferme cette fenêtre.")
    if "--sans-navigateur" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
