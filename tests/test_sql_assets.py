"""Offline fixture checks; these do not validate MySQL SQL syntax or enforcement."""

import ast
from pathlib import Path
import re
from unittest.mock import MagicMock, patch

import pytest

from database.setup import connection_options, provision
from tests.test_schema_mysql import COUNTS, FOREIGN_KEYS


ROOT = Path(__file__).resolve().parents[1] / 'database'


def seed_rows():
    """Read this seed's restricted literals (strings, numbers, NULL), not general SQL."""
    sql = re.sub(r'--[^\n]*', '', (ROOT / '02_seed.sql').read_text())
    result = {}
    for table, columns, values in re.findall(r'INSERT INTO (\w+)\s*\(([^)]+)\)\s*VALUES\s*(.*?);', sql, re.S):
        # Our fictional strings contain no SQL escaped quotes or SQL expressions.
        tree = ast.parse('[' + values + ']', mode='eval')
        class NullLiteral(ast.NodeTransformer):
            def visit_Name(self, node):
                assert node.id == 'NULL'
                return ast.Constant(value=None)

        rows = ast.literal_eval(NullLiteral().visit(tree))
        result[table] = [dict(zip([c.strip() for c in columns.split(',')], row, strict=True)) for row in rows]
    return result


def test_exact_approved_tables_columns_and_composite_keys():
    sql = (ROOT / '01_schema.sql').read_text()
    tables = dict(re.findall(r'CREATE TABLE (\w+) \((.*?)\) ENGINE=', sql, re.S))
    expected = {
        'SERVICE': 'idService libelleService',
        'SPECIALITE': 'idSpecialite libelleSpecialite',
        'MEDECIN': 'idMedecin nom prenom telephone idService',
        'EXERCER': 'idMedecin idSpecialite',
        'PATIENT': 'idPatient nom prenom dateNaissance telephone adresse',
        'RENDEZ_VOUS': 'idRDV dateHeure dureePrevue statut idPatient idMedecin',
        'SALLE': 'idSalle codeSalle',
        'CONSULTATION': 'idConsultation dateHeure motif diagnostic idPatient idMedecin idRDV idSalle',
        'MEDICAMENT': 'idMedicament nomMedicament forme dosage',
        'PRESCRIRE': 'idConsultation idMedicament quantite posologie duree',
        'CHAMBRE': 'idChambre numeroChambre typeChambre',
        'LIT': 'idLit numeroLit idChambre',
        'HOSPITALISATION': 'idHospitalisation dateAdmission dateSortie idPatient idLit',
        'ACTE_MEDICAL': 'idActe libelleActe cout',
        'DESIGNER_RESPONSABLE': 'idHospitalisation idActe idMedecin',
    }
    assert set(tables) == set(expected)
    for name, columns in expected.items():
        actual = re.findall(r'^    (\w+) (?:INT|VARCHAR|DATE|SMALLINT|TEXT|DECIMAL)', tables[name], re.M)
        assert actual == columns.split()
    for table, key in [('EXERCER', 'idMedecin, idSpecialite'),
                       ('PRESCRIRE', 'idConsultation, idMedicament'),
                       ('DESIGNER_RESPONSABLE', 'idHospitalisation, idActe')]:
        assert re.search(r'PRIMARY KEY \(' + key + r'\)', tables[table])
    assert 'UNIQUE (idChambre, numeroLit)' in tables['LIT']
    assert 'UNIQUE (idRDV)' in tables['CONSULTATION']


def test_seed_counts_keys_fk_consistency_and_insertion_order():
    rows = seed_rows()
    assert {table: len(data) for table, data in rows.items()} == COUNTS
    schema = (ROOT / '01_schema.sql').read_text()
    tables = dict(re.findall(r'CREATE TABLE (\w+) \((.*?)\) ENGINE=', schema, re.S))
    seen = set()
    actual_fks = []
    for table, records in rows.items():
        pk = re.search(r'PRIMARY KEY \(([^)]+)\)', tables[table]).group(1).split(', ')
        keys = [tuple(row[column] for column in pk) for row in records]
        assert len(set(keys)) == len(keys), table
        for column, parent, parent_key in re.findall(r'FOREIGN KEY \((\w+)\) REFERENCES (\w+) \((\w+)\)', tables[table]):
            assert parent in seen, (table, parent)
            parents = {row[parent_key] for row in rows[parent]}
            assert all(row[column] is None or row[column] in parents for row in records)
            actual_fks.append((table, column))
        seen.add(table)
    assert set(actual_fks) == set(FOREIGN_KEYS)


def test_seed_optional_links_and_cross_table_coherence():
    rows = seed_rows()
    appointments = {r['idRDV']: r for r in rows['RENDEZ_VOUS']}
    assert {p['idPatient'] for p in rows['PATIENT']} - {r['idPatient'] for r in appointments.values()} == {6, 7}
    assert sum(c['idRDV'] is None for c in rows['CONSULTATION']) == 2
    for consultation in rows['CONSULTATION']:
        if consultation['idRDV'] is not None:
            appointment = appointments[consultation['idRDV']]
            assert all(consultation[k] == appointment[k] for k in ('idPatient', 'idMedecin'))
    for stay in rows['HOSPITALISATION']:
        assert stay['dateSortie'] is None or stay['dateSortie'] >= stay['dateAdmission']
    for i, a in enumerate(rows['HOSPITALISATION']):
        for b in rows['HOSPITALISATION'][i + 1:]:
            if a['idLit'] == b['idLit'] or a['idPatient'] == b['idPatient']:
                assert (a['dateSortie'] is not None and a['dateSortie'] <= b['dateAdmission']) or (b['dateSortie'] is not None and b['dateSortie'] <= a['dateAdmission'])
    for table, key, link in [('MEDECIN', 'idMedecin', 'EXERCER'), ('CHAMBRE', 'idChambre', 'LIT')]:
        assert {r[key] for r in rows[table]} <= {r[key] for r in rows[link]}


def test_dev008_assets_preserve_schema_and_define_only_bounded_extensions():
    triggers = re.sub(r'--[^\n]*', '', (ROOT / '03_triggers.sql').read_text())
    indexes = re.sub(r'--[^\n]*', '', (ROOT / '05_indexes.sql').read_text())
    queries = (ROOT / '04_queries.sql').read_text()
    assert len(re.findall(r'CREATE TRIGGER ', triggers)) == 3
    assert len(re.findall(r'CREATE INDEX ', indexes)) == 2
    assert len(re.findall(r'^-- Q\d{2} :', queries, re.M)) == 12
    for sql in (triggers, indexes):
        assert not re.search(r'\b(?:DROP|CREATE TABLE|ALTER TABLE|USE)\b', sql, re.I)


def test_setup_requires_separate_credentials(monkeypatch):
    monkeypatch.delenv('CLINIQ_TEST_USER', raising=False)
    monkeypatch.setenv('MYSQL_USER', 'existing_application_user')
    with patch('database.setup.load_dotenv'):
        with pytest.raises(ValueError, match='CLINIQ_TEST_USER'):
            connection_options('test')


def test_database_creation_collision_never_runs_scripts():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ('8.0.40',)
    import mysql.connector
    cursor.execute.side_effect = [None, None, mysql.connector.Error('already exists', errno=1007)]
    with patch('database.setup.connection_options', return_value={}), patch('database.setup.mysql.connector.connect', return_value=connection), patch('database.setup.run_script') as run:
        with pytest.raises(mysql.connector.Error):
            provision('test')
    run.assert_not_called()
    create = cursor.execute.call_args.args[0]
    assert re.fullmatch(r'CREATE DATABASE `cliniq_test_[0-9a-f]{32}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci', create)
    connection.close.assert_called_once()


def test_failed_seed_rolls_back_and_retains_database():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ('8.0.40',)
    with patch('database.setup.connection_options', return_value={}), patch('database.setup.mysql.connector.connect', return_value=connection), patch('database.setup.run_script', side_effect=[None, RuntimeError('seed failed')]):
        with pytest.raises(RuntimeError, match='seed failed'):
            provision('dev')
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    assert not any('DROP' in call.args[0] for call in cursor.execute.call_args_list)
    connection.close.assert_called_once()
