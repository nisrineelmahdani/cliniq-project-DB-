-- CLINIQ DEV-008 : uniquement des index secondaires, aucune clé métier modifiée.
-- Exécuter APRÈS inspection de SHOW INDEX et validation sur la base de test.
-- Pas de DROP INDEX ni IF NOT EXISTS : une seconde installation échoue clairement.
-- Les EXPLAIN réellement relevés avant/après figurent dans docs/sql_validation.md
-- et docs/sql_evidence.json. Ne pas appliquer en développement sans approbation.

-- I01 : agenda d'un médecin sur une période : idMedecin = ? et intervalle dateHeure.
-- L'ancien index FK (idMedecin) ne couvre pas le second prédicat ni le tri temporel.
-- Le PK idRDV est déjà ajouté implicitement par InnoDB : inutile de le répéter.
-- L'index FK simple peut être supprimé implicitement par InnoDB si celui-ci le couvre ;
-- la contrainte FK reste identique. Aucun index PK/UNIQUE existant n'est dupliqué.
CREATE INDEX idx_rdv_medecin_dateheure ON RENDEZ_VOUS (idMedecin,dateHeure);

-- I02 : consultations récentes du dashboard : dateHeure <= ? puis tri DESC et LIMIT.
-- Aucun index existant ne commence par dateHeure. Le PK idConsultation, implicite,
-- permet aussi le départage stable. Le choix effectif reste celui de l'optimiseur.
CREATE INDEX idx_consultation_dateheure ON CONSULTATION (dateHeure);

-- Coût : espace disque/mémoire, écritures d'index sur INSERT/DELETE et sur les UPDATE
-- des colonnes indexées. Ces index ne rendent pas sargable la recherche LOCATE('%...').
-- Ils ne constituent ni une preuve de gain temporel ni une contrainte supplémentaire.
