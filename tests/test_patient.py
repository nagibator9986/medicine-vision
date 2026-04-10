"""Tests for patient routes — dashboard, booking, health tracker, reviews."""
from datetime import datetime, date, timezone, timedelta
from app import db
from app.models import Appointment, MedicalRecord, Notification, Review, Prescription
from tests.conftest import login


class TestPatientDashboard:
    def test_dashboard_loads(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/')
        assert resp.status_code == 200

    def test_dashboard_requires_patient_role(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/patient/')
        assert resp.status_code == 403


class TestDoctorsList:
    def test_doctors_page_loads(self, client, patient_user, doctor_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/doctors')
        assert resp.status_code == 200
        assert b'Doctor' in resp.data


class TestAppointmentsPaginated:
    def test_appointments_page_loads(self, client, patient_user, appointment):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/appointments')
        assert resp.status_code == 200

    def test_appointments_with_page_param(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/appointments?page=1')
        assert resp.status_code == 200

    def test_appointments_filter_by_status(self, client, patient_user, appointment):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/appointments?status=scheduled')
        assert resp.status_code == 200


class TestHealthTracker:
    def test_health_tracker_loads(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/health-tracker')
        assert resp.status_code == 200

    def test_log_symptom_with_null_doctor(self, client, app, patient_user):
        """Verify self-logged symptoms have doctor_id=None and type='self_log'."""
        login(client, 'patient@test.kz')
        resp = client.post('/patient/health-tracker', data={
            'symptom': 'Головная боль',
            'severity': 'moderate',
            'notes': 'После сна',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            rec = MedicalRecord.query.filter_by(
                patient_id=patient_user, record_type='self_log'
            ).first()
            assert rec is not None
            assert rec.doctor_id is None
            assert 'Головная боль' in rec.title

    def test_empty_symptom_rejected(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.post('/patient/health-tracker', data={
            'symptom': '',
        }, follow_redirects=True)
        assert 'Введите описание симптома' in resp.data.decode()


class TestBookAppointment:
    def test_booking_page_loads(self, client, patient_user, doctor_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/book')
        assert resp.status_code == 200

    def test_time_slots_api(self, client, patient_user, doctor_user, clinic):
        login(client, 'patient@test.kz')
        # Get a future weekday
        from datetime import date
        d = date.today() + timedelta(days=1)
        while d.isoweekday() > 5:
            d += timedelta(days=1)
        resp = client.get(f'/patient/api/time-slots?doctor_id={doctor_user}&date={d.isoformat()}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


class TestNotifications:
    def test_notifications_page(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/notifications')
        assert resp.status_code == 200

    def test_mark_read(self, client, app, patient_user):
        with app.app_context():
            n = Notification(
                user_id=patient_user,
                title='Test',
                message='Test msg',
                type='info',
                is_read=False,
            )
            db.session.add(n)
            db.session.commit()
            nid = n.id

        login(client, 'patient@test.kz')
        resp = client.post(f'/patient/notifications/{nid}/read', follow_redirects=True)
        assert resp.status_code == 200

    def test_mark_all_read(self, client, app, patient_user):
        with app.app_context():
            for i in range(3):
                n = Notification(
                    user_id=patient_user,
                    title=f'N{i}',
                    message='msg',
                    type='info',
                )
                db.session.add(n)
            db.session.commit()

        login(client, 'patient@test.kz')
        resp = client.post('/patient/notifications/read-all', follow_redirects=True)
        assert resp.status_code == 200


class TestReviews:
    def test_reviews_page(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/reviews')
        assert resp.status_code == 200

    def test_leave_review(self, client, app, patient_user, doctor_user, appointment):
        # First mark appointment as completed
        with app.app_context():
            apt = db.session.get(Appointment, appointment)
            apt.status = 'completed'
            db.session.commit()

        login(client, 'patient@test.kz')
        resp = client.post(f'/patient/reviews/{appointment}', data={
            'rating': '5',
            'comment': 'Отличный врач!',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            r = Review.query.filter_by(appointment_id=appointment).first()
            assert r is not None
            assert r.rating == 5
            assert r.comment == 'Отличный врач!'


class TestMedicalRecordsPage:
    def test_medical_records_page_loads(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/medical-records')
        assert resp.status_code == 200

    def test_medical_records_filter_by_type(self, client, app, patient_user):
        with app.app_context():
            db.session.add(MedicalRecord(
                patient_id=patient_user, record_type='examination',
                title='Test Exam', content='Content',
            ))
            db.session.commit()
        login(client, 'patient@test.kz')
        resp = client.get('/patient/medical-records?type=examination')
        assert resp.status_code == 200
        assert b'Test Exam' in resp.data


class TestPrescriptionsPage:
    def test_prescriptions_page_loads(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/patient/prescriptions')
        assert resp.status_code == 200

    def test_prescriptions_shows_data(self, client, app, patient_user, doctor_user, appointment):
        with app.app_context():
            db.session.add(Prescription(
                appointment_id=appointment, patient_id=patient_user,
                doctor_id=doctor_user, diagnosis='Грипп',
            ))
            db.session.commit()
        login(client, 'patient@test.kz')
        resp = client.get('/patient/prescriptions')
        assert resp.status_code == 200


class TestWeekendSlots:
    def test_weekend_slots_unavailable(self, client, patient_user, doctor_user, clinic):
        login(client, 'patient@test.kz')
        d = date.today() + timedelta(days=1)
        while d.isoweekday() <= 5:
            d += timedelta(days=1)
        resp = client.get(f'/patient/api/time-slots?doctor_id={doctor_user}&date={d.isoformat()}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []


class TestStatusTransitionValidation:
    def test_cannot_transition_completed_to_scheduled(self, client, app, doctor_user, appointment):
        with app.app_context():
            apt = db.session.get(Appointment, appointment)
            apt.status = 'completed'
            db.session.commit()
        login(client, 'doctor@test.kz')
        resp = client.post(f'/doctor/appointments/{appointment}/status', data={
            'status': 'scheduled',
        }, follow_redirects=True)
        assert 'Недопустимый статус' in resp.data.decode()

    def test_cannot_transition_cancelled_to_in_progress(self, client, app, doctor_user, appointment):
        with app.app_context():
            apt = db.session.get(Appointment, appointment)
            apt.status = 'cancelled'
            db.session.commit()
        login(client, 'doctor@test.kz')
        resp = client.post(f'/doctor/appointments/{appointment}/status', data={
            'status': 'in_progress',
        }, follow_redirects=True)
        assert 'Невозможно перевести' in resp.data.decode()
