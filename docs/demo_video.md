# Démonstration CLINIQ — conducteur vidéo, 9 min 30 maximum

Remise : **18 novembre 2026, 12:00 (Africa/Casablanca)**.
Le scénario ci-dessous a été répété via l'API de l'application Streamlit réelle,
sur `cliniq_test_dev`, puis confirmé par des lectures SQL indépendantes. Les sept
pages ont été chargées sans exception. Il reste à enregistrer la vidéo ; aucun
fichier vidéo ou capture n'est fabriqué dans cette livraison.

## Préparation hors enregistrement

1. Fermer toute application utilisant la base test. Configurer CLINIQ_TEST_* dans
   le `.env` privé et faire préparer `cliniq_test_dev` par la suite complète du
   README (extensions activées). L'administrateur doit permettre CREATE TRIGGER.
   Cette préparation remet à zéro exclusivement cette base test, jamais cliniq_db.
2. Ne plus lancer de suite/reset pendant la démo. Utiliser uniquement le seed
   fictif, sans dump local. Lancer une instance pointant sur le compte test,
   sans modifier `.env` et sans afficher les secrets :

   ```bash
   python - <<'PY'
   import os, subprocess, sys
   from dotenv import load_dotenv
   load_dotenv()
   assert os.environ.get('CLINIQ_TEST_DATABASE') == 'cliniq_test_dev'
   env = os.environ.copy()
   for suffix in ('HOST', 'PORT', 'USER', 'PASSWORD'):
       env['MYSQL_' + suffix] = os.environ.get('CLINIQ_TEST_' + suffix, '')
   env['MYSQL_DATABASE'] = 'cliniq_test_dev'
   subprocess.run([sys.executable, '-m', 'streamlit', 'run', 'app.py',
                   '--server.address=127.0.0.1', '--server.port=8789'], env=env, check=True)
   PY
   ```

3. Préparer un client SQL connecté explicitement à cliniq_test_dev ; vérifier
   SELECT DATABASE(). Ouvrir `sql_validation.md` et `sql_evidence.json` pour les
   EXPLAIN avant/après historiques réels. Ne pas supprimer des index pour la vidéo.
4. Valeurs répétées : patient **Demo-DEV009 Camille**, naissance 10/05/1995,
   téléphone fictif 0600000099, adresse « Adresse fictive DEV009 » ; médecin
   **Exemple-Amrani Lina** ; RDV **17/11/2026 09:00**, 30 min, **Confirmé**.
   Les dates sont fixes pour reproduire le scénario ; les indicateurs « aujourd'hui »
   dépendent réellement du jour local, donc ne pas annoncer un chiffre attendu.
5. Après une répétition, arrêter Streamlit puis relancer la préparation test si
   nécessaire pour repartir du seed. Ne jamais réinitialiser la base de développement.

## Conducteur parlé et actions

| Temps | Écran et actions | Commentaire proposé |
| --- | --- | --- |
| 00:00–00:30 | Titre, MCD puis navigation | « CLINIQ applique un modèle officiel de quinze tables. Nous montrons les données fictives de la base test. » |
| 00:30–01:15 | Vue d'ensemble, Actualiser, statistiques et graphiques | « Ces indicateurs sont calculés en SQL. L'occupation dépend des dates d'admission et de sortie ; une sortie NULL prolonge le séjour. Les chiffres affichés sont ceux du jour, sans valeur simulée. » |
| 01:15–02:10 | Patients → Nouveau patient ; saisir les valeurs ci-dessus, enregistrer ; Répertoire → rechercher Demo-DEV009 | « La validation précède l'écriture transactionnelle. La recherche retrouve le dossier persisté. » Noter l'ID patient affiché. |
| 02:10–02:55 | Rendez-vous → Nouveau rendez-vous ; patient créé, médecin 1, date/heure prévues, durée 30, Confirmé ; enregistrer | « Nous réutilisons les patients et médecins existants. Le contrôle de chevauchement du médecin s'effectue aussi dans la transaction. » |
| 02:55–03:50 | Consultations → Nouvelle consultation ; patient et médecin, puis RDV créé, salle CONS-01, même date/heure ; motif/diagnostic explicitement fictifs ; enregistrer | « Le lien RDV est facultatif et unique. Ici les deux couples patient/médecin correspondent ; le trigger les vérifie également. » Noter l'ID consultation. |
| 03:50–04:45 | Prescriptions → consultation créée ; ajouter DemoCalm quantité 2/durée 3/posologie fictive, puis DemoVita quantité 1/durée 2/posologie fictive | « Deux médicaments donnent deux lignes de PRESCRIRE. Quantité, posologie et durée appartiennent à cette association, dont la PK est le couple consultation–médicament. Ce ne sont pas des conseils médicaux. » |
| 04:45–05:40 | Hospitalisations → Nouvelle admission ; même patient, 17/11/2026 10:00, sortie non renseignée, chambre 102, lit A ; enregistrer puis Occupation | « L'application verrouille le lit et contrôle tous les intervalles pertinents. Un séjour futur reste prévu jusqu'à son admission ; le SQL direct n'est pas couvert par un trigger de chevauchement. » Noter l'ID séjour. |
| 05:40–06:40 | Actes médicaux → Nouvelle affectation ; séjour créé, Examen clinique fictif, médecin 1 ; Vue par séjour ; montrer la PK puis tentative SQL ci-dessous | « DESIGNER_RESPONSABLE stocke une responsabilité. Le couple séjour–acte détermine un seul médecin. Changer de responsable nécessite un UPDATE de la même ligne, et non un second INSERT. » |
| 06:40–07:30 | Client SQL test : tentative de lien incohérent ci-dessous | « Le SQL direct est rejeté avec 1644, SQLSTATE 45000. La règle fonctionne aussi lorsque l'on modifie le RDV parent. » |
| 07:30–09:00 | Montrer les deux CREATE INDEX et les plans réels du rapport/JSON | « L'agenda passe de ref/2402 lignes estimées à range/4 ; les consultations récentes de ALL/12024 à range/3668 avec parcours inverse et LIMIT. Filesort disparaît. Ce sont des plans, pas des gains de temps mesurés. Le benchmark synthétique était isolé et a été retiré. » |
| 09:00–09:30 | Résultats pytest et limites | « La validation complète rapporte 418 tests réussis, dont 135 cas MySQL. Le schéma et la CIF sont préservés. Le chevauchement hospitalier hors chemin applicatif et les participations minimales restent des limites documentées. » |

## SQL de démonstration, uniquement dans le test

Ne pas présumer les IDs si le seed n'est plus neuf. Remplacer les variables par
les IDs affichés. Sur le seed neuf du scénario vérifié, patient=8, RDV=9,
consultation=8, séjour=6. Les SELECT avant chaque tentative confirment la cible.

```sql
SELECT DATABASE(); -- doit être exactement cliniq_test_dev
SET @sejour = 6; -- adapter à l'ID effectivement créé
SELECT idHospitalisation,idActe,idMedecin
FROM DESIGNER_RESPONSABLE WHERE idHospitalisation=@sejour;
START TRANSACTION;
INSERT INTO DESIGNER_RESPONSABLE(idHospitalisation,idActe,idMedecin)
VALUES (@sejour,1,2);
-- Attendu : 1062 / 23000, même couple séjour–acte malgré un autre médecin.
ROLLBACK;

SET @consultation = 8; -- adapter à l'ID effectivement créé
SELECT idConsultation,idPatient,idMedecin,idRDV
FROM CONSULTATION WHERE idConsultation=@consultation;
START TRANSACTION;
UPDATE CONSULTATION SET idPatient=1 WHERE idConsultation=@consultation;
-- Attendu : 1644 / 45000, patient différent de celui du RDV lié.
ROLLBACK;
```

Pour une démonstration EXPLAIN en direct, rejouer uniquement les SELECT/EXPLAIN
paramétrés enregistrés dans le JSON, avec les index installés. Identifier les
captures « avant » comme preuves historiques DEV-008 ; ne pas prétendre les
recréer en direct sans refaire le benchmark isolé. Ni chronométrage inventé,
ni fausse capture. Après enregistrement, arrêter l'instance et restaurer le seed
par la suite dédiée si souhaité ; ne pas laisser un reset tourner pendant la vidéo.
