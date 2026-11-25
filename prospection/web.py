"""Visite des sites web des entreprises pour y trouver un e-mail et un téléphone."""
import re
from urllib.parse import urljoin, urlparse

import requests

import config

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TEL_RE = re.compile(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}")
LIEN_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
MOTS_PAGES = ("contact", "mentions", "legal", "a-propos", "apropos", "qui-sommes")

EMAILS_EXCLUS = ("example.", "exemple.", "sentry", "wixpress", "domain.", "email.com",
                 "votre", "your", "nom@", "@2x", "jquery", "bootstrap", "godaddy", "ovh.net",
                 "@sentry", "noreply", "no-reply", "webmaster@wix", "user@", "jean.dupont",
                 "john.doe", "prenom.nom", "nom.prenom", "exemple@", "test@", "service.consommateurs",
                 "service-client", "serviceclient")
WEBMAILS = ("gmail.com", "orange.fr", "wanadoo.fr", "free.fr", "hotmail.fr", "hotmail.com",
            "outlook.fr", "outlook.com", "yahoo.fr", "yahoo.com", "laposte.net", "sfr.fr",
            "live.fr", "icloud.com", "neuf.fr", "bbox.fr", "aol.com", "club-internet.fr")
EXTENSIONS_IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def _telecharger(url):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": config.USER_AGENT},
                         allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", "text/html"):
            return r.text[:800_000], r.url
    except requests.RequestException:
        pass
    return "", url


def _emails(html):
    html = html.replace("[at]", "@").replace("(at)", "@").replace("&#64;", "@").replace("%40", "@")
    trouves = []
    for e in EMAIL_RE.findall(html):
        e = e.strip(".").lower()
        if e.endswith(EXTENSIONS_IMAGES) or any(x in e for x in EMAILS_EXCLUS):
            continue
        if e not in trouves:
            trouves.append(e)
    return trouves


def _meilleur_email(emails, domaine):
    # on ne garde que les e-mails du domaine du site, ou une messagerie classique
    # (évite les e-mails d'agences web cités en bas de page)
    racine = ".".join(domaine.split(".")[-2:]) if domaine else ""
    emails = [e for e in emails
              if e.split("@")[1] in WEBMAILS or (racine and e.split("@")[1].endswith(racine))]
    if not emails:
        return ""
    def note(e):
        n = 0
        if domaine and e.split("@")[1].endswith(domaine):
            n += 3
        if e.split("@")[0] in ("contact", "info", "accueil", "direction", "gerant", "secretariat"):
            n += 2
        if e.split("@")[0] in ("rgpd", "dpo", "recrutement", "jobs", "rh", "compta", "factures"):
            n -= 3
        return n
    return sorted(emails, key=note, reverse=True)[0]


def explorer_site(url):
    """Renvoie {"email": ..., "telephone": ...} trouvés sur le site (accueil + pages contact)."""
    if not url:
        return {"email": "", "telephone": ""}
    if not url.startswith("http"):
        url = "http://" + url
    html, url_finale = _telecharger(url)
    if not html:
        return {"email": "", "telephone": ""}
    domaine = urlparse(url_finale).netloc.replace("www.", "")
    emails = _emails(html)
    tels = TEL_RE.findall(html)

    pages = []
    for lien in LIEN_RE.findall(html):
        if any(m in lien.lower() for m in MOTS_PAGES):
            complet = urljoin(url_finale, lien)
            if urlparse(complet).netloc.replace("www.", "") == domaine and complet not in pages:
                pages.append(complet)
    for page in pages[:3]:
        h, _ = _telecharger(page)
        emails += [e for e in _emails(h) if e not in emails]
        tels += TEL_RE.findall(h)

    uniques = []
    for t in tels:
        if t not in uniques:
            uniques.append(t)
    return {"email": _meilleur_email(emails, domaine), "telephone": "; ".join(uniques[:6])}
