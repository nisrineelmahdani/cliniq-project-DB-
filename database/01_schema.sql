-- CLINIQ / approved Phase 2 MLD. MySQL >= 8.0.16 (enforced CHECKs).
-- Select a NEW database before running. No CREATE DATABASE, USE, DROP or reset.
-- IDs are positive surrogate integers; explicit IDs in the seed are intentional.
-- Required descriptive values are NOT NULL; only approved optional FKs and
-- dateSortie are nullable. No unapproved uniqueness on names, phones or codes.
-- All FKs use RESTRICT: historical records cannot be silently cascaded away.
-- Status vocabulary is deliberately unrestricted pending approved business rules.
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE SERVICE (
    idService INT UNSIGNED NOT NULL AUTO_INCREMENT,
    libelleService VARCHAR(120) NOT NULL,
    CONSTRAINT pk_service PRIMARY KEY (idService)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE SPECIALITE (
    idSpecialite INT UNSIGNED NOT NULL AUTO_INCREMENT,
    libelleSpecialite VARCHAR(120) NOT NULL,
    CONSTRAINT pk_specialite PRIMARY KEY (idSpecialite)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE MEDECIN (
    idMedecin INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    telephone VARCHAR(30) NOT NULL,
    idService INT UNSIGNED NOT NULL,
    CONSTRAINT pk_medecin PRIMARY KEY (idMedecin),
    CONSTRAINT fk_medecin_service FOREIGN KEY (idService) REFERENCES SERVICE (idService) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE EXERCER (
    idMedecin INT UNSIGNED NOT NULL,
    idSpecialite INT UNSIGNED NOT NULL,
    CONSTRAINT pk_exercer PRIMARY KEY (idMedecin, idSpecialite),
    CONSTRAINT fk_exercer_medecin FOREIGN KEY (idMedecin) REFERENCES MEDECIN (idMedecin) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_exercer_specialite FOREIGN KEY (idSpecialite) REFERENCES SPECIALITE (idSpecialite) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE PATIENT (
    idPatient INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    dateNaissance DATE NOT NULL,
    telephone VARCHAR(30) NOT NULL,
    adresse VARCHAR(255) NOT NULL,
    CONSTRAINT pk_patient PRIMARY KEY (idPatient)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE RENDEZ_VOUS (
    idRDV INT UNSIGNED NOT NULL AUTO_INCREMENT,
    dateHeure DATETIME NOT NULL,
    dureePrevue SMALLINT UNSIGNED NOT NULL COMMENT 'Minutes',
    statut VARCHAR(40) NOT NULL,
    idPatient INT UNSIGNED NOT NULL,
    idMedecin INT UNSIGNED NOT NULL,
    CONSTRAINT pk_rendez_vous PRIMARY KEY (idRDV),
    CONSTRAINT ck_rdv_duree_positive CHECK (dureePrevue > 0),
    CONSTRAINT fk_rdv_patient FOREIGN KEY (idPatient) REFERENCES PATIENT (idPatient) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_rdv_medecin FOREIGN KEY (idMedecin) REFERENCES MEDECIN (idMedecin) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE SALLE (
    idSalle INT UNSIGNED NOT NULL AUTO_INCREMENT,
    codeSalle VARCHAR(30) NOT NULL,
    CONSTRAINT pk_salle PRIMARY KEY (idSalle)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE CONSULTATION (
    idConsultation INT UNSIGNED NOT NULL AUTO_INCREMENT,
    dateHeure DATETIME NOT NULL,
    motif TEXT NOT NULL,
    diagnostic TEXT NOT NULL,
    idPatient INT UNSIGNED NOT NULL,
    idMedecin INT UNSIGNED NOT NULL,
    idRDV INT UNSIGNED NULL,
    idSalle INT UNSIGNED NULL,
    CONSTRAINT pk_consultation PRIMARY KEY (idConsultation),
    -- UNIQUE permits multiple NULLs: walk-ins remain possible, but an appointment
    -- can lead to at most one consultation. Matching patient/doctor needs Phase 3.
    CONSTRAINT uq_consultation_rdv UNIQUE (idRDV),
    CONSTRAINT fk_consultation_patient FOREIGN KEY (idPatient) REFERENCES PATIENT (idPatient) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_consultation_medecin FOREIGN KEY (idMedecin) REFERENCES MEDECIN (idMedecin) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_consultation_rdv FOREIGN KEY (idRDV) REFERENCES RENDEZ_VOUS (idRDV) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_consultation_salle FOREIGN KEY (idSalle) REFERENCES SALLE (idSalle) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE MEDICAMENT (
    idMedicament INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nomMedicament VARCHAR(150) NOT NULL,
    forme VARCHAR(80) NOT NULL,
    dosage VARCHAR(80) NOT NULL,
    CONSTRAINT pk_medicament PRIMARY KEY (idMedicament)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE PRESCRIRE (
    idConsultation INT UNSIGNED NOT NULL,
    idMedicament INT UNSIGNED NOT NULL,
    quantite INT UNSIGNED NOT NULL COMMENT 'Nombre d unités délivrées',
    posologie VARCHAR(255) NOT NULL,
    duree SMALLINT UNSIGNED NOT NULL COMMENT 'Jours',
    CONSTRAINT pk_prescrire PRIMARY KEY (idConsultation, idMedicament),
    -- An actual prescription has a positive quantity and treatment duration.
    CONSTRAINT ck_prescrire_quantite_positive CHECK (quantite > 0),
    CONSTRAINT ck_prescrire_duree_positive CHECK (duree > 0),
    CONSTRAINT fk_prescrire_consultation FOREIGN KEY (idConsultation) REFERENCES CONSULTATION (idConsultation) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_prescrire_medicament FOREIGN KEY (idMedicament) REFERENCES MEDICAMENT (idMedicament) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE CHAMBRE (
    idChambre INT UNSIGNED NOT NULL AUTO_INCREMENT,
    numeroChambre VARCHAR(20) NOT NULL,
    typeChambre VARCHAR(80) NOT NULL,
    CONSTRAINT pk_chambre PRIMARY KEY (idChambre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE LIT (
    idLit INT UNSIGNED NOT NULL AUTO_INCREMENT,
    numeroLit VARCHAR(20) NOT NULL,
    idChambre INT UNSIGNED NOT NULL,
    CONSTRAINT pk_lit PRIMARY KEY (idLit),
    -- A bed number is unique within its chamber, not across the clinic.
    CONSTRAINT uq_lit_chambre_numero UNIQUE (idChambre, numeroLit),
    CONSTRAINT fk_lit_chambre FOREIGN KEY (idChambre) REFERENCES CHAMBRE (idChambre) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE HOSPITALISATION (
    idHospitalisation INT UNSIGNED NOT NULL AUTO_INCREMENT,
    dateAdmission DATETIME NOT NULL,
    dateSortie DATETIME NULL,
    idPatient INT UNSIGNED NOT NULL,
    idLit INT UNSIGNED NOT NULL,
    CONSTRAINT pk_hospitalisation PRIMARY KEY (idHospitalisation),
    -- NULL means no discharge recorded. Same-time discharge is allowed.
    CONSTRAINT ck_hospitalisation_dates CHECK (dateSortie IS NULL OR dateSortie >= dateAdmission),
    CONSTRAINT fk_hospitalisation_patient FOREIGN KEY (idPatient) REFERENCES PATIENT (idPatient) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_hospitalisation_lit FOREIGN KEY (idLit) REFERENCES LIT (idLit) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ACTE_MEDICAL (
    idActe INT UNSIGNED NOT NULL AUTO_INCREMENT,
    libelleActe VARCHAR(150) NOT NULL,
    cout DECIMAL(10,2) NOT NULL,
    CONSTRAINT pk_acte_medical PRIMARY KEY (idActe),
    -- Free acts are valid; negative costs are not.
    CONSTRAINT ck_acte_cout_nonnegative CHECK (cout >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE DESIGNER_RESPONSABLE (
    idHospitalisation INT UNSIGNED NOT NULL,
    idActe INT UNSIGNED NOT NULL,
    idMedecin INT UNSIGNED NOT NULL,
    -- CIF: (idHospitalisation, idActe) -> idMedecin.
    -- The doctor is mandatory but NEVER part of this primary key.
    CONSTRAINT pk_designer_responsable PRIMARY KEY (idHospitalisation, idActe),
    CONSTRAINT fk_responsable_hospitalisation FOREIGN KEY (idHospitalisation) REFERENCES HOSPITALISATION (idHospitalisation) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_responsable_acte FOREIGN KEY (idActe) REFERENCES ACTE_MEDICAL (idActe) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_responsable_medecin FOREIGN KEY (idMedecin) REFERENCES MEDECIN (idMedecin) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
