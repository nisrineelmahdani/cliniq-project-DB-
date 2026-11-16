# Controlled DEV-008 development installation — 16 November 2026

Explicit user authorization limited installation to existing `cliniq_db`.
No schema setup, seed import, database reset, record deletion or global setting
change was executed against development. The approved SQL files were unchanged.

## Preflight and backup

- Actual selected database: `cliniq_db`, server version 26.10.0.
- 15 original tables; 89 records. No existing triggers, conflicting index names,
  equivalent index prefixes or inconsistent consultation/appointment links.
- Scripts inspected: only the three approved CREATE TRIGGER statements and two
  approved CREATE INDEX statements. The commented examples were not executed.
- Binary logging enabled and trust setting already 1; no SET GLOBAL executed.
- Full logical backup completed before DDL, with single-transaction snapshot,
  routines/events/triggers included, no table locks and no DROP TABLE statements.
- Private backup (directory mode 0700, file mode 0600):
  `/private/tmp/cliniq_db_backup_vw4lj4mr/cliniq_db_before_dev008.sql`
- Size: 19267 bytes; SHA-256: `51465ac5bc35f753d2bf06105f6786b591d4c5dead9685613441df4d789b92f4`.
  This backup contains database records: retain it securely and copy it to a
  durable private backup location, since the operating system can purge /tmp.
  The dump completed successfully; no restoration drill was performed.

## Changes actually applied

Via the mysql client, stopping on errors, in this order:

1. `database/03_triggers.sql`:
   - `trg_consultation_rdv_bi` — BEFORE INSERT CONSULTATION.
   - `trg_consultation_rdv_bu` — BEFORE UPDATE CONSULTATION.
   - `trg_rdv_consultation_bu` — BEFORE UPDATE RENDEZ_VOUS.
2. `database/05_indexes.sql`:
   - `idx_rdv_medecin_dateheure` — RENDEZ_VOUS(idMedecin,dateHeure), nonunique.
   - `idx_consultation_dateheure` — CONSULTATION(dateHeure), nonunique.

InnoDB absorbed the redundant single-column supporting index `fk_rdv_medecin`;
the doctor FK itself is unchanged. Remaining RENDEZ_VOUS indexes are PRIMARY,
fk_rdv_patient and idx_rdv_medecin_dateheure. No DROP INDEX was executed.
DDL commits implicitly; no rollback of installed DDL was attempted or needed.
No installation errors occurred. No unrelated application code was changed.

## Verification results

- Three trigger names, event tables/timings and both nonunique index column
  sequences verified through actual metadata queries.
- Before/after and post-regression comparisons: **all 15 table contents match**
  via row counts and canonical SHA-256 hashes; all column definitions and original
  PK/UNIQUE/FK column relationships match. Existing 89 records remain intact.
- Direct SQL invalid INSERT, patient/doctor consultation UPDATE and parent RDV
  UPDATE rejected with **1644 / SQLSTATE 45000**. These expected rejection errors
  demonstrate all three installed guards. The INSERT used an explicit existing
  ID, avoiding auto-increment allocation; BEFORE trigger rejected ownership first.
- Duplicate DESIGNER_RESPONSABLE pair rejected with **1062 / SQLSTATE 23000**.
  Its PK remains exactly (idHospitalisation,idActe); doctor remains a mandatory FK.
- Valid consultation UPDATE succeeded, was observed inside its transaction, then
  rolled back. No verification record was retained.
- Unchanged application dashboard/patient repositories read successfully using
  the configured application connection. The patient update repository performed
  an observable real write under a rollback-only transaction wrapper; it was
  rolled back. No production commit or UI automation was needed for this SQL-only
  installation. Full workflow tests cover normal commit/persistence in isolation.
- Complete regression on **cliniq_test_dev only**, with extensions enabled:
  **418 passed, 0 failed, 0 errors, 0 skipped** in 15.48 seconds, including
  **135 live MySQL cases**. No development reset was executed.

The existing temporal-overlap limitations and server-version qualification in
`sql_validation.md` remain unchanged. The owner may now restore the original
`log_bin_trust_function_creators` value; installed triggers remain, while future
trigger creation must again satisfy the administrator's server policy.

Repository file changed for this installation: only this installation report.
Temporary private runner scripts and evidence were kept outside the repository.
