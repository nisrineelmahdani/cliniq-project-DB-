# DEV-008 — Validation SQL et optimisation

## Périmètre et environnement réellement inspecté

Le schéma actif et les index ont été inspectés en lecture seule avant les travaux.
Les 15 tables, colonnes, clés et relations officielles restent inchangées.
`DESIGNER_RESPONSABLE` conserve exactement la PK `(idHospitalisation,idActe)` :
`idMedecin` est une FK obligatoire, hors PK. Le MCD, `01_schema.sql`, `02_seed.sql`,
les services, repositories, pages et styles n'ont pas été modifiés.

Tous les essais d'écriture, DDL et jeux synthétiques utilisent uniquement
`cliniq_test_dev`. Le serveur disponible rapporte MySQL Community **26.10.0** ;
les scripts ciblent MySQL 8.0.16+ (syntaxe 8.x), mais cette session ne constitue
pas une validation sur un serveur portant effectivement un numéro 8.x.
Les résultats bruts sont dans [sql_evidence.json](sql_evidence.json).
Aucune installation dans la base de développement n'a été exécutée.

## Choix du trigger métier

### Hospitalisations : analyse et limite constatée

Le repository existant verrouille la ligne `LIT` avant de contrôler les séjours
par lecture courante, dans la même transaction. Les modifications verrouillent
les lits concernés dans un ordre stable. Les intervalles sont semi-ouverts
`[dateAdmission,dateSortie)` ; une sortie NULL représente une fin indéfinie.
Deux séjours peuvent donc se toucher exactement à la sortie/admission.
Les conflits concernent tous les séjours pertinents, terminés ou non.

Un simple SELECT de conflit dans un trigger ne protège pas de deux admissions
concurrentes. Le prototype qui tente une lecture verrouillante `FOR UPDATE`
de `HOSPITALISATION` dans son propre trigger BEFORE INSERT a été réellement
rejeté avec **1442 / HY000**. Le test reproductible conserve ce résultat.
MySQL limite les accès modifiants/verrouillants à la table déjà utilisée par
l'instruction appelante ; un trigger ne peut pas ouvrir une transaction autonome
ni utiliser LOCK TABLES pour contourner cela. Voir les
[restrictions officielles](https://dev.mysql.com/doc/refman/8.0/en/stored-program-restrictions.html).
Cette stratégie ne fournit donc pas la garantie demandée. Aucun trigger
hospitalier partiellement sûr n'est livré. La protection applicative DEV-006 et
ses tests concurrents restent actifs ; les écritures SQL arbitraires peuvent
encore contourner cette règle temporelle. La même limite de couverture subsiste
pour les chevauchements de rendez-vous hors chemin applicatif contrôlé.

### Règle retenue : cohérence consultation–rendez-vous

Une consultation liée doit avoir le même patient ET le même médecin que son RDV.
Les FK vérifient seulement l'existence des parents, et UNIQUE(idRDV) l'unicité du
lien ; elles n'imposent pas cette égalité inter-table. Le fichier
[03_triggers.sql](../database/03_triggers.sql) fournit trois gardes :

| Trigger | Événement | Vérification |
| --- | --- | --- |
| trg_consultation_rdv_bi | BEFORE INSERT CONSULTATION | Couple patient/médecin du RDV lié |
| trg_consultation_rdv_bu | BEFORE UPDATE CONSULTATION | Même contrôle après modification ou changement de RDV |
| trg_rdv_consultation_bu | BEFORE UPDATE RENDEZ_VOUS | Modification du parent compatible avec sa consultation |

Les deux premières gardes lisent le parent avec `FOR SHARE` et gardent son verrou
jusqu'au COMMIT/ROLLBACK. La troisième effectue une lecture courante verrouillante
de l'enfant lorsque le patient ou le médecin du parent change. L'UPDATE parent
possède déjà un verrou exclusif sur la ligne RDV. Un insert enfant concurrent
attend donc le parent, ou l'UPDATE parent attend le verrou partagé pris par
l'enfant. La lecture courante voit les données validées récentes même si une
ancienne vue REPEATABLE READ avait été ouverte. Les deux ordres concurrents et
les anciennes vues sont testés avec des connexions MySQL distinctes.
Voir les [lectures verrouillantes InnoDB](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html).

Les opérations multi-lignes ou d'autres ordres de verrouillage peuvent provoquer
un deadlock 1213 ou un délai 1205. Le client doit annuler la transaction et, si
approprié, retenter toute l'opération. La garantie porte sur les écritures
validées ; aucune absence de contention n'est promise. Les transactions
applicatives existantes annulent déjà les erreurs. Pas de COMMIT dans le trigger.

Un conflit produit **SQLSTATE 45000, erreur 1644**, avec un message fixe sans
nom de patient ni diagnostic. Un RDV inexistant reste une erreur FK **1452**.
Un deuxième lien cohérent vers un RDV occupé reste une erreur UNIQUE **1062**.
Les consultations sans RDV et la suppression du lien restent permises.
Les contrôles ne sont pas rétroactifs : auditer les lignes existantes avant toute
installation en développement. Aucun enregistrement n'est corrigé automatiquement.

### Démonstration sur le seed isolé

Exécuter les exemples séparément dans `cliniq_test_dev`, après installation :

```sql
START TRANSACTION;
INSERT INTO CONSULTATION
(dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV,idSalle)
VALUES ('2026-11-20 09:00:00','Exemple fictif','Exemple fictif',1,1,6,NULL);
-- Accepté : le RDV 6 appartient au patient 1 et au médecin 1.
ROLLBACK;

START TRANSACTION;
INSERT INTO CONSULTATION
(dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV,idSalle)
VALUES ('2026-11-20 09:00:00','Exemple fictif','Exemple fictif',2,1,6,NULL);
-- 1644 / 45000 : patient incohérent ; aucune insertion.
ROLLBACK;

START TRANSACTION;
UPDATE RENDEZ_VOUS SET idPatient=2 WHERE idRDV=1;
-- 1644 / 45000 : garde réciproque, consultation déjà liée.
ROLLBACK;
```

Une erreur SIGNAL rejette l'instruction ; le client doit encore annuler la
transaction complète si d'autres écritures la précédaient. Un test vérifie
explicitement cette annulation via le gestionnaire de transactions existant.

## Douze requêtes documentées

[04_queries.sql](../database/04_queries.sql) contient uniquement des lectures,
avec explications françaises et dates fixes pour une démonstration reproductible.
Les cardinalités suivantes ont été exécutées et vérifiées sur le seed officiel :

| ID | Objectif et notion | Lignes |
| --- | --- | ---: |
| Q01 | Patients nés avant 2000 ; WHERE et ORDER BY | 5 |
| Q02 | RDV avec patient et médecin ; INNER JOIN | 8 |
| Q03 | Patients sans RDV ; LEFT JOIN et NULL | 2 |
| Q04 | Consultations par médecin, y compris zéro ; GROUP BY/COUNT | 5 |
| Q05 | Médecins ayant au moins deux consultations ; HAVING | 2 |
| Q06 | Activité supérieure à la moyenne ; sous-requêtes | 2 |
| Q07 | Historique des séjours ; patient, lit et chambre | 5 |
| Q08 | Médicaments prescrits et attributs de PRESCRIRE | 7 |
| Q09 | Responsabilités ternaires ; hospitalisation, acte, médecin | 7 |
| Q10 | Classement d'activité ; CTE et DENSE_RANK | 5 |
| Q11 | Activité quotidienne et cumul ; SUM OVER | 4 |
| Q12 | Occupation par chambre à une date fixe ; CTE et agrégation | 5 |

Les tests ne vérifient pas seulement le nombre de lignes : ils contrôlent aussi
les identifiants attendus, les comptes par médecin, les couples de prescription,
les triplets CIF, les rangs et les cumuls. Q12 donne 7 lits, 2 occupés et 5 libres
au 16 novembre 2026 à midi, avec la même convention semi-ouverte que l'application.
La jointure de Q09 ne représente pas des exécutions répétées d'actes.

## Index : inspection et justification

Les PK, UNIQUE et index FK automatiques des 15 tables ont été inventoriés avant
création ; les inventaires complets avant/après figurent dans le JSON. Exemples :
`RENDEZ_VOUS` avait PRIMARY(idRDV), fk_rdv_patient(idPatient),
fk_rdv_medecin(idMedecin). `CONSULTATION` avait PRIMARY(idConsultation),
uq_consultation_rdv(idRDV), et les index FK patient, médecin et salle.
Aucun index ne commençait par `CONSULTATION.dateHeure`, ni par le couple
`RENDEZ_VOUS(idMedecin,dateHeure)`.

[05_indexes.sql](../database/05_indexes.sql) crée exactement :

```sql
CREATE INDEX idx_rdv_medecin_dateheure ON RENDEZ_VOUS(idMedecin,dateHeure);
CREATE INDEX idx_consultation_dateheure ON CONSULTATION(dateHeure);
```

Le premier correspond au filtre agenda médecin + intervalle temporel du
repository existant. Le second correspond aux consultations récentes du dashboard
avec borne de date, tri descendant et LIMIT. InnoDB inclut la PK dans les feuilles
des index secondaires ; aucun suffixe idRDV/idConsultation redondant n'est ajouté.
Le nouvel index composé peut remplacer implicitement l'ancien index FK à une
colonne : c'est observé ici pour fk_rdv_medecin, sans changement de FK.
Les deux nouveaux index sont non uniques et ont des préfixes distincts des
index préexistants. Ils consomment du stockage et augmentent le coût des INSERT,
DELETE et UPDATE des colonnes indexées. Ils n'accélèrent pas automatiquement les
recherches par sous-chaîne LOCATE. Aucun index supplémentaire n'est ajouté.

### EXPLAIN réels avant/après

`ANALYZE TABLE` précède les captures ; `EXPLAIN FORMAT=TRADITIONAL` conserve les
champs comparables. Les paramètres et SQL exacts sont enregistrés dans le JSON.
`rows` et `filtered` sont des **estimations de l'optimiseur**, pas un chronométrage.
Aucun gain de temps d'exécution n'est affirmé. Voir
[EXPLAIN officiel](https://dev.mysql.com/doc/refman/8.0/en/explain-output.html).

| Jeu / requête | Avant : type, key, rows estimées | Après : type, key, rows estimées | Résultat réel |
| --- | --- | --- | ---: |
| Seed, agenda | ref, fk_rdv_medecin, 2 | range, idx_rdv_medecin_dateheure, 1 | 1 |
| Seed, récentes | ALL, NULL, 7 | range, idx_consultation_dateheure, 7 | 7 |
| Synthétique, agenda | ref, fk_rdv_medecin, 2402 | range, idx_rdv_medecin_dateheure, 4 | 4 |
| Synthétique, récentes | ALL, NULL, 12024 | range, idx_consultation_dateheure, 3668 | 10 |

Avant, les quatre plans indiquent `Using where; Using filesort`.
Après, l'agenda indique `Using index condition`, et les consultations
`Using index condition; Backward index scan`, sans filesort. Sur le petit seed,
le deuxième index n'abaisse pas l'estimation rows : il améliore le chemin de tri,
pas une mesure de durée. Sur le jeu synthétique, la sélection médecin/date est
plus précise ; l'index des consultations permet le parcours ordonné avec LIMIT.
L'estimation 12024 diffère du compte réel 12007, ce qui illustre sa nature statistique.

Le benchmark ajoute temporairement **12000 RDV et 12000 consultations** fictifs
à dates de 2040, seulement dans le test isolé : totaux réels 12008 et 12007.
Les consultations sont sans RDV, les RDV répartis sur cinq médecins sans
chevauchement. Le seed est rétabli après la capture ; aucun jeu synthétique ne
reste dans la base de développement ou dans le seed versionné.

Reproduction (attention : réinitialise exclusivement la base test autorisée) :

```bash
CLINIQ_TEST_RESET_CONFIRM=cliniq_test_dev \
CLINIQ_TEST_SQL_EXTENSIONS=0 \
python -m tests.generate_sql_evidence --output docs/sql_evidence.json
```

Ce générateur commence sans extensions pour comparer le même schéma avant/après.
Il sérialise les essais via le verrou du harness, vérifie la cible avant reset,
installe les objets uniquement dans le test, et restaure le seed à la sortie.
Le JSON contient des plans et comptes, aucune donnée personnelle ni secret.

## Permissions et sécurité d'installation

La première tentative réelle a rencontré **1419** : journal binaire activé et
création de trigger refusée par la politique serveur. Après intervention de
l'administrateur utilisateur, les lectures ont confirmé `log_bin=1` et
`log_bin_trust_function_creators=1`, avec ALL PRIVILEGES limité à la base test et
USAGE global. Les trois CREATE TRIGGER ont ensuite réussi dans cette base.
Nous n'avons exécuté aucun SET GLOBAL ni changé les privilèges.
Une instance privée de diagnostic, utilisée pour isoler la restriction 1442 avant
la réponse administrateur, a été arrêtée ; les validations finales utilisent
uniquement le serveur existant. Voir les
[règles de journalisation des programmes stockés](https://dev.mysql.com/doc/refman/8.0/en/stored-programs-logging.html).

L'administrateur peut restaurer la valeur globale d'origine après la dernière
création de trigger de cette validation. Cela ne supprime pas les triggers déjà
créés ; une future réinitialisation des tests devra de nouveau satisfaire la
politique de création. Le compte DEFINER implicite doit rester valide avec ses
droits nécessaires à l'exécution. Aucun DEFINER explicite n'est imposé.

Pour le développement, suivre le processus soumis à approbation dans le README.
DDL implique des commits et verrous de métadonnées : sauvegarde, contrôle des
objets existants et fenêtre appropriée sont nécessaires. Les scripts échouent sur
un nom existant ; aucun DROP, remplacement automatique ou correction de données.

## Tests et limites

Les 28 nouveaux cas MySQL couvrent les 12 résultats SQL, métadonnées, écritures
valides et invalides directes INSERT/UPDATE, garde parent réciproque, NULL,
FK/UNIQUE existantes, concurrence dans les deux ordres, anciennes vues RR,
rollback transactionnel et erreur 1442 du prototype écarté. Les tests historiques
s'exécutent également avec les trois triggers et deux index installés.
Le harness n'accepte toujours que `cliniq_test_dev`, confirmation explicite,
FK actives, 15 tables autorisées, aucun lien inter-base ni objet exécutable inconnu.
Il autorise seulement les trois noms/événements/tables de triggers DEV-008.

Les participations minimales médecin–spécialité et chambre–lit restent hors
contrôle déclaratif. Le chevauchement temporel hors application reste non couvert.
Les triggers ne réparent pas les incohérences préexistantes et ne constituent
ni une piste d'audit ni un contrôle d'accès. Le modèle ne stocke pas d'exécutions
répétées d'actes. Aucune nouvelle entité n'a été introduite.

## Captures et vidéo conseillées

1. Montrer les 15 tables et la PK à deux colonnes de DESIGNER_RESPONSABLE.
2. Exécuter Q03, Q06, Q09 et Q10 ; expliquer optionalité, sous-requête et CIF.
3. Montrer l'INSERT cohérent puis ROLLBACK, l'erreur 1644 incohérente et la garde
   UPDATE parent ; ne montrer que le seed fictif de test.
4. Comparer les quatre plans EXPLAIN et distinguer estimations et mesures réelles.
5. Montrer le résultat complet de pytest et expliquer la limite hospitalière 1442.

## Résultats finaux réellement obtenus

Validation du 16 novembre 2026 sur le serveur existant :

- Suite complète, toutes options MySQL activées et extensions installées :
  **418 réussis, 0 échec, 0 erreur, 0 ignoré** (14,51 s), dont **135 cas MySQL**.
- Les 28 nouveaux cas DEV-008, exécutés aussi séparément : **28 réussis** (3,33 s).
- Exécution sans options MySQL : **283 réussis, 135 ignorés**, aucun échec (4,28 s).
- Mypy : aucun problème dans les **7 fichiers Python modifiés/ajoutés**.
- Première régression : 416 réussis et 2 échecs de sondes FK historiques ; les
  sondes visaient des RDV liés et rencontraient correctement la nouvelle garde
  1644 avant la FK. Elles ciblent maintenant un RDV sans consultation pour isoler
  1452. La relance complète ci-dessus est entièrement verte.
- Les 33 fichiers protégés contrôlés par SHA-256 sont inchangés, dont MCD,
  schéma/seed, connexion, repositories, services, pages et design.
- Dernière lecture du test : 15 tables, **89 lignes du seed**, trois triggers
  livrés et deux nouveaux index. Aucun prototype ni benchmark persistant.

Comptes finaux : SERVICE 5, SPECIALITE 5, MEDECIN 5, EXERCER 6, PATIENT 7,
RENDEZ_VOUS 8, SALLE 5, CONSULTATION 7, MEDICAMENT 5, PRESCRIRE 7,
CHAMBRE 5, LIT 7, HOSPITALISATION 5, ACTE_MEDICAL 5,
DESIGNER_RESPONSABLE 7.

Fichiers livrés pour DEV-008 : `.env.example`, `README.md`,
`database/03_triggers.sql`, `database/04_queries.sql`, `database/05_indexes.sql`,
`docs/sql_validation.md`, `docs/sql_evidence.json`, `tests/mysql_support.py`,
`tests/test_mysql_safety.py`, `tests/test_sql_assets.py`,
`tests/test_schema_mysql.py`, `tests/sql_validation_support.py`,
`tests/generate_sql_evidence.py`, `tests/test_dev008_sql.py`.

Toutes les créations de triggers de cette validation sont terminées :
**il est maintenant possible pour l'administrateur de restaurer la valeur globale
d'origine de `log_bin_trust_function_creators`**. Aucune modification globale n'a
été effectuée par l'agent. Une installation ultérieure en développement reste
soumise à approbation explicite et à la politique de création applicable.
