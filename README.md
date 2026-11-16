# CLINIQ — Projet académique de bases de données relationnelles

CLINIQ est une application de gestion de clinique en Python, Streamlit et MySQL.
Elle utilise exactement les **15 tables** du MCD/MLD approuvé. DEV-009 valide et
prépare la remise ; aucune nouvelle fonctionnalité métier n'est ajoutée.

**Échéance : 18 novembre 2026 à 12:00, Africa/Casablanca.**

## Livrables et architecture

- `app.py`, `pages/`, `ui/` : navigation et interface existantes ; sept pages actives.
- `services/` : validation métier, horloge locale et orchestration.
- `db/repositories/` : requêtes paramétrées et contrôles de concurrence.
- `db/connection.py` : configuration `.env`, connexions et transactions avec rollback.
- `database/01_schema.sql` : 15 tables InnoDB, utf8mb4, PK/FK/UNIQUE/CHECK.
- `database/02_seed.sql` : 89 enregistrements entièrement fictifs.
- `database/03_triggers.sql` : trois gardes de cohérence consultation–RDV.
- `database/04_queries.sql` : 12 requêtes commentées en français.
- `database/05_indexes.sql` : deux index secondaires non uniques.
- `docs/mcd_mld/` : MCD officiel PNG et transcription du MLD approuvé.
- `docs/rapport_technique.md` : synthèse technique en français.
- `docs/demo_video.md` : scénario reproductible de moins de dix minutes.
- `docs/validation_finale.md` : résultats, sécurité et checklist de remise.
- `docs/sql_validation.md`, `docs/sql_evidence.json` : preuves EXPLAIN réelles.
- `tests/` : tests unitaires, repositories, interface et MySQL isolé.

Les modules livrés couvrent le dashboard SQL, patients, rendez-vous,
consultations, prescriptions, hospitalisations/lits et affectations d'actes.
Les catalogues de médicaments, chambres, lits, médecins et actes sont existants ;
aucune interface CRUD supplémentaire de catalogue n'est revendiquée.

## Prérequis et environnement Python

Python 3.11+ conseillé ; MySQL **8.0.16+ dans la branche 8.x** pour le provisionneur,
CHECK actifs et InnoDB. MariaDB n'a pas été validé. Connector/Python 9.2+ est
nécessaire pour l'exécution de scripts multi-instructions.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

`requirements.txt` décrit les dépendances applicatives/tests ;
`requirements-dev.txt` ajoute mypy. `requirements-validated.txt` consigne les
versions directes réellement utilisées, sans prétendre être un verrou transitif.

La validation locale utilise Python 3.14.8 et un serveur MySQL annonçant 26.10.0.
Le SQL compatible 8.x a été exécuté sur ce serveur ; une validation indépendante
sur un serveur réellement numéroté 8.x reste à effectuer. Le provisionneur
`database.setup` refuse volontairement les versions hors 8.x ; il n'a pas été
assoupli pour le serveur local existant.

## Configuration MySQL

Renseigner `.env` localement ; ne jamais le remettre, publier ou afficher en vidéo.

| Usage | Variables |
| --- | --- |
| Application | MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD |
| Nouveau développement | CLINIQ_SETUP_HOST, CLINIQ_SETUP_PORT, CLINIQ_SETUP_USER, CLINIQ_SETUP_PASSWORD |
| Tests isolés | CLINIQ_TEST_HOST, CLINIQ_TEST_PORT, CLINIQ_TEST_DATABASE=cliniq_test_dev, CLINIQ_TEST_USER, CLINIQ_TEST_PASSWORD |

`CLINIQ_SETUP_UNIX_SOCKET` et `CLINIQ_TEST_UNIX_SOCKET` sont facultatifs. Le harness
ne reprend jamais les identifiants applicatifs comme identifiants de test.
L'application dispose de SELECT/INSERT/UPDATE/DELETE sur sa base. L'installation
DDL nécessite les droits propres à ses opérations. Les tests nécessitent
SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, REFERENCES, TRIGGER et INDEX sur
**cliniq_test_dev seulement**, sans CREATE DATABASE global. L'administrateur doit
provisionner cette base séparée et attribuer les privilèges appropriés.

## Installer le schéma et le seed dans une nouvelle base

Sur un serveur MySQL 8.x compatible, configurer CLINIQ_SETUP_* puis :

```bash
python -m database.setup
```

Le provisionneur crée une nouvelle base `cliniq_dev_<uuid>`, charge 01 puis 02 et
imprime son nom. Reporter ce nom dans MYSQL_DATABASE. Il ne réutilise ni ne
réinitialise une base existante. En cas d'erreur DDL, la nouvelle base incomplète
est conservée ; ne pas réessayer en supprimant une base existante.
Le seed est transactionnel, mais le DDL MySQL implique des commits.

Pour le serveur local existant, `cliniq_db` est déjà installé et vérifié : **ne pas
recharger 01/02**. La remise contient le seed fictif, aucun dump de cette base.

## Installer les triggers et index en sécurité

Les trois triggers et deux index ont déjà été installés dans `cliniq_db` avec
l'autorisation du propriétaire. Voir `docs/development_installation.md`.
Ne pas les réinstaller : les scripts sont volontairement non idempotents.

Pour une **nouvelle cible approuvée** : confirmer SELECT DATABASE(), sauvegarder
la base, inspecter SHOW TRIGGERS et SHOW INDEX pour exclure les conflits, et
vérifier zéro incohérence existante :

```sql
SELECT COUNT(*) AS incoherences
FROM CONSULTATION c JOIN RENDEZ_VOUS r ON r.idRDV=c.idRDV
WHERE c.idPatient<>r.idPatient OR c.idMedecin<>r.idMedecin;
```

Arrêter si le résultat n'est pas zéro, ou si un trigger/index équivalent existe.
Après approbation de la cible et de l'impact (rejets métier nouveaux, coût disque
et écritures des index, commits DDL et verrous de métadonnées), utiliser le client
mysql, qui comprend DELIMITER. Remplacer les paramètres par la cible revue :

```bash
mysql --host=HOTE_APPROUVE --user=COMPTE_APPROUVE --password \
  --database=BASE_APPROUVEE < database/03_triggers.sql
mysql --host=HOTE_APPROUVE --user=COMPTE_APPROUVE --password \
  --database=BASE_APPROUVEE < database/05_indexes.sql
```

Ne pas mettre le mot de passe dans la commande. Arrêter à la première erreur et
inspecter les objets déjà créés : le DDL n'est pas annulable en bloc. Aucun DROP
ou remplacement automatique n'est fourni. L'index composé peut absorber l'ancien
index simple supportant la FK médecin sans changer cette FK.

Avec binary logging, une politique serveur peut refuser CREATE TRIGGER (1419).
Seul l'administrateur décide des permissions/de `log_bin_trust_function_creators`.
Aucun script du projet ne modifie les variables globales. Le compte DEFINER
implicite doit rester valide. Une fois les créations terminées, l'administrateur
peut restaurer sa valeur d'origine ; les triggers existants ne sont pas supprimés.

## Lancer Streamlit

```bash
python -m streamlit run app.py
```

La navigation conserve le design CLINIQ existant. Le module « Analyses » annoncé
en pied de navigation n'est pas une page active. Pas d'authentification clinique
ou de déploiement de production revendiqué par ce projet universitaire.

## Tests et contrôles de types

Sans accès MySQL réel ni reset :

```bash
python -m pytest -q -rs
```

Suite complète sur la base **dédiée pré-provisionnée uniquement** :

```bash
CLINIQ_TEST_RESET_CONFIRM=cliniq_test_dev \
CLINIQ_RUN_MYSQL_TESTS=1 \
CLINIQ_RUN_DEV003_MYSQL_TESTS=1 \
CLINIQ_RUN_DEV004_MYSQL_TESTS=1 \
CLINIQ_RUN_DEV005_MYSQL_TESTS=1 \
CLINIQ_RUN_DEV006_MYSQL_TESTS=1 \
CLINIQ_RUN_DEV007_MYSQL_TESTS=1 \
CLINIQ_RUN_DEV008_MYSQL_TESTS=1 \
CLINIQ_TEST_SQL_EXTENSIONS=1 \
python -m pytest -q -rs

python -m mypy --ignore-missing-imports app.py db services pages ui database tests tools
```

La suite intégrale reconstruit les tables autorisées de cliniq_test_dev et
restaure le seed en sortie. Elle ne DROP jamais la base elle-même. Le nom exact,
la confirmation, SELECT DATABASE(), les FK actives, les objets connus et
l'absence de relations inter-bases sont vérifiés avant reset. cliniq_db, ventes,
Hollywood et toute autre cible sont refusées ; un garde autouse empêche aussi
une connexion réelle oubliée vers une base applicative. Ne jamais conserver la
confirmation de reset dans `.env`. Ne pas ouvrir la démo sur la base test pendant
une suite : un verrou sérialise les essais.

Résultats DEV-009 et limites de vérification : `docs/validation_finale.md`.
Pour recréer les preuves EXPLAIN avant/après avec jeu synthétique temporaire :

```bash
CLINIQ_TEST_RESET_CONFIRM=cliniq_test_dev CLINIQ_TEST_SQL_EXTENSIONS=0 \
python -m tests.generate_sql_evidence --output docs/sql_evidence.json
```

Cela réinitialise uniquement la base test explicitement autorisée et restaure
le seed. Les estimations rows d'EXPLAIN ne sont pas des durées mesurées.

## Limites connues et remise

- Les chevauchements d'hospitalisations sont empêchés par le chemin applicatif
  transactionnel verrouillant LIT ; du SQL direct peut contourner cette règle.
  Le prototype de trigger auto-verrouillant échouait avec 1442 et n'est pas livré.
- Même limite de couverture temporelle des rendez-vous hors chemin applicatif.
- Les FK ne garantissent pas au moins une spécialité par médecin ou un lit par chambre.
- Les trois triggers garantissent la cohérence patient/médecin consultation–RDV,
  mais ne corrigent pas rétroactivement des incohérences historiques.
- La CIF est exactement (idHospitalisation,idActe) -> idMedecin ; aucune notion
  d'exécutions répétées ou d'audit de réaffectation n'est stockée.
- La protection contre les éditions périmées compare les valeurs ; elle ne détecte
  pas une modification intermédiaire revenue à la même valeur.
- Des sélecteurs chargent les référentiels complets ; pas d'optimisation à grande
  échelle, d'authentification ou de garanties de production revendiquées.
- Le PNG officiel du MCD est livré ; son original éditable n'a pas été fourni.
- La vidéo et les captures réelles restent à enregistrer ; aucun média factice.

Le dossier `submission/CLINIQ_DEV009` et son ZIP contiennent les sources, scripts,
modèles disponibles, documentation et tests. Le manifeste SHA-256 permet de
vérifier leur intégrité. `.env`, environnements virtuels, caches, Git, outils
locaux, dumps et identifiants en sont exclus. Ne pas confondre la présence du
livrable local avec un dépôt effectué auprès de l'établissement.

## DEV-010 — Interface et parcours repensés

Le code courant comporte désormais le redesign rose/blanc CLINIQ : navigation
persistante en trois groupes, en-têtes avec action principale, dashboard organisé
par activité et capacité, dossier patient à côté du répertoire, sélecteurs avant
les longues listes, filtres avancés repliables, formulaires regroupés et carte
visuelle des lits. Les listes se replient lorsqu'un dossier est ouvert ; les
commandes de pagination apparaissent seulement lorsqu'il existe plusieurs pages.
Les confirmations, validations, verrous et éditions protégées sont conservés.

Les couleurs, surfaces, états, champs et dates sont centralisés dans `ui/design.py`,
`ui/styles.css` et `.streamlit/config.toml`. Le rose #E84C71 reste l'accent ; le
rouge profond #C93F55 est utilisé pour des CTA à texte blanc plus lisibles.
Aucune dépendance applicative n'a été ajoutée. Inter est chargé à distance avec
repli système si indisponible. Les données et indicateurs restent issus de MySQL.

Audit, preuves et captures : [docs/design/redesign_audit.md](docs/design/redesign_audit.md).
Le backend, les modèles, les cinq scripts SQL et la connexion restent inchangés
pendant DEV-010. Redémarrer le processus Streamlit existant après la mise à jour
pour recharger les composants partagés si le watcher n'est pas disponible.

L'archive `submission/CLINIQ_DEV009.zip` est le snapshot académique créé avant ce
redesign ; elle n'a pas été régénérée silencieusement en livrable DEV-010.

Résultats DEV-010 : **427 tests réussis, 0 échec, 0 ignoré**, dont 135 cas MySQL ;
mypy sans erreur sur 74 fichiers. Répétition réelle : 68 interactions, 23 contrôles
SQL. Sept pages contrôlées à 1440 px et 390 px, captures authentiques dans docs/design.
