# MLD CLINIQ approuvé — transcription documentaire

Source : les 15 relations validées par le propriétaire du projet, cohérentes avec
`MCD_Clinique.png` et `database/01_schema.sql`. Cette transcription n'ajoute ni
attribut ni association. PK = clé primaire, FK = clé étrangère.

```text
SERVICE(idService PK, libelleService)
SPECIALITE(idSpecialite PK, libelleSpecialite)
MEDECIN(idMedecin PK, nom, prenom, telephone, idService FK NOT NULL)
EXERCER(idMedecin PK/FK, idSpecialite PK/FK)
PATIENT(idPatient PK, nom, prenom, dateNaissance, telephone, adresse)
RENDEZ_VOUS(idRDV PK, dateHeure, dureePrevue, statut, idPatient FK NOT NULL, idMedecin FK NOT NULL)
SALLE(idSalle PK, codeSalle)
CONSULTATION(idConsultation PK, dateHeure, motif, diagnostic, idPatient FK NOT NULL, idMedecin FK NOT NULL, idRDV FK NULL UNIQUE, idSalle FK NULL)
MEDICAMENT(idMedicament PK, nomMedicament, forme, dosage)
PRESCRIRE(idConsultation PK/FK, idMedicament PK/FK, quantite, posologie, duree)
CHAMBRE(idChambre PK, numeroChambre, typeChambre)
LIT(idLit PK, numeroLit, idChambre FK NOT NULL)
HOSPITALISATION(idHospitalisation PK, dateAdmission, dateSortie NULL, idPatient FK NOT NULL, idLit FK NOT NULL)
ACTE_MEDICAL(idActe PK, libelleActe, cout)
DESIGNER_RESPONSABLE(idHospitalisation PK/FK, idActe PK/FK, idMedecin FK NOT NULL)
```

Clés composées : EXERCER(idMedecin,idSpecialite),
PRESCRIRE(idConsultation,idMedicament),
DESIGNER_RESPONSABLE(idHospitalisation,idActe).
CIF : `(idHospitalisation,idActe) -> idMedecin` ; ne jamais ajouter idMedecin à la PK.
Unicité locale des lits : UNIQUE(idChambre,numeroLit).

La consultation peut n'avoir aucun RDV ; un RDV peut n'avoir aucune consultation
et au plus une. Les prescriptions sont des lignes d'association avec attributs,
non une entité PRESCRIPTION. DESIGNER_RESPONSABLE affecte une responsabilité,
sans stocker les exécutions répétées d'un acte.

Les minimums conceptuels médecin–spécialité (1,N) et chambre–lit (1,N) ne sont
pas entièrement exprimables par les seules FK de ce MLD. Cette limite connue
n'est pas une modification des cardinalités officielles.

Le fichier original éditable du MCD (outil de conception) n'a pas été fourni.
Seul le PNG officiel est présent ; ce document est la transcription du MLD,
pas une prétendue source originale du diagramme.
