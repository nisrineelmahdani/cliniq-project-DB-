"""Date-derived hospital stays and serialized bed assignments; approved MLD only."""

import mysql.connector
from mysql.connector import errorcode

from db.repositories.common import ConcurrentEditError, RepositoryError, database_cursor


PAGE_SIZE = 25
FIELDS = ('dateAdmission', 'dateSortie', 'idPatient', 'idLit')
STATUS_SQL = "CASE WHEN h.dateAdmission>%s THEN 'Prévue' WHEN h.dateSortie IS NOT NULL AND h.dateSortie<=%s THEN 'Terminée' ELSE 'En cours' END"
JOIN_SQL = 'FROM HOSPITALISATION h JOIN PATIENT p ON p.idPatient=h.idPatient JOIN LIT l ON l.idLit=h.idLit JOIN CHAMBRE ch ON ch.idChambre=l.idChambre'
PROJECTION = "h.*,CONCAT(p.nom,' ',p.prenom) AS patient,ch.idChambre,ch.numeroChambre,ch.typeChambre,l.numeroLit"
# A NULL upper bound is infinity. Empty stored intervals occupy no time.
OVERLAP_SQL = '(h.dateSortie IS NULL OR h.dateSortie>h.dateAdmission) AND (%s IS NULL OR h.dateAdmission<%s) AND (h.dateSortie IS NULL OR h.dateSortie>%s)'


class HospitalizationError(RepositoryError):
    """Actionable message without identifying values or raw SQL."""


def filter_options():
    with database_cursor(readonly=True) as cursor:
        cursor.execute("SELECT idPatient,CONCAT(nom,' ',prenom) AS label FROM PATIENT ORDER BY nom,prenom,idPatient")
        patients = cursor.fetchall()
        cursor.execute("SELECT idChambre,CONCAT(numeroChambre,' · ',typeChambre) AS label FROM CHAMBRE ORDER BY numeroChambre,idChambre")
        rooms = cursor.fetchall()
    return dict(patients=patients, rooms=rooms)


def list_hospitalizations(as_of, search='', *, patient=None, room=None, from_day=None, to_day=None, status=None, page=0):
    clauses = ["LOCATE(%s,CONCAT_WS(' ',h.idHospitalisation,p.nom,p.prenom,ch.numeroChambre,l.numeroLit))>0"]
    params = [search.strip()]
    for column, value in [('h.idPatient', patient), ('ch.idChambre', room)]:
        if value is not None:
            clauses.append(f'{column}=%s')
            params.append(value)
    for operator, value in [('>=', from_day), ('<=', to_day)]:
        if value is not None:
            clauses.append(f'DATE(h.dateAdmission){operator}%s')
            params.append(value)
    if status is not None:
        clauses.append(f'({STATUS_SQL})=%s')
        params.extend((as_of, as_of, status))
    where = ' AND '.join(clauses)
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total {JOIN_SQL} WHERE {where}', tuple(params))
        total = cursor.fetchone()['total']
        page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
        cursor.execute(f'SELECT {PROJECTION},{STATUS_SQL} AS statut {JOIN_SQL} WHERE {where} ORDER BY h.dateAdmission DESC,h.idHospitalisation DESC LIMIT %s OFFSET %s',
                       (as_of, as_of, *params, PAGE_SIZE, page * PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows, total=total, page=page)


def get_hospitalization(hospitalization_id, as_of):
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT {PROJECTION},{STATUS_SQL} AS statut {JOIN_SQL} WHERE h.idHospitalisation=%s', (as_of, as_of, hospitalization_id))
        row = cursor.fetchone()
    if row is None:
        raise HospitalizationError('Ce séjour n’est plus disponible. Actualisez la liste.')
    return row


def patient_history(patient_id, as_of):
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT {PROJECTION},{STATUS_SQL} AS statut {JOIN_SQL} WHERE h.idPatient=%s ORDER BY h.dateAdmission DESC,h.idHospitalisation DESC', (as_of, as_of, patient_id))
        return cursor.fetchall()


def available_beds(start, end=None, *, room=None, exclude_id=None):
    with database_cursor(readonly=True) as cursor:
        # An empty candidate interval is valid under the existing CHECK and
        # cannot overlap another interval. All beds are available for it.
        where = '(%s IS NULL OR ch.idChambre=%s)'
        params = [room, room]
        if end != start:
            where += f' AND NOT EXISTS(SELECT 1 FROM HOSPITALISATION h WHERE h.idLit=l.idLit AND h.idHospitalisation<>%s AND {OVERLAP_SQL})'
            params.extend((exclude_id or 0, end, end, start))
        cursor.execute(f'''SELECT l.idLit,l.numeroLit,ch.idChambre,ch.numeroChambre,ch.typeChambre,
            CONCAT('Chambre ',ch.numeroChambre,' · Lit ',l.numeroLit,' · ',ch.typeChambre) AS label
            FROM LIT l JOIN CHAMBRE ch ON ch.idChambre=l.idChambre
            WHERE {where} ORDER BY ch.numeroChambre,l.numeroLit,l.idLit''', tuple(params))
        return cursor.fetchall()


def occupancy(as_of, *, room=None):
    active = 'h.dateAdmission<=%s AND (h.dateSortie IS NULL OR h.dateSortie>%s)'
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'''SELECT l.idLit,l.numeroLit,ch.idChambre,ch.numeroChambre,ch.typeChambre,
            EXISTS(SELECT 1 FROM HOSPITALISATION h WHERE h.idLit=l.idLit AND {active}) AS occupied
            FROM LIT l JOIN CHAMBRE ch ON ch.idChambre=l.idChambre
            WHERE (%s IS NULL OR ch.idChambre=%s) ORDER BY ch.numeroChambre,l.numeroLit,l.idLit''', (as_of, as_of, room, room))
        beds = cursor.fetchall()
        cursor.execute(f'''WITH occupied_beds AS (SELECT DISTINCT h.idLit FROM HOSPITALISATION h WHERE {active})
            SELECT ch.idChambre,ch.numeroChambre,ch.typeChambre,COUNT(l.idLit) AS total,
                COUNT(o.idLit) AS occupied,COUNT(l.idLit)-COUNT(o.idLit) AS available
            FROM CHAMBRE ch LEFT JOIN LIT l ON l.idChambre=ch.idChambre
            LEFT JOIN occupied_beds o ON o.idLit=l.idLit WHERE (%s IS NULL OR ch.idChambre=%s)
            GROUP BY ch.idChambre,ch.numeroChambre,ch.typeChambre ORDER BY ch.numeroChambre,ch.idChambre''', (as_of, as_of, room, room))
        rooms = cursor.fetchall()
    return dict(beds=beds, rooms=rooms, as_of=as_of)


def _execute_write(cursor, sql, params):
    try:
        cursor.execute(sql, params)
    except mysql.connector.Error as exc:
        if exc.errno == errorcode.ER_NO_REFERENCED_ROW_2:
            raise HospitalizationError('Le patient ou le lit n’est plus disponible. Actualisez les listes.') from None
        if exc.errno == errorcode.ER_CHECK_CONSTRAINT_VIOLATED:
            raise HospitalizationError('La sortie ne peut pas précéder l’admission.') from None
        raise


def save_hospitalization(values, *, hospitalization_id=None, original=None):
    # Parent row locks provide interval serialization; READ COMMITTED avoids
    # empty-range gap locks deadlocking admissions to different empty beds.
    with database_cursor(isolation_level='READ COMMITTED') as cursor:
        bed_ids = {values['idLit']}
        if original is not None:
            bed_ids.add(original['idLit'])
        # Serialize on actual LIT rows, including the first assignment of a bed.
        # Corrections moving beds acquire both parents in a deterministic order.
        for bed_id in sorted(bed_ids):
            cursor.execute('SELECT idLit FROM LIT WHERE idLit=%s FOR UPDATE', (bed_id,))
            if cursor.fetchone() is None:
                raise HospitalizationError('Le lit sélectionné n’est plus disponible.')
        if hospitalization_id is not None:
            cursor.execute('SELECT * FROM HOSPITALISATION WHERE idHospitalisation=%s FOR UPDATE', (hospitalization_id,))
            current = cursor.fetchone()
            if current is None:
                raise HospitalizationError('Ce séjour n’est plus disponible.')
            if any(current[key] != original[key] for key in FIELDS):
                raise ConcurrentEditError('Ce séjour a été modifié. Rechargez ses informations avant de réessayer.')
            if values['idPatient'] != current['idPatient']:
                raise HospitalizationError('Le patient d’un séjour existant ne peut pas être changé ici.')
        cursor.execute('SELECT idPatient FROM PATIENT WHERE idPatient=%s', (values['idPatient'],))
        if cursor.fetchone() is None:
            raise HospitalizationError('Le patient sélectionné n’est plus disponible.')
        if values['dateSortie'] != values['dateAdmission']:
            cursor.execute(f'''SELECT h.idHospitalisation FROM HOSPITALISATION h
                WHERE h.idLit=%s AND h.idHospitalisation<>%s AND {OVERLAP_SQL}
                ORDER BY h.idHospitalisation LIMIT 1 FOR UPDATE''',
                           (values['idLit'], hospitalization_id or 0, values['dateSortie'], values['dateSortie'], values['dateAdmission']))
            if cursor.fetchone() is not None:
                raise HospitalizationError('Ce lit est occupé pendant une partie du séjour demandé. Choisissez un autre lit ou corrigez les dates.')
        if hospitalization_id is None:
            _execute_write(cursor, 'INSERT INTO HOSPITALISATION (dateAdmission,dateSortie,idPatient,idLit) VALUES (%s,%s,%s,%s)', tuple(values[key] for key in FIELDS))
            hospitalization_id = cursor.lastrowid
        else:
            _execute_write(cursor, 'UPDATE HOSPITALISATION SET dateAdmission=%s,dateSortie=%s,idLit=%s WHERE idHospitalisation=%s',
                           (values['dateAdmission'], values['dateSortie'], values['idLit'], hospitalization_id))
    return hospitalization_id
