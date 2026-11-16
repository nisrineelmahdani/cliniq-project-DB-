"""Real MySQL 8 constraint tests. Opt in explicitly; no existing DB is touched.

CLINIQ_RUN_MYSQL_TESTS=1 python -m pytest tests/test_schema_mysql.py -v -s
Uses only cliniq_test_dev; an exact reset confirmation is mandatory.
The database is never dropped. The approved schema/seed are restored per module.
"""

import os

import mysql.connector
from mysql.connector import errorcode
import pytest



COUNTS = {
    "SERVICE": 5, "SPECIALITE": 5, "MEDECIN": 5, "EXERCER": 6,
    "PATIENT": 7, "RENDEZ_VOUS": 8, "SALLE": 5, "CONSULTATION": 7,
    "MEDICAMENT": 5, "PRESCRIRE": 7, "CHAMBRE": 5, "LIT": 7,
    "HOSPITALISATION": 5, "ACTE_MEDICAL": 5, "DESIGNER_RESPONSABLE": 7,
}


@pytest.fixture(scope="module")
def database(request):
    if os.getenv("CLINIQ_RUN_MYSQL_TESTS") != "1":
        pytest.skip("Live MySQL not enabled: set CLINIQ_RUN_MYSQL_TESTS=1 and confirm the dedicated database reset")
    return request.getfixturevalue('dedicated_mysql_database')


@pytest.fixture
def connection(database):
    connection = database.connect()
    try:
        yield connection
    finally:
        connection.rollback()  # constraint probes never persist
        connection.close()


def scalar(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def test_exact_tables_storage_and_seed_counts(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT TABLE_NAME, ENGINE, TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")
        tables = cursor.fetchall()
    assert {row[0] for row in tables} == set(COUNTS)
    assert all(row[1:] == ('InnoDB', 'utf8mb4_0900_ai_ci') for row in tables)
    for table, count in COUNTS.items():
        assert scalar(connection, f"SELECT COUNT(*) FROM `{table}`") == count


def test_cif_primary_key_and_required_doctor(connection):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DESIGNER_RESPONSABLE'
            AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION""")
        assert cursor.fetchall() == [('idHospitalisation',), ('idActe',)]
    assert scalar(connection, """SELECT IS_NULLABLE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DESIGNER_RESPONSABLE'
        AND COLUMN_NAME = 'idMedecin'""") == 'NO'


@pytest.mark.parametrize("sql,params,errno", [
    ("INSERT INTO EXERCER VALUES (%s,%s)", (1, 1), errorcode.ER_DUP_ENTRY),
    ("INSERT INTO PRESCRIRE VALUES (%s,%s,%s,%s,%s)", (1, 1, 1, 'Démo', 1), errorcode.ER_DUP_ENTRY),
    ("INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)", (1, 1, 2), errorcode.ER_DUP_ENTRY),
    ("INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)", (1, 2, None), errorcode.ER_BAD_NULL_ERROR),
    ("INSERT INTO LIT (numeroLit,idChambre) VALUES (%s,%s)", ('A', 1), errorcode.ER_DUP_ENTRY),
    ("UPDATE CONSULTATION SET idRDV=%s,idPatient=%s,idMedecin=%s WHERE idConsultation=%s", (1, 1, 1, 6), errorcode.ER_DUP_ENTRY),
    ("INSERT INTO HOSPITALISATION (dateAdmission,dateSortie,idPatient,idLit) VALUES (%s,%s,%s,%s)",
     ('2026-12-02 10:00:00', '2026-12-01 10:00:00', 1, 7), errorcode.ER_CHECK_CONSTRAINT_VIOLATED),
    ("UPDATE HOSPITALISATION SET dateSortie=%s WHERE idHospitalisation=%s",
     ('2026-01-01 00:00:00', 4), errorcode.ER_CHECK_CONSTRAINT_VIOLATED),
    ("UPDATE RENDEZ_VOUS SET dureePrevue=%s WHERE idRDV=%s", (0, 1), errorcode.ER_CHECK_CONSTRAINT_VIOLATED),
    ("UPDATE PRESCRIRE SET quantite=%s WHERE idConsultation=%s AND idMedicament=%s", (0, 1, 1), errorcode.ER_CHECK_CONSTRAINT_VIOLATED),
    ("UPDATE PRESCRIRE SET duree=%s WHERE idConsultation=%s AND idMedicament=%s", (0, 1, 1), errorcode.ER_CHECK_CONSTRAINT_VIOLATED),
    ("UPDATE ACTE_MEDICAL SET cout=%s WHERE idActe=%s", (-1, 1), errorcode.ER_CHECK_CONSTRAINT_VIOLATED),
])
def test_constraints_reject_invalid_writes(connection, sql, params, errno):
    with connection.cursor() as cursor:
        with pytest.raises(mysql.connector.Error) as caught:
            cursor.execute(sql, params)
    assert caught.value.errno == errno


# One invalid FK probe for every FK in the approved MLD (17 in total).
FOREIGN_KEYS = [
    ('MEDECIN', 'idService'), ('EXERCER', 'idMedecin'), ('EXERCER', 'idSpecialite'),
    ('RENDEZ_VOUS', 'idPatient'), ('RENDEZ_VOUS', 'idMedecin'),
    ('CONSULTATION', 'idPatient'), ('CONSULTATION', 'idMedecin'),
    ('CONSULTATION', 'idRDV'), ('CONSULTATION', 'idSalle'),
    ('PRESCRIRE', 'idConsultation'), ('PRESCRIRE', 'idMedicament'),
    ('LIT', 'idChambre'), ('HOSPITALISATION', 'idPatient'), ('HOSPITALISATION', 'idLit'),
    ('DESIGNER_RESPONSABLE', 'idHospitalisation'), ('DESIGNER_RESPONSABLE', 'idActe'),
    ('DESIGNER_RESPONSABLE', 'idMedecin'),
]


@pytest.mark.parametrize('table,column', FOREIGN_KEYS)
def test_every_foreign_key_rejects_missing_parent(connection, table, column):
    with connection.cursor() as cursor:
        with pytest.raises(mysql.connector.Error) as caught:
            # Table/column names are fixed test constants; values are bound.
            # Use unlinked records so this probe isolates the FK, rather than
            # intentionally failing the separate cross-table ownership trigger.
            where = ''
            if column in ('idPatient', 'idMedecin'):
                if table == 'CONSULTATION':
                    where = ' WHERE idRDV IS NULL'
                elif table == 'RENDEZ_VOUS':
                    where = ' WHERE idRDV = 6'
            cursor.execute(f'UPDATE `{table}` SET `{column}` = %s{where} LIMIT 1', (999999,))
    assert caught.value.errno == errorcode.ER_NO_REFERENCED_ROW_2


def test_seed_foreign_keys_have_no_orphans(connection):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE()
            AND REFERENCED_TABLE_NAME IS NOT NULL""")
        keys = cursor.fetchall()
    assert len(keys) == len(FOREIGN_KEYS)
    for table, column, parent, pk in keys:
        assert scalar(connection, f"""SELECT COUNT(*) FROM `{table}` c LEFT JOIN `{parent}` p
            ON c.`{column}` = p.`{pk}` WHERE c.`{column}` IS NOT NULL AND p.`{pk}` IS NULL""") == 0


def test_seed_optionality_and_minimum_participation(connection):
    assert scalar(connection, "SELECT COUNT(*) FROM PATIENT p WHERE NOT EXISTS (SELECT 1 FROM RENDEZ_VOUS r WHERE r.idPatient=p.idPatient)") == 2
    assert scalar(connection, "SELECT COUNT(*) FROM CONSULTATION WHERE idRDV IS NULL") == 2
    assert scalar(connection, "SELECT COUNT(*) FROM CONSULTATION WHERE idSalle IS NULL") == 1
    assert scalar(connection, "SELECT COUNT(*) FROM MEDECIN m WHERE NOT EXISTS (SELECT 1 FROM EXERCER e WHERE e.idMedecin=m.idMedecin)") == 0
    assert scalar(connection, "SELECT COUNT(*) FROM CHAMBRE c WHERE NOT EXISTS (SELECT 1 FROM LIT l WHERE l.idChambre=c.idChambre)") == 0
    assert scalar(connection, "SELECT COUNT(*) FROM HOSPITALISATION WHERE dateSortie IS NULL") == 2


def test_seed_appointments_match_consultations(connection):
    assert scalar(connection, """SELECT COUNT(*) FROM CONSULTATION c JOIN RENDEZ_VOUS r ON c.idRDV=r.idRDV
        WHERE c.idPatient<>r.idPatient OR c.idMedecin<>r.idMedecin""") == 0


def test_seed_has_no_bed_or_patient_overlap(connection):
    # Half-open stays [admission, discharge); unknown discharge means still occupied.
    for key in ('idLit', 'idPatient'):
        assert scalar(connection, f"""SELECT COUNT(*) FROM HOSPITALISATION a JOIN HOSPITALISATION b
            ON a.`{key}`=b.`{key}` AND a.idHospitalisation<b.idHospitalisation
            WHERE (a.dateSortie IS NULL OR b.dateAdmission<a.dateSortie)
              AND (b.dateSortie IS NULL OR a.dateAdmission<b.dateSortie)""") == 0


def test_seed_has_no_doctor_appointment_overlap(connection):
    assert scalar(connection, """SELECT COUNT(*) FROM RENDEZ_VOUS a JOIN RENDEZ_VOUS b
        ON a.idMedecin=b.idMedecin AND a.idRDV<b.idRDV
        WHERE a.statut<>'Annulé' AND b.statut<>'Annulé'
        AND a.dateHeure<TIMESTAMPADD(MINUTE,b.dureePrevue,b.dateHeure)
        AND b.dateHeure<TIMESTAMPADD(MINUTE,a.dureePrevue,a.dateHeure)""") == 0


def test_valid_boundaries_and_optionality(connection):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE HOSPITALISATION SET dateSortie=dateAdmission WHERE idHospitalisation=4")
        cursor.execute("UPDATE ACTE_MEDICAL SET cout=0 WHERE idActe=1")
        cursor.execute("INSERT INTO CONSULTATION (dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV,idSalle) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       ('2026-12-01 09:00:00', 'Démo', 'Démo', 7, 1, None, None))
        # Same act/different stay and same stay/different act are allowed by CIF.
        cursor.execute("INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)", (1, 2, 2))
        cursor.execute("INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)", (3, 2, 2))
