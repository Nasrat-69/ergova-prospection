# ERGOVA Prospection

Logiciel gratuit qui trouve les entreprises **avec au moins 1 salarié** dans une ville ou un département
(BTP, transport, industrie, supérettes, fleuristes, garages, boulangeries-pâtisseries, boucheries),
retrouve leur **téléphone et leur e-mail** quand ils sont publics, et aide à les contacter :
liste d'appels priorisée, fiche par entreprise, suivi des appels, envoi d'e-mails et export Excel.

Tout tourne **sur ton propre PC**. Chaque personne a **son compte** : ses prospects, son Gmail et son suivi.

---

## Installation (une seule fois, environ 5 minutes)

1. **Installe Python** : https://www.python.org/downloads/
   Pendant l'installation, **coche la case « Add python.exe to PATH »**.
2. **Télécharge le logiciel** : sur cette page GitHub, bouton vert **Code**, puis **Download ZIP**.
   Fais un clic droit sur le fichier ZIP, choisis **Extraire tout…**, puis range le dossier où tu veux (par exemple dans Documents).
3. Dans le dossier, **double-clique sur `Ouvrir_l_application.bat`**.
   Au premier lancement, les modules nécessaires s'installent tout seuls (environ 1 minute).

L'application s'ouvre dans ton navigateur à l'adresse http://127.0.0.1:8765.
**Laisse la fenêtre noire ouverte** pendant que tu l'utilises, et ferme-la pour arrêter.

> Si Windows affiche « Windows a protégé votre ordinateur », clique sur **Informations complémentaires**, puis **Exécuter quand même**.

## Premier lancement : crée ton compte

Choisis un identifiant (par exemple `karim`) et un mot de passe pour l'application.
Ce n'est **pas** ton mot de passe Gmail. D'autres personnes peuvent créer leur compte sur le même PC :
chacun ne voit que ses propres données.

## Utilisation

| Onglet | Ce qu'on y fait |
|---|---|
| **Rechercher** | Ville ou département, nombre de prospects, secteurs, puis « Lancer ». Environ 2 à 6 minutes pour une ville moyenne. |
| **Prospects** | Tableau filtrable. Un clic sur une entreprise ouvre sa fiche : appeler, accroche, statut, rappel, notes. Bouton **Télécharger l'Excel**. |
| **E-mails** | Coche les destinataires et envoie. Jamais deux e-mails à la même adresse, et les « STOP » sont exclus. |
| **Réglages** | Ton nom, ton téléphone, ton Gmail d'envoi, ton script d'appel et le mot de passe de ton compte. |

## Envoyer des e-mails avec Gmail

Gmail refuse ton mot de passe habituel pour les applications. Il te faut un **mot de passe d'application** :

1. Active la **validation en 2 étapes** : https://myaccount.google.com/signinoptions/twosv
2. Crée un mot de passe d'application : https://myaccount.google.com/apppasswords
   (Google affiche 16 lettres, du type `abcd efgh ijkl mnop`.)
3. Colle-le dans l'onglet **Réglages**.

**Conseil** : commence par 20 à 50 e-mails par jour, puis augmente doucement (500 par jour au maximum).
Envoyer beaucoup d'e-mails dès le premier jour fait bloquer le compte Gmail.

## Mettre à jour le logiciel

Télécharge à nouveau le ZIP et remplace les fichiers du dossier, **sauf le dossier `donnees`**.
C'est là que sont tes comptes et tes prospects.

## D'où viennent les données ? (100 % gratuit et public)

1. **Base Sirene de l'INSEE** (API Recherche d'entreprises) : entreprises, effectif, dirigeant.
2. **Liste RGE de l'ADEME** : téléphone et e-mail des artisans du bâtiment.
3. **OpenStreetMap** : téléphone et site web des commerces.
4. **Sites web des entreprises** : e-mail de contact.

## Confidentialité

- Tout reste sur ton PC : rien n'est envoyé ailleurs, sauf les e-mails que tu choisis d'envoyer.
- Les mots de passe des comptes sont enregistrés sous forme chiffrée (empreinte PBKDF2), jamais en clair.
- Le dossier `donnees/` contient tes comptes, tes prospects et tes réglages Gmail : ne le partage pas.

## Règles de prospection (RGPD)

La prospection par e-mail d'entreprises est autorisée si le message concerne leur activité
et permet de se désinscrire. Le modèle d'e-mail contient une mention « STOP ».
Respecte toujours une demande de désinscription : passe le prospect en statut « STOP / ne plus contacter ».
