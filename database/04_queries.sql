-- CLINIQ DEV-008 : lectures pédagogiques uniquement, MySQL 8+.
-- Chaque bloc Qxx est autonome et fonctionne sur le schéma officiel.
-- Aucun INSERT/UPDATE/DELETE, aucune création d'entité, aucun chiffre simulé.

-- Q01 : sélectionner les patients nés avant 2000, puis trier les identités.
-- Concepts : projection, sélection (WHERE), tri stable (ORDER BY).
SELECT idPatient,nom,prenom,dateNaissance
FROM PATIENT WHERE dateNaissance < '2000-01-01'
ORDER BY nom,prenom,idPatient;

-- Q02 : afficher les rendez-vous avec leur patient et leur médecin.
-- Concepts : deux jointures internes et sélection des attributs utiles.
SELECT r.idRDV,r.dateHeure,r.dureePrevue,r.statut,
       p.idPatient,CONCAT(p.nom,' ',p.prenom) AS patient,
       m.idMedecin,CONCAT(m.nom,' ',m.prenom) AS medecin
FROM RENDEZ_VOUS r JOIN PATIENT p ON p.idPatient=r.idPatient
JOIN MEDECIN m ON m.idMedecin=r.idMedecin
ORDER BY r.dateHeure,r.idRDV;

-- Q03 : retrouver les patients sans aucun rendez-vous, même s'ils ont consulté.
-- Concepts : jointure externe gauche et anti-jointure par IS NULL.
SELECT p.idPatient,p.nom,p.prenom
FROM PATIENT p LEFT JOIN RENDEZ_VOUS r ON r.idPatient=p.idPatient
WHERE r.idRDV IS NULL ORDER BY p.idPatient;

-- Q04 : compter les consultations par médecin, y compris une activité nulle.
-- Concepts : LEFT JOIN, GROUP BY, COUNT d'une clé nullable après jointure.
SELECT m.idMedecin,m.nom,m.prenom,COUNT(c.idConsultation) AS consultations
FROM MEDECIN m LEFT JOIN CONSULTATION c ON c.idMedecin=m.idMedecin
GROUP BY m.idMedecin,m.nom,m.prenom ORDER BY consultations DESC,m.idMedecin;

-- Q05 : ne conserver que les médecins ayant au moins deux consultations.
-- Concepts : agrégation puis filtrage des groupes avec HAVING.
SELECT m.idMedecin,m.nom,m.prenom,COUNT(c.idConsultation) AS consultations
FROM MEDECIN m LEFT JOIN CONSULTATION c ON c.idMedecin=m.idMedecin
GROUP BY m.idMedecin,m.nom,m.prenom
HAVING COUNT(c.idConsultation)>=2 ORDER BY consultations DESC,m.idMedecin;

-- Q06 : identifier les médecins dont l'activité dépasse la moyenne de TOUS les médecins.
-- Concepts : sous-requête dérivée, AVG et sous-requête corrélée ; zéro compris.
SELECT m.idMedecin,m.nom,m.prenom,
       (SELECT COUNT(*) FROM CONSULTATION c WHERE c.idMedecin=m.idMedecin) AS consultations
FROM MEDECIN m
WHERE (SELECT COUNT(*) FROM CONSULTATION c WHERE c.idMedecin=m.idMedecin) >
      (SELECT AVG(effectif.nombre) FROM
          (SELECT med.idMedecin,COUNT(con.idConsultation) AS nombre
           FROM MEDECIN med LEFT JOIN CONSULTATION con ON con.idMedecin=med.idMedecin
           GROUP BY med.idMedecin) AS effectif)
ORDER BY consultations DESC,m.idMedecin;

-- Q07 : reconstruire l'historique des séjours, du patient au lit et à sa chambre.
-- Concepts : jointures internes 1:N successives et sortie facultative conservée.
SELECT h.idHospitalisation,h.idPatient,CONCAT(p.nom,' ',p.prenom) AS patient,
       h.dateAdmission,h.dateSortie,ch.numeroChambre,l.numeroLit
FROM HOSPITALISATION h JOIN PATIENT p ON p.idPatient=h.idPatient
JOIN LIT l ON l.idLit=h.idLit JOIN CHAMBRE ch ON ch.idChambre=l.idChambre
ORDER BY h.idPatient,h.dateAdmission,h.idHospitalisation;

-- Q08 : lire les médicaments d'une consultation et les attributs de PRESCRIRE.
-- Concepts : association N:N à clé composée ; attributs portés par l'association.
SELECT c.idConsultation,c.idPatient,c.dateHeure,m.idMedicament,
       m.nomMedicament,m.forme,m.dosage,rx.quantite,rx.posologie,rx.duree
FROM CONSULTATION c JOIN PRESCRIRE rx ON rx.idConsultation=c.idConsultation
JOIN MEDICAMENT m ON m.idMedicament=rx.idMedicament
ORDER BY c.idConsultation,m.idMedicament;

-- Q09 : expliciter la ternaire et sa CIF, sans compter des réalisations répétées.
-- Concepts : DESIGNER_RESPONSABLE relie séjour, type d'acte et médecin ;
-- (idHospitalisation,idActe) détermine un seul idMedecin, hors clé primaire.
SELECT d.idHospitalisation,h.idPatient,CONCAT(p.nom,' ',p.prenom) AS patient,
       d.idActe,a.libelleActe,d.idMedecin,CONCAT(m.nom,' ',m.prenom) AS responsable
FROM DESIGNER_RESPONSABLE d
JOIN HOSPITALISATION h ON h.idHospitalisation=d.idHospitalisation
JOIN PATIENT p ON p.idPatient=h.idPatient
JOIN ACTE_MEDICAL a ON a.idActe=d.idActe JOIN MEDECIN m ON m.idMedecin=d.idMedecin
ORDER BY d.idHospitalisation,d.idActe;

-- Q10 : classer les médecins selon leur nombre de consultations.
-- Concepts : CTE, agrégation, DENSE_RANK ; les ex aequo ont le même rang.
WITH activite AS (
    SELECT m.idMedecin,COUNT(c.idConsultation) AS consultations
    FROM MEDECIN m LEFT JOIN CONSULTATION c ON c.idMedecin=m.idMedecin
    GROUP BY m.idMedecin
)
SELECT idMedecin,consultations,DENSE_RANK() OVER(ORDER BY consultations DESC) AS rang
FROM activite ORDER BY rang,idMedecin;

-- Q11 : calculer l'activité quotidienne et son cumul chronologique.
-- Concepts : CTE, GROUP BY DATE et SUM OVER ; seuls les jours réellement observés.
WITH quotidien AS (
    SELECT DATE(dateHeure) AS jour,COUNT(*) AS consultations
    FROM CONSULTATION GROUP BY DATE(dateHeure)
)
SELECT jour,consultations,SUM(consultations) OVER(ORDER BY jour ROWS UNBOUNDED PRECEDING) AS cumul
FROM quotidien ORDER BY jour;

-- Q12 : état des lits au 16 novembre 2026 à midi (instant fixe, résultat reproductible).
-- Concepts : CTE, DISTINCT, LEFT JOIN et agrégats ; admission incluse, sortie exclue.
WITH occupes AS (
    SELECT DISTINCT idLit FROM HOSPITALISATION
    WHERE dateAdmission<='2026-11-16 12:00:00'
      AND (dateSortie IS NULL OR dateSortie>'2026-11-16 12:00:00')
)
SELECT ch.idChambre,ch.numeroChambre,COUNT(l.idLit) AS lits,
       COUNT(o.idLit) AS occupes,COUNT(l.idLit)-COUNT(o.idLit) AS disponibles
FROM CHAMBRE ch LEFT JOIN LIT l ON l.idChambre=ch.idChambre
LEFT JOIN occupes o ON o.idLit=l.idLit
GROUP BY ch.idChambre,ch.numeroChambre ORDER BY ch.idChambre;
