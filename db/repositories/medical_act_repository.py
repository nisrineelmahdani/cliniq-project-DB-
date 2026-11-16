"""Responsibility assignments for the approved ternary CIF; no execution records."""

import mysql.connector
from mysql.connector import errorcode

from db.repositories.common import ConcurrentEditError, RepositoryError, database_cursor


PAGE_SIZE = 25
CONTEXT_FIELDS = ('idPatient','idLit','dateAdmission','dateSortie')
JOIN_SQL = '''FROM DESIGNER_RESPONSABLE d
    JOIN HOSPITALISATION h ON h.idHospitalisation=d.idHospitalisation
    JOIN PATIENT p ON p.idPatient=h.idPatient
    JOIN ACTE_MEDICAL a ON a.idActe=d.idActe
    JOIN MEDECIN m ON m.idMedecin=d.idMedecin'''
PROJECTION = "d.idHospitalisation,d.idActe,d.idMedecin,h.idPatient,h.dateAdmission,h.dateSortie,CONCAT(p.nom,' ',p.prenom) AS patient,a.libelleActe,a.cout,CONCAT(m.nom,' ',m.prenom) AS medecin"


class AssignmentError(RepositoryError):
    """Controlled, non-identifying assignment feedback."""


class CIFViolationError(AssignmentError):
    """The existing hospitalization–act pair already determines one doctor."""


CIF_MESSAGE = ('CIF : ce couple hospitalisation–acte possède déjà un médecin responsable. '
               'La clé primaire (idHospitalisation, idActe) interdit une seconde ligne, '
               'même avec un autre médecin. Utilisez « Réaffecter » pour modifier la responsabilité.')


def hospitalizations(patient=None):
    with database_cursor(readonly=True) as cursor:
        cursor.execute("""SELECT h.*,CONCAT(p.nom,' ',p.prenom) AS patient,
            CONCAT('Séjour ',h.idHospitalisation,' · ',p.nom,' ',p.prenom,' · ',DATE_FORMAT(h.dateAdmission,'%d/%m/%Y')) AS label
            FROM HOSPITALISATION h JOIN PATIENT p ON p.idPatient=h.idPatient
            WHERE (%s IS NULL OR h.idPatient=%s) ORDER BY h.dateAdmission DESC,h.idHospitalisation DESC""", (patient,patient))
        return cursor.fetchall()


def filter_options():
    with database_cursor(readonly=True) as cursor:
        cursor.execute("SELECT idPatient,CONCAT(nom,' ',prenom) AS label FROM PATIENT ORDER BY nom,prenom,idPatient")
        patients = cursor.fetchall()
        cursor.execute("SELECT idMedecin,CONCAT(nom,' ',prenom) AS label FROM MEDECIN ORDER BY nom,prenom,idMedecin")
        doctors = cursor.fetchall()
        cursor.execute('SELECT idActe,libelleActe AS label FROM ACTE_MEDICAL ORDER BY libelleActe,idActe')
        acts = cursor.fetchall()
    return dict(patients=patients,doctors=doctors,acts=acts)


def list_acts(search='', *, page=0):
    where = "LOCATE(%s,CONCAT_WS(' ',idActe,libelleActe))>0"
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total FROM ACTE_MEDICAL WHERE {where}',(search.strip(),))
        total = cursor.fetchone()['total']
        page = min(max(0,page),max(0,(total-1)//PAGE_SIZE))
        cursor.execute(f'SELECT idActe,libelleActe,cout FROM ACTE_MEDICAL WHERE {where} ORDER BY libelleActe,idActe LIMIT %s OFFSET %s',(search.strip(),PAGE_SIZE,page*PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows,total=total,page=page)


def list_assignments(search='', *, patient=None, hospitalization=None, act=None, doctor=None, page=0):
    clauses = ["LOCATE(%s,CONCAT_WS(' ',d.idHospitalisation,d.idActe,p.nom,p.prenom,a.libelleActe,m.nom,m.prenom))>0"]
    params = [search.strip()]
    for column,value in [('h.idPatient',patient),('d.idHospitalisation',hospitalization),('d.idActe',act),('d.idMedecin',doctor)]:
        if value is not None:
            clauses.append(f'{column}=%s')
            params.append(value)
    where = ' AND '.join(clauses)
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total {JOIN_SQL} WHERE {where}',tuple(params))
        total = cursor.fetchone()['total']
        page = min(max(0,page),max(0,(total-1)//PAGE_SIZE))
        cursor.execute(f'SELECT {PROJECTION} {JOIN_SQL} WHERE {where} ORDER BY h.dateAdmission DESC,d.idHospitalisation,d.idActe LIMIT %s OFFSET %s',(*params,PAGE_SIZE,page*PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows,total=total,page=page)


def hospitalization_detail(hospitalization_id):
    with database_cursor(readonly=True) as cursor:
        cursor.execute("""SELECT h.*,CONCAT(p.nom,' ',p.prenom) AS patient,ch.numeroChambre,l.numeroLit
            FROM HOSPITALISATION h JOIN PATIENT p ON p.idPatient=h.idPatient
            JOIN LIT l ON l.idLit=h.idLit JOIN CHAMBRE ch ON ch.idChambre=l.idChambre
            WHERE h.idHospitalisation=%s""",(hospitalization_id,))
        hospitalization = cursor.fetchone()
        if hospitalization is None:
            raise AssignmentError('Ce séjour n’est plus disponible. Actualisez les listes.')
        cursor.execute(f'SELECT {PROJECTION} {JOIN_SQL} WHERE d.idHospitalisation=%s ORDER BY a.libelleActe,d.idActe',(hospitalization_id,))
        assignments = cursor.fetchall()
    return dict(hospitalization=hospitalization,assignments=assignments)


def _lock_parents(cursor,hospitalization_id,act_id,doctor_ids,context):
    # Shared doctor locks protect FK parents without serializing one doctor's
    # independent assignments. Hospitalization parent is the pair-creation mutex.
    for doctor_id in sorted(set(doctor_ids)):
        cursor.execute('SELECT idMedecin FROM MEDECIN WHERE idMedecin=%s FOR SHARE',(doctor_id,))
        if cursor.fetchone() is None:
            raise AssignmentError('Le médecin sélectionné n’est plus disponible.')
    cursor.execute('SELECT * FROM HOSPITALISATION WHERE idHospitalisation=%s FOR UPDATE',(hospitalization_id,))
    current = cursor.fetchone()
    if current is None:
        raise AssignmentError('Ce séjour n’est plus disponible.')
    if any(current[key]!=context[key] for key in CONTEXT_FIELDS):
        raise ConcurrentEditError('Le séjour a changé. Rechargez son contexte avant de modifier les responsabilités.')
    cursor.execute('SELECT idActe FROM ACTE_MEDICAL WHERE idActe=%s FOR SHARE',(act_id,))
    if cursor.fetchone() is None:
        raise AssignmentError('Ce type d’acte médical n’est plus disponible.')


def _lock_pair(cursor,hospitalization_id,act_id):
    cursor.execute('SELECT idHospitalisation,idActe,idMedecin FROM DESIGNER_RESPONSABLE WHERE idHospitalisation=%s AND idActe=%s FOR UPDATE',(hospitalization_id,act_id))
    return cursor.fetchone()


def _check_original(current,original):
    if current is None:
        raise AssignmentError('Cette affectation n’existe plus. Actualisez la liste.')
    if current['idMedecin']!=original['idMedecin']:
        raise ConcurrentEditError('Le médecin responsable a changé. Rechargez l’affectation avant de réessayer.')


def _execute_write(cursor,sql,params):
    try:
        cursor.execute(sql,params)
    except mysql.connector.Error as exc:
        if exc.errno==errorcode.ER_DUP_ENTRY:
            raise CIFViolationError(CIF_MESSAGE) from None
        if exc.errno==errorcode.ER_NO_REFERENCED_ROW_2:
            raise AssignmentError('Le séjour, l’acte ou le médecin n’est plus disponible. Actualisez les listes.') from None
        if exc.errno==errorcode.ER_BAD_NULL_ERROR:
            raise AssignmentError('Le séjour, l’acte et le médecin responsable sont obligatoires.') from None
        raise  # existing cursor helper sanitizes every remaining connector error


def add_assignment(hospitalization_id,act_id,doctor_id,*,context):
    with database_cursor(isolation_level='READ COMMITTED') as cursor:
        _lock_parents(cursor,hospitalization_id,act_id,[doctor_id],context)
        if _lock_pair(cursor,hospitalization_id,act_id) is not None:
            raise CIFViolationError(CIF_MESSAGE)
        _execute_write(cursor,'INSERT INTO DESIGNER_RESPONSABLE (idHospitalisation,idActe,idMedecin) VALUES (%s,%s,%s)',(hospitalization_id,act_id,doctor_id))


def reassign(hospitalization_id,act_id,doctor_id,*,original,context):
    with database_cursor(isolation_level='READ COMMITTED') as cursor:
        _lock_parents(cursor,hospitalization_id,act_id,[original['idMedecin'],doctor_id],context)
        _check_original(_lock_pair(cursor,hospitalization_id,act_id),original)
        # Keys never change; reassignment is one UPDATE, never another INSERT.
        _execute_write(cursor,'UPDATE DESIGNER_RESPONSABLE SET idMedecin=%s WHERE idHospitalisation=%s AND idActe=%s',(doctor_id,hospitalization_id,act_id))


def remove_assignment(hospitalization_id,act_id,*,original,context):
    with database_cursor(isolation_level='READ COMMITTED') as cursor:
        _lock_parents(cursor,hospitalization_id,act_id,[original['idMedecin']],context)
        _check_original(_lock_pair(cursor,hospitalization_id,act_id),original)
        _execute_write(cursor,'DELETE FROM DESIGNER_RESPONSABLE WHERE idHospitalisation=%s AND idActe=%s',(hospitalization_id,act_id))
