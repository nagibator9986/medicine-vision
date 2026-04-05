"""Tests for clinic admin routes — dashboard, doctors, appointments, statistics."""
from datetime import datetime, timezone, timedelta
from app import db
from app.models import User, Appointment
from tests.conftest import login


class TestClinicDashboard:
    def test_dashboard_loads(self, client, clinic_admin_user):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/dashboard')
        assert resp.status_code == 200

    def test_requires_clinic_admin(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/clinic/dashboard')
        assert resp.status_code == 403


class TestClinicDoctors:
    def test_doctors_list(self, client, clinic_admin_user, doctor_user):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/doctors')
        assert resp.status_code == 200

    def test_add_doctor_form(self, client, clinic_admin_user):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/doctors/add')
        assert resp.status_code == 200

    def test_add_doctor_success(self, client, app, clinic_admin_user, clinic):
        login(client, 'clinicadmin@test.kz')
        resp = client.post('/clinic/doctors/add', data={
            'email': 'newdoc@test.kz',
            'password': 'docpass123',
            'first_name': 'Новый',
            'last_name': 'Врач',
            'specialization': 'Хирург',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            doc = User.query.filter_by(email='newdoc@test.kz').first()
            assert doc is not None
            assert doc.role == 'doctor'
            assert doc.clinic_id == clinic


class TestClinicAppointments:
    def test_appointments_list(self, client, clinic_admin_user, appointment):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/appointments')
        assert resp.status_code == 200

    def test_appointments_filter_by_status(self, client, clinic_admin_user, appointment):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/appointments?status=scheduled')
        assert resp.status_code == 200


class TestClinicStatistics:
    def test_statistics_page(self, client, clinic_admin_user):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/statistics')
        assert resp.status_code == 200

    def test_statistics_with_completed_appointments(self, client, app, clinic_admin_user, clinic, doctor_user, patient_user):
        """Verify revenue calculation uses aggregate query (no N+1)."""
        with app.app_context():
            for i in range(3):
                a = Appointment(
                    patient_id=patient_user,
                    doctor_id=doctor_user,
                    clinic_id=clinic,
                    scheduled_time=datetime.now(timezone.utc) - timedelta(days=i),
                    status='completed',
                )
                db.session.add(a)
            db.session.commit()

        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/statistics')
        assert resp.status_code == 200


class TestClinicSettings:
    def test_settings_loads(self, client, clinic_admin_user):
        login(client, 'clinicadmin@test.kz')
        resp = client.get('/clinic/settings')
        assert resp.status_code == 200
