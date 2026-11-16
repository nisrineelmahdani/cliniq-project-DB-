"""Date/identity rules match the approved nullable discharge and CHECK."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from services import hospitalization_service as service
from services.patient_service import ValidationError


VALUES=dict(dateAdmission=datetime(2038,1,1,9),dateSortie=None,idPatient=1,idLit=3)
ORIGINAL=dict(idHospitalisation=8,**VALUES)


@pytest.mark.parametrize('field,value',[
    ('dateAdmission',None),('dateAdmission','2038-01-01'),('dateAdmission',datetime(999,1,1)),
    ('dateAdmission',datetime.now(timezone.utc)),('dateSortie',datetime(2037,12,31)),
    ('dateSortie','2038-01-02'),('idPatient',0),('idPatient',True),('idLit',None),('idLit',-1),('idLit','3'),
])
def test_invalid_admission_never_writes(field,value):
    with patch('services.hospitalization_service.repository.save_hospitalization') as write:
        with pytest.raises(ValidationError):
            service.save_hospitalization({**VALUES,field:value})
    write.assert_not_called()


def test_null_discharge_and_equal_dates_are_valid():
    assert service.validate_hospitalization(VALUES)==VALUES
    assert service.validate_interval(VALUES['dateAdmission'],VALUES['dateAdmission'])[0]==VALUES['dateAdmission']


@pytest.mark.parametrize('original',[None,{}, {**ORIGINAL,'idHospitalisation':9}])
def test_edit_requires_original_matching_record(original):
    with pytest.raises(ValidationError):
        service.save_hospitalization(VALUES,hospitalization_id=8,original=original)


def test_discharge_validated_and_passes_original_snapshot():
    with pytest.raises(ValidationError):
        service.record_discharge(8,None,original=ORIGINAL)
    with patch('services.hospitalization_service.repository.save_hospitalization',return_value=8) as save:
        assert service.record_discharge(8,datetime(2038,1,2),original=ORIGINAL)==8
        assert save.call_args.args[0]['dateSortie']==datetime(2038,1,2)
        assert save.call_args.kwargs['original'] is ORIGINAL


@pytest.mark.parametrize('start,end',[(date(2038,1,2),date(2038,1,1)),('bad',None),(datetime(2038,1,1),None)])
def test_invalid_admission_period(start,end):
    with pytest.raises(ValidationError):
        service.validate_period(start,end)


def test_availability_checks_dates_before_query_and_binds_exclusion():
    with patch('services.hospitalization_service.repository.available_beds',return_value=[]) as query:
        with pytest.raises(ValidationError):
            service.available_beds(datetime(2038,1,2),datetime(2038,1,1))
        query.assert_not_called()
        service.available_beds(VALUES['dateAdmission'],room=2,exclude_id=8)
        query.assert_called_once_with(VALUES['dateAdmission'],None,room=2,exclude_id=8)
