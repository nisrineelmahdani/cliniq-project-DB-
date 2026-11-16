# CLINIQ — Synthèse technique du projet relationnel

## Objectif et réalisation

CLINIQ propose une interface Streamlit en Python pour explorer et gérer les
patients, rendez-vous, consultations, prescriptions, hospitalisations et
responsabilités d'actes d'une clinique. Le dashboard utilise des agrégations SQL
réelles. Le projet académique conserve le MCD officiel et ses quinze relations.
Le schéma InnoDB utilise utf8mb4, des clés primaires, étrangères, uniques et des
CHECK. Le seed de 89 lignes est fictif et distinct des dossiers de développement.

L'architecture sépare pages/UI, services de validation et repositories SQL.
Les valeurs utilisateur sont paramétrées. Les écritures utilisent transactions,
rollback, verrous et comparaison des valeurs pour empêcher les éditions périmées.
Les erreurs affichées n'incluent pas le diagnostic, le nom ou les données du patient.
Le temps clinique est interprété en Africa/Casablanca avec DATETIME sans fuseau.

## Modèle et contraintes

Le MCD est livré dans `mcd_mld/MCD_Clinique.png` et le MLD approuvé dans
`mcd_mld/MLD_Clinique.md`. Les quinze tables et leurs attributs sont ceux du SQL
initial. Les associations EXERCER et PRESCRIRE ont des PK composées de leurs deux
FK. Les attributs quantite/posologie/duree appartiennent à PRESCRIRE, sans entité
PRESCRIPTION supplémentaire. Un lit est unique dans sa chambre par
UNIQUE(idChambre,numeroLit). Le lien CONSULTATION.idRDV est nullable et UNIQUE.

La relation ternaire DESIGNER_RESPONSABLE associe hospitalisation, type d'acte
et médecin. La CIF est **(idHospitalisation,idActe) -> idMedecin**. Sa PK est
exactement (idHospitalisation,idActe) ; idMedecin reste une FK obligatoire hors PK.
Le même médecin peut gérer plusieurs couples, mais un couple possède un seul
responsable. Une réaffectation modifie la ligne existante. Les exécutions répétées
d'un acte et l'historique des responsables sont hors du modèle approuvé.

## Règle métier inter-table et triggers

Les FK et UNIQUE ne garantissent pas que le patient/médecin d'une consultation
coïncident avec ceux du RDV lié. Trois triggers BEFORE imposent cette égalité :
INSERT et UPDATE CONSULTATION, puis UPDATE RENDEZ_VOUS pour protéger le parent.
Les lectures FOR SHARE sont courantes, avec verrous conservés jusqu'à la fin de
transaction. Les tests couvrent les deux ordres concurrents et une ancienne vue
REPEATABLE READ. Un conflit produit 1644 / SQLSTATE 45000 avec message fixe.
Les FK/UNIQUE gardent leurs rôles distincts : 1452 pour parent manquant et 1062
pour doublon. Les consultations sans rendez-vous restent autorisées.

Le trigger hospitalier recommandé a été étudié : une lecture verrouillante de
HOSPITALISATION dans son propre trigger a été rejetée avec 1442. Aucun trigger
partiellement sûr n'est livré. Les admissions applicatives verrouillent LIT et
vérifient les intervalles semi-ouverts [admission,sortie), NULL étant une fin
indéfinie. Les écritures SQL arbitraires peuvent contourner ce contrôle. Les
chevauchements de rendez-vous ont aussi une protection applicative, sans trigger
universel. Deadlocks/délais demeurent possibles et nécessitent rollback/reprise.

## Requêtes et index

`04_queries.sql` expose douze requêtes commentées : sélection/tri, INNER JOIN,
anti-jointure LEFT JOIN, COUNT/GROUP BY, HAVING, activité supérieure à la moyenne
par sous-requête, historiques de séjours, prescriptions, ternaire CIF, classement
CTE/DENSE_RANK, cumul SUM OVER et occupation par chambre.

Exemples à commenter dans le rapport : Q03 retourne les deux patients du seed
sans rendez-vous ; Q06 les médecins 1 et 5 au-dessus de l'activité moyenne ; Q09
retourne sept affectations ternaires ; Q12 retourne sept lits dont deux occupés
au 16 novembre 2026 à midi. Les valeurs et associations ont été vérifiées, pas
seulement les cardinalités.

Les inventaires des PK, UNIQUE et index FK ont précédé les ajouts :
`idx_rdv_medecin_dateheure(idMedecin,dateHeure)` répond au filtre agenda médecin +
intervalle ; `idx_consultation_dateheure(dateHeure)` répond aux consultations
récentes ordonnées avec LIMIT. Ils sont non uniques et non redondants avec les
préfixes d'index antérieurs. InnoDB peut absorber l'ancien index FK simple médecin
sans changer la contrainte. Les index coûtent espace et maintenance à l'écriture.

Les EXPLAIN réellement capturés dans `sql_evidence.json` donnent :

| Requête | Seed avant → après (rows estimées) | Synthétique avant → après |
| --- | --- | --- |
| Agenda médecin | ref/fk_rdv_medecin/2 → range/index composé/1 | ref/2402 → range/4 |
| Consultations récentes | ALL/7 → range/index date/7 | ALL/12024 → range/3668 |

Filesort disparaît dans les plans après index ; le second utilise un parcours
inverse. Le benchmark ajoutait temporairement 12000 lignes par table concernée,
soit 12008 RDV et 12007 consultations, dans le test uniquement. rows est une
estimation, différente parfois du compte réel. Aucun gain de durée n'est mesuré
ou revendiqué. Les résultats détaillés figurent dans `sql_validation.md`.

## Validation et périmètre de confiance

DEV-009 exécute la suite complète : **418 réussis, 0 échec, 0 ignoré**, dont
**135 cas MySQL**. Le contrôle mypy porte sur **73 fichiers Python**. Deux fichiers
ont reçu des ajustements d'annotations pour les types du connecteur, sans
modification d'algorithme. Le test isolé restaure le seed ; le contrôle de la base
de développement est en lecture seule. Les protections de cible empêchent les
resets vers cliniq_db, ventes, Hollywood ou une base non autorisée.

Une répétition via l'API Streamlit réelle a chargé les sept pages et persisté un
parcours patient → RDV → consultation liée → deux médicaments → admission/lit →
responsable d'acte. Des connexions SQL indépendantes ont vérifié ces écritures et
les rejets trigger/CIF. Le serveur temporaire a été arrêté et le seed restauré.
Cette validation fonctionnelle n'est pas une inspection visuelle par navigateur,
ni une vidéo enregistrée. Les tests UI historiques couvrent aussi les actions
modifier/retirer, confirmations et erreurs. Aucun média artificiel n'est fourni.

## Limites et livrables restant à fournir

La validation locale utilise Python 3.14.8, Streamlit 1.67.0 et MySQL annonçant
26.10.0. Un essai sur un serveur réellement numéroté MySQL 8.x reste distinct de
cette validation. Le provisionneur de base neuve accepte uniquement 8.x.
Le modèle ne peut imposer par FK les minimums spécialité/médecin et lit/chambre.
Les triggers ne corrigent pas rétroactivement les données ; pas d'audit des
réaffectations, d'authentification ou de garantie de production.
Les sélecteurs de référentiels complets limitent le passage à grande échelle.
Le MCD original éditable est absent ; seul le PNG est disponible. Le MLD livré
est une transcription documentaire de la spécification validée. La vidéo réelle,
les captures et le dépôt auprès de l'établissement restent à effectuer avant
**18 novembre 2026 à 12:00, Africa/Casablanca**.
