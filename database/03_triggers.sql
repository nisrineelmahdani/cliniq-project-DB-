-- CLINIQ DEV-008 : une règle métier inter-table, implémentée par trois triggers.
-- Une consultation liée à un RDV doit garder le même patient ET le même médecin.
-- Les FK/UNIQUE ne comparent pas ces deux couples : ce n'est pas un doublon de CHECK.
-- FOR SHARE fait une lecture courante et conserve le verrou jusqu'à COMMIT/ROLLBACK.
-- La garde réciproque interdit qu'un RDV modifié rende une consultation incohérente.
-- Aucun COMMIT, DDL, transaction autonome, nouveau champ ou changement de clé.
-- Création volontairement non idempotente : ne jamais remplacer un trigger existant
-- sans revue. Aucun DROP ni DEFINER de compte n'est imposé par ce script.
-- Voir docs/sql_validation.md : limites MySQL du trigger d'occupation écarté.

DELIMITER $$

CREATE TRIGGER trg_consultation_rdv_bi
BEFORE INSERT ON CONSULTATION FOR EACH ROW
BEGIN
    DECLARE v_patient INT UNSIGNED DEFAULT NULL;
    DECLARE v_medecin INT UNSIGNED DEFAULT NULL;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_patient = NULL;
    IF NEW.idRDV IS NOT NULL THEN
        SELECT idPatient,idMedecin INTO v_patient,v_medecin
        FROM RENDEZ_VOUS WHERE idRDV=NEW.idRDV FOR SHARE;
        -- L'absence du parent reste du ressort de la FK existante (erreur 1452).
        IF v_patient IS NOT NULL AND
           (NEW.idPatient<>v_patient OR NEW.idMedecin<>v_medecin) THEN
            SIGNAL SQLSTATE '45000' SET MYSQL_ERRNO=1644,
                MESSAGE_TEXT='CLINIQ: patient et medecin doivent correspondre au rendez-vous lie.';
        END IF;
    END IF;
END$$

CREATE TRIGGER trg_consultation_rdv_bu
BEFORE UPDATE ON CONSULTATION FOR EACH ROW
BEGIN
    DECLARE v_patient INT UNSIGNED DEFAULT NULL;
    DECLARE v_medecin INT UNSIGNED DEFAULT NULL;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_patient = NULL;
    IF NEW.idRDV IS NOT NULL THEN
        SELECT idPatient,idMedecin INTO v_patient,v_medecin
        FROM RENDEZ_VOUS WHERE idRDV=NEW.idRDV FOR SHARE;
        IF v_patient IS NOT NULL AND
           (NEW.idPatient<>v_patient OR NEW.idMedecin<>v_medecin) THEN
            SIGNAL SQLSTATE '45000' SET MYSQL_ERRNO=1644,
                MESSAGE_TEXT='CLINIQ: patient et medecin doivent correspondre au rendez-vous lie.';
        END IF;
    END IF;
END$$

CREATE TRIGGER trg_rdv_consultation_bu
BEFORE UPDATE ON RENDEZ_VOUS FOR EACH ROW
BEGIN
    DECLARE v_consultation INT UNSIGNED DEFAULT NULL;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_consultation = NULL;
    IF NEW.idPatient<>OLD.idPatient OR NEW.idMedecin<>OLD.idMedecin THEN
        SELECT idConsultation INTO v_consultation
        FROM CONSULTATION WHERE idRDV=OLD.idRDV
          AND (idPatient<>NEW.idPatient OR idMedecin<>NEW.idMedecin)
        LIMIT 1 FOR SHARE;
        IF v_consultation IS NOT NULL THEN
            SIGNAL SQLSTATE '45000' SET MYSQL_ERRNO=1644,
                MESSAGE_TEXT='CLINIQ: modification du rendez-vous incompatible avec sa consultation.';
        END IF;
    END IF;
END$$

DELIMITER ;

-- Exemples reproductibles sur le SEED, à exécuter séparément dans une transaction.
-- Valide : RDV 6 appartient au patient 1 et au médecin 1, sans consultation liée.
-- START TRANSACTION;
-- INSERT INTO CONSULTATION (dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV,idSalle)
-- VALUES ('2026-11-20 09:00:00','Exemple fictif','Exemple fictif',1,1,6,NULL);
-- ROLLBACK;
-- Invalide : le patient 2 diffère du patient 1 du RDV 6.
-- INSERT INTO CONSULTATION (dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV,idSalle)
-- VALUES ('2026-11-20 09:00:00','Exemple fictif','Exemple fictif',2,1,6,NULL);
-- Attendu : ERROR 1644, SQLSTATE 45000 ; aucune ligne n'est insérée.
-- Invalide réciproque : UPDATE RENDEZ_VOUS SET idPatient=2 WHERE idRDV=1;
-- Attendu : ERROR 1644, SQLSTATE 45000 (consultation 1 déjà liée).
