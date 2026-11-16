-- FICTIONAL educational records only. Names, addresses, phones, medications and
-- clinical scenarios are invented. Medication instructions are not medical advice.
-- Fixed dates make this reproducible; these are NOT today's dashboard statistics.
-- Run ONCE on a freshly created schema, in strict mode, within one transaction.
-- No INSERT IGNORE, REPLACE, FK disabling, destructive cleanup or ID resets.
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
START TRANSACTION;

INSERT INTO SERVICE (idService, libelleService) VALUES
(1, 'Médecine générale'), (2, 'Cardiologie'), (3, 'Pédiatrie'),
(4, 'Chirurgie'), (5, 'Médecine interne');
INSERT INTO SPECIALITE (idSpecialite, libelleSpecialite) VALUES
(1, 'Médecine générale'), (2, 'Cardiologie'), (3, 'Pédiatrie'),
(4, 'Chirurgie générale'), (5, 'Médecine interne');
INSERT INTO MEDECIN (idMedecin, nom, prenom, telephone, idService) VALUES
(1, 'Exemple-Amrani', 'Lina', 'DEMO-M01', 1),
(2, 'Exemple-Bennani', 'Sami', 'DEMO-M02', 2),
(3, 'Exemple-Tazi', 'Nora', 'DEMO-M03', 3),
(4, 'Exemple-Idrissi', 'Adam', 'DEMO-M04', 4),
(5, 'Exemple-Fassi', 'Ines', 'DEMO-M05', 5);
INSERT INTO EXERCER (idMedecin, idSpecialite) VALUES
(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (5, 1);

INSERT INTO PATIENT (idPatient, nom, prenom, dateNaissance, telephone, adresse) VALUES
(1, 'Demo-Alami', 'Yasmine', '1990-04-12', 'DEMO-P01', '1 rue Fictive, Ville Démo'),
(2, 'Demo-Saidi', 'Omar', '1978-09-03', 'DEMO-P02', '2 rue Fictive, Ville Démo'),
(3, 'Demo-Mansouri', 'Aya', '2017-02-21', 'DEMO-P03', '3 rue Fictive, Ville Démo'),
(4, 'Demo-Naciri', 'Karim', '1985-06-18', 'DEMO-P04', '4 rue Fictive, Ville Démo'),
(5, 'Demo-Ziani', 'Salma', '1966-11-08', 'DEMO-P05', '5 rue Fictive, Ville Démo'),
(6, 'Demo-Rami', 'Ilyas', '2000-01-30', 'DEMO-P06', '6 rue Fictive, Ville Démo'),
(7, 'Demo-Hilali', 'Meriem', '1996-07-07', 'DEMO-P07', '7 rue Fictive, Ville Démo');
-- Patients 6 and 7 have no appointments. Patient 7 has no consultations either.
INSERT INTO RENDEZ_VOUS (idRDV, dateHeure, dureePrevue, statut, idPatient, idMedecin) VALUES
(1, '2026-11-02 09:00:00', 30, 'Terminé', 1, 1),
(2, '2026-11-02 09:00:00', 45, 'Terminé', 2, 2),
(3, '2026-11-02 10:00:00', 30, 'Terminé', 3, 3),
(4, '2026-11-03 11:00:00', 45, 'Terminé', 4, 4),
(5, '2026-11-03 14:00:00', 30, 'Terminé', 5, 5),
(6, '2026-11-20 09:00:00', 30, 'Planifié', 1, 1),
(7, '2026-11-20 10:00:00', 45, 'Confirmé', 2, 2),
(8, '2026-11-21 11:00:00', 30, 'Annulé', 3, 3);
INSERT INTO SALLE (idSalle, codeSalle) VALUES
(1, 'CONS-01'), (2, 'CONS-02'), (3, 'CONS-03'), (4, 'CONS-04'), (5, 'CONS-05');
INSERT INTO CONSULTATION (idConsultation, dateHeure, motif, diagnostic, idPatient, idMedecin, idRDV, idSalle) VALUES
(1, '2026-11-02 09:00:00', 'Céphalées légères, scénario fictif', 'Céphalée de tension fictive', 1, 1, 1, 1),
(2, '2026-11-02 09:00:00', 'Contrôle cardiaque fictif', 'Bilan de surveillance fictif', 2, 2, 2, 2),
(3, '2026-11-02 10:00:00', 'Rhinorrhée, scénario fictif', 'Rhinite fictive', 3, 3, 3, 3),
(4, '2026-11-03 11:00:00', 'Contrôle postopératoire fictif', 'Cicatrisation favorable fictive', 4, 4, 4, 4),
(5, '2026-11-03 14:00:00', 'Fatigue, scénario fictif', 'Bilan clinique fictif', 5, 5, 5, 5),
(6, '2026-11-04 15:00:00', 'Consultation sans rendez-vous fictive', 'Irritation cutanée fictive', 6, 1, NULL, 1),
(7, '2026-11-05 16:00:00', 'Avis au chevet, scénario fictif', 'Surveillance fictive', 5, 5, NULL, NULL);
INSERT INTO MEDICAMENT (idMedicament, nomMedicament, forme, dosage) VALUES
(1, 'DemoCalm', 'Comprimé fictif', '500 mg fictifs'),
(2, 'DemoCard', 'Comprimé fictif', '5 mg fictifs'),
(3, 'DemoNasal', 'Solution fictive', '0,9 % fictif'),
(4, 'DemoDerm', 'Crème fictive', '1 % fictif'),
(5, 'DemoVita', 'Gélule fictive', '10 mg fictifs');
INSERT INTO PRESCRIRE (idConsultation, idMedicament, quantite, posologie, duree) VALUES
(1, 1, 6, 'Démo uniquement : une unité matin et soir', 3),
(2, 2, 7, 'Démo uniquement : une unité le matin', 7),
(3, 3, 1, 'Démo uniquement : application matin et soir', 3),
(4, 1, 4, 'Démo uniquement : une unité matin et soir', 2),
(5, 5, 7, 'Démo uniquement : une unité le matin', 7),
(6, 4, 1, 'Démo uniquement : application le soir', 5),
(1, 5, 3, 'Démo uniquement : une unité le matin', 3);

INSERT INTO CHAMBRE (idChambre, numeroChambre, typeChambre) VALUES
(1, '101', 'Individuelle'), (2, '102', 'Double'), (3, '103', 'Individuelle'),
(4, '201', 'Double'), (5, '202', 'Individuelle');
INSERT INTO LIT (idLit, numeroLit, idChambre) VALUES
(1, 'A', 1), (2, 'A', 2), (3, 'B', 2), (4, 'A', 3),
(5, 'A', 4), (6, 'B', 4), (7, 'A', 5);
-- Bed 1 is reused only after discharge; beds 3, 6 and 7 have no admissions.
INSERT INTO HOSPITALISATION (idHospitalisation, dateAdmission, dateSortie, idPatient, idLit) VALUES
(1, '2026-11-01 08:00:00', '2026-11-02 16:00:00', 1, 1),
(2, '2026-11-02 12:00:00', '2026-11-04 10:00:00', 2, 2),
(3, '2026-11-03 08:00:00', '2026-11-04 15:00:00', 4, 4),
(4, '2026-11-05 09:00:00', NULL, 5, 5),
(5, '2026-11-06 10:00:00', NULL, 6, 1);
INSERT INTO ACTE_MEDICAL (idActe, libelleActe, cout) VALUES
(1, 'Examen clinique fictif', 150.00), (2, 'ECG fictif', 250.00),
(3, 'Pansement fictif', 80.00), (4, 'Surveillance clinique fictive', 100.00),
(5, 'Avis médical fictif offert', 0.00);
INSERT INTO DESIGNER_RESPONSABLE (idHospitalisation, idActe, idMedecin) VALUES
(1, 1, 1), (2, 1, 2), (2, 2, 2), (3, 3, 4),
(4, 4, 5), (4, 5, 5), (5, 1, 1);
COMMIT;
