# DEV-009 — Contrôle final et remise

Validation réelle le 16 novembre 2026. Échéance : 18 novembre 2026, 12:00,
Africa/Casablanca. Les résultats agrégés sont dans `final_qa_results.json`.

- Suite intégrale : **418 réussis, 0 échec, 0 erreur, 0 ignoré**, dont 135 cas MySQL
  (15,82 s). Mypy : aucun problème dans 73 fichiers Python.
- Base de développement : 15 tables, 89 lignes inchangées par comparaison de
  comptes et empreintes avant/après QA, trois triggers et deux index vérifiés.
  Audit en lecture seule ; aucun reset ou écriture de développement en DEV-009.
- Colonnes, PK, UNIQUE, FK, règles RESTRICT et CHECK concordent avec la base test
  reconstruite par le SQL approuvé. MCD/01_schema/02_seed conservent leurs empreintes.
- EXERCER et PRESCRIRE ont leurs deux FK comme PK ; la CIF conserve exactement
  PRIMARY KEY(idHospitalisation,idActe), médecin obligatoire hors PK.
- Les guards de tests et le provisionneur ont été revus : pas de fallback des
  identifiants de tests vers l'application, cible exacte cliniq_test_dev, contrôles
  avant DROP TABLE, jamais DROP DATABASE. Le provisionneur crée seulement un UUID.
- Les sept pages ont été chargées via l'API Streamlit réelle. Le parcours complet
  est confirmé en SQL : patient, RDV, consultation liée, deux médicaments, lit,
  responsabilité. Rejets directs trigger 1644 et CIF 1062 confirmés dans le test.
  Serveur arrêté et seed restauré ; pas de capture ni de contrôle visuel navigateur
  revendiqué pour DEV-009. Aucun avertissement applicatif/dépréciation dans ce run ;
  Streamlit conseille seulement Watchdog, optionnel.
- Scan des candidats à la remise : aucun secret configuré ni signature de clé
  détecté. `.env` et dumps exclus. Les mots de passe factices des tests sont des
  fixtures. Ce contrôle est prudent, sans prétendre détecter toute chaîne sensible.
- Git est initialisé sur main, mais **aucun commit ni fichier suivi**. Aucun ajout,
  commit ou envoi distant effectué. Le ZIP fournit les sources indépendamment de Git.

## Changements DEV-009

README réécrit ; documentation MLD, synthèse française et conducteur 9 min 30 ;
preuves QA agrégées ; définitions de dépendances de développement/versions
exercées ; outil de packaging allowlisté et manifeste SHA-256 ; exclusions Git.
`pytest.ini` limite la découverte à tests pour éviter de rejouer les copies du ZIP.
Deux ajustements d'annotations du connecteur dans db/connection.py et
 database/setup.py corrigent le contrôle global, sans changement de comportement.
Aucune logique SQL, modèle, page ou règle métier n'est modifiée par DEV-009.

## Livrables et manques honnêtes

Le dossier `submission/CLINIQ_DEV009` et son ZIP livrent sources, SQL, PNG officiel,
MLD transcrit, tests, dépendances et documentation. `MANIFEST.sha256` et
`PACKAGE_AUDIT.json` accompagnent le paquet. Reproduction :
`python tools/package_submission.py` (aucun accès DB). Le ZIP est contrôlé par CRC.

Restent à fournir : **source éditable originale du MCD**, **vidéo réelle et
captures**, puis dépôt effectif auprès de l'établissement. Le MLD est une
transcription validée, pas un original prétendument retrouvé. Le serveur disponible
annonce 26.10.0 ; une validation indépendante sur un MySQL 8.x numéroté reste
nécessaire pour cette cible. Les dépendances effectivement exercées sont
consignées ; plotly est encore déclaré mais inutilisé et absent du runtime local.
Les limites de chevauchement hors chemin applicatif, de participation minimale,
d'audit, d'authentification et d'échelle sont détaillées dans le README/rapport.

Le packaging local n'est pas un dépôt académique ni une vidéo. Aucun résultat,
chiffre de performance ou média factice n'est ajouté.
