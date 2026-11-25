"""Fichier Excel de travail : liste d'appels, suivi, script, statistiques.

Les colonnes « Statut », « Rappel le » et « Notes » que tu remplis dans Excel
sont relues à chaque nouvelle exécution, donc rien n'est perdu.
"""
import os
from datetime import datetime
from collections import Counter

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation

from . import base, messages, statuts

STATUTS = statuts.LISTE

COLONNES = [  # (titre, clé ou fonction, largeur)
    ("Priorité", "priorite", 9),
    ("Score", "score", 7),
    ("Entreprise", "entreprise", 30),
    ("Secteur", "secteur", 20),
    ("Effectif", "effectif", 15),
    ("Dirigeant", "dirigeant", 22),
    ("Mobile", "mobile", 16),
    ("Téléphone", "telephone", 16),
    ("E-mail", "email", 30),
    ("Site web", "site", 28),
    ("Adresse", "adresse", 40),
    ("Statut de l'appel", lambda p: p.get("statut") or statuts.DEFAUT, 24),
    ("Remarque", "notes", 45),
    ("Rappel le", "rappel_le", 12),
    ("E-mail envoyé le", "email_envoye_le", 18),
    ("Accroche d'appel", lambda p: messages.accroche_appel(p), 70),
    ("Raison sociale", "raison_sociale", 30),
    ("Code NAF", "naf", 9),
    ("SIRET", "siret", 16),
    ("Source du contact", "source_contact", 16),
]
COULEURS = {"A": "C6EFCE", "B": "FFEB9C", "C": "F2F2F2"}


def relire_suivi(chemin, conn):
    """Recopie dans la base ce que l'utilisateur a saisi dans Excel."""
    if not os.path.exists(chemin):
        return 0
    try:
        wb = load_workbook(chemin, read_only=True)
    except Exception:
        return 0
    if "Prospects" not in wb.sheetnames:
        return 0
    ws = wb["Prospects"]
    lignes = ws.iter_rows(values_only=True)
    entetes = list(next(lignes))
    alias = {"Statut de l'appel": "Statut", "Remarque": "Notes"}
    entetes = [alias.get(e, e) for e in entetes]
    idx = {t: entetes.index(t) for t in ("SIRET", "Statut", "Rappel le", "Notes") if t in entetes}
    if "SIRET" not in idx:
        return 0
    # une modification faite dans l'interface après le dernier enregistrement de l'Excel
    # est plus récente : on ne l'écrase pas
    date_excel = datetime.fromtimestamp(os.path.getmtime(chemin)).isoformat(timespec="seconds")
    recents = {r[0] for r in conn.execute(
        "SELECT siret FROM prospects WHERE suivi_maj_le > ?", (date_excel,))}
    n = 0
    for ligne in lignes:
        siret = ligne[idx["SIRET"]]
        if not siret or str(siret) in recents:
            continue
        champs = {}
        for titre, cle in (("Statut", "statut"), ("Rappel le", "rappel_le"), ("Notes", "notes")):
            if titre in idx and ligne[idx[titre]] not in (None, ""):
                champs[cle] = str(ligne[idx[titre]])
        base.mettre_a_jour_suivi(conn, str(siret), **champs)
        n += 1
    wb.close()
    return n


def ecrire(chemin, prospects, script_appel):
    wb = Workbook()
    ws = wb.active
    ws.title = "Prospects"
    ws.append([c[0] for c in COLONNES])
    for p in prospects:
        ligne = []
        for _, cle, _ in COLONNES:
            v = cle(p) if callable(cle) else p.get(cle)
            ligne.append(v if v not in (None,) else "")
        ws.append(ligne)

    entete_fill = PatternFill("solid", fgColor="1F3864")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = entete_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    titres = [c[0] for c in COLONNES]
    col_tel = titres.index("Téléphone") + 1
    col_mob = titres.index("Mobile") + 1
    col_site = titres.index("Site web") + 1
    col_mail = titres.index("E-mail") + 1
    for i, p in enumerate(prospects, start=2):
        fill = PatternFill("solid", fgColor=COULEURS.get(p.get("priorite"), "FFFFFF"))
        ws.cell(i, 1).fill = fill
        if p.get("telephone"):
            ws.cell(i, col_tel).hyperlink = "tel:" + p["telephone"].replace(" ", "")
        if p.get("mobile"):
            ws.cell(i, col_mob).hyperlink = "tel:" + p["mobile"].replace(" ", "")
            ws.cell(i, col_mob).font = Font(bold=True, color="0A53A8")
        if p.get("site"):
            s = p["site"] if p["site"].startswith("http") else "http://" + p["site"]
            ws.cell(i, col_site).hyperlink = s
        if p.get("email"):
            ws.cell(i, col_mail).hyperlink = "mailto:" + p["email"]
    for j, (_, _, largeur) in enumerate(COLONNES, start=1):
        ws.column_dimensions[get_column_letter(j)].width = largeur
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions

    col_statut = get_column_letter(titres.index("Statut de l'appel") + 1)
    derniere = max(len(prospects) + 1, 2)
    plage = f"{col_statut}2:{col_statut}{derniere}"
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUTS) + '"', allow_blank=True,
                        showErrorMessage=True, errorTitle="Statut inconnu",
                        error="Choisis un statut dans la liste.")
    ws.add_data_validation(dv)
    dv.add(plage)
    # une couleur par statut, comme dans l'application (suit les changements faits dans Excel)
    for nom, (fond, texte) in statuts.COULEURS.items():
        ws.conditional_formatting.add(plage, FormulaRule(
            formula=[f'{col_statut}2="{nom}"'], stopIfTrue=True,
            fill=PatternFill("solid", fgColor=fond, bgColor=fond),
            font=Font(color=texte, bold=True)))
    # onglet « Mobiles » : uniquement les prospects avec un 06 / 07
    mob = wb.create_sheet("Mobiles", 1)
    mob.append(["Priorité", "Entreprise", "Secteur", "Dirigeant", "Mobile", "Statut de l'appel", "Remarque", "SIRET"])
    for p in [p for p in prospects if p.get("mobile")]:
        mob.append([p.get("priorite"), p.get("entreprise"), p.get("secteur"), p.get("dirigeant"),
                    p.get("mobile"), p.get("statut") or statuts.DEFAUT, p.get("notes") or "", p.get("siret")])
    for cell in mob[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = entete_fill
    for col, w in zip("ABCDEFGH", (9, 32, 22, 24, 16, 24, 40, 16)):
        mob.column_dimensions[col].width = w
    mob.freeze_panes = "B2"
    mob.auto_filter.ref = mob.dimensions

    # --- Statistiques ---
    st = wb.create_sheet("Statistiques")
    st.append(["Secteur", "Prospects", "Avec téléphone", "Avec e-mail", "Priorité A"])
    par_secteur = Counter(p["secteur"] for p in prospects)
    for sect, n in par_secteur.most_common():
        lot = [p for p in prospects if p["secteur"] == sect]
        st.append([sect, n, sum(1 for p in lot if p.get("telephone")),
                   sum(1 for p in lot if p.get("email")),
                   sum(1 for p in lot if p.get("priorite") == "A")])
    st.append(["TOTAL", len(prospects), sum(1 for p in prospects if p.get("telephone")),
               sum(1 for p in prospects if p.get("email")),
               sum(1 for p in prospects if p.get("priorite") == "A")])
    for cell in st[1] + st[st.max_row]:
        cell.font = Font(bold=True)
    for col, w in zip("ABCDE", (28, 12, 16, 14, 12)):
        st.column_dimensions[col].width = w

    # --- Script d'appel ---
    sc = wb.create_sheet("Script d'appel")
    sc.column_dimensions["A"].width = 120
    for ligne in script_appel.splitlines():
        sc.append([ligne])
        c = sc.cell(sc.max_row, 1)
        c.alignment = Alignment(wrap_text=True)
        if ligne.isupper() or ligne.startswith("#"):
            c.font = Font(bold=True, size=12)

    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    wb.save(chemin)
