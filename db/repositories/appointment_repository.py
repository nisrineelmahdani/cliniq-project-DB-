"""Appointment searches and doctor-serialized scheduling transactions."""

from datetime import datetime, time, timedelta
import unicodedata

from db.repositories.common import database_cursor
from db.repositories.clinical_common import ClinicalRuleError, check_original, check_patient, lock_doctors


FIELDS = ('dateHeure', 'dureePrevue', 'statut', 'idPatient', 'idMedecin')
COLUMNS = 'idRDV, dateHeure, dureePrevue, statut, idPatient, idMedecin'
PAGE_SIZE = 25
CANCELLED = 'Annulé'


def is_cancelled(status):
    return ''.join(c for c in unicodedata.normalize('NFKD', status.strip().casefold()) if not unicodedata.combining(c)) == 'annule'


def list_appointments(search='', *, doctor=None, patient=None, day=None, status=None, page=0):
    clauses = ["LOCATE(%s, CONCAT_WS(' ', p.nom, p.prenom, m.nom, m.prenom, r.statut, r.idRDV)) > 0"]
    params = [search.strip()]
    for column, value in [('r.idMedecin', doctor), ('r.idPatient', patient), ('r.statut', status)]:
        if value is not None:
            clauses.append(f'{column}=%s')
            params.append(value)
    if day is not None:
        start = datetime.combine(day, time.min)
        clauses.append('r.dateHeure >= %s AND r.dateHeure < %s')
        params.extend((start, start + timedelta(days=1)))
    join = 'FROM RENDEZ_VOUS r JOIN PATIENT p ON p.idPatient=r.idPatient JOIN MEDECIN m ON m.idMedecin=r.idMedecin'
    where = ' AND '.join(clauses)
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total {join} WHERE {where}', tuple(params))
        total = cursor.fetchone()['total']
        page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
        cursor.execute(f"""SELECT r.*,
            CONCAT(p.nom, ' ', p.prenom) AS patient, CONCAT(m.nom, ' ', m.prenom) AS medecin,
            TIMESTAMPADD(MINUTE, r.dureePrevue, r.dateHeure) AS fin
            {join} WHERE {where} ORDER BY r.dateHeure, r.idRDV LIMIT %s OFFSET %s""",
                       (*params, PAGE_SIZE, page * PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows, total=total, page=page)


def get_appointment(appointment_id):
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT {COLUMNS} FROM RENDEZ_VOUS WHERE idRDV=%s', (appointment_id,))
        row = cursor.fetchone()
    if row is None:
        raise ClinicalRuleError('Ce rendez-vous n’est plus disponible.')
    return row


def save_appointment(values, *, appointment_id=None, original=None):
    with database_cursor() as cursor:
        lock_doctors(cursor, [values['idMedecin']])
        if appointment_id is not None:
            cursor.execute(f'SELECT {COLUMNS} FROM RENDEZ_VOUS WHERE idRDV=%s FOR UPDATE', (appointment_id,))
            current = cursor.fetchone()
            check_original(current, original, FIELDS)
            # DEV-004 only edits date, duration and status. Keeping ownership
            # immutable also preserves every linked consultation's ownership.
            if any(values[key] != current[key] for key in ('idPatient', 'idMedecin')):
                raise ClinicalRuleError('Le patient et le médecin d’un rendez-vous existant ne peuvent pas être changés ici.')
        check_patient(cursor, values['idPatient'])
        if not is_cancelled(values['statut']):
            end = values['dateHeure'] + timedelta(minutes=values['dureePrevue'])
            cursor.execute('''SELECT idRDV FROM RENDEZ_VOUS
                WHERE idMedecin=%s AND idRDV<>%s AND TRIM(statut)<>%s
                  AND dateHeure < %s AND TIMESTAMPADD(MINUTE,dureePrevue,dateHeure) > %s
                ORDER BY idRDV LIMIT 1 FOR UPDATE''',
                           (values['idMedecin'], appointment_id or 0, CANCELLED, end, values['dateHeure']))
            if cursor.fetchone() is not None:
                raise ClinicalRuleError('Ce créneau chevauche un rendez-vous actif de ce médecin. Choisissez une autre heure ou durée.')
        if appointment_id is None:
            cursor.execute('INSERT INTO RENDEZ_VOUS (dateHeure,dureePrevue,statut,idPatient,idMedecin) VALUES (%s,%s,%s,%s,%s)',
                           tuple(values[key] for key in FIELDS))
            appointment_id = cursor.lastrowid
        else:
            cursor.execute('UPDATE RENDEZ_VOUS SET dateHeure=%s,dureePrevue=%s,statut=%s WHERE idRDV=%s',
                           (values['dateHeure'], values['dureePrevue'], values['statut'], appointment_id))
    return appointment_id
