"""Tests for doctor routes — prescriptions, medical records, video calls, profile."""
import uuid
from datetime import datetime, timezone
from app import db
from app.models import Appointment, VideoCall, Prescription, MedicalRecord, Review
from tests.conftest import login


class TestDoctorDashboard:
    def test_dashboard_loads(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/doctor/dashboard')
        assert resp.status_code == 200

    def test_dashboard_requires_doctor_role(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/doctor/dashboard')
        assert resp.status_code == 403


class TestDoctorAppointments:
    def test_appointments_page(self, client, doctor_user, appointment):
        login(client, 'doctor@test.kz')
        resp = client.get('/doctor/appointments')
        assert resp.status_code == 200

    def test_update_status(self, client, doctor_user, appointment):
        login(client, 'doctor@test.kz')
        resp = client.post(f'/doctor/appointments/{appointment}/status', data={
            'status': 'in_progress',
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_update_status_invalid(self, client, doctor_user, appointment):
        login(client, 'doctor@test.kz')
        resp = client.post(f'/doctor/appointments/{appointment}/status', data={
            'status': 'invalid_status',
        }, follow_redirects=True)
        assert 'Недопустимый статус' in resp.data.decode()


class TestCreatePrescription:
    def test_prescription_form_loads(self, client, app, doctor_user, appointment):
        with app.app_context():
            a = db.session.get(Appointment, appointment)
            a.status = 'awaiting_report'
            db.session.commit()
        login(client, 'doctor@test.kz')
        resp = client.get(f'/doctor/appointments/{appointment}/prescription')
        assert resp.status_code == 200

    def test_create_prescription_success(self, client, app, doctor_user, appointment, patient_user):
        with app.app_context():
            a = db.session.get(Appointment, appointment)
            a.status = 'awaiting_report'
            db.session.commit()
        login(client, 'doctor@test.kz')
        resp = client.post(f'/doctor/appointments/{appointment}/prescription', data={
            'diagnosis': 'ОРВИ',
            'medications': 'Парацетамол 500мг 3 раза в день',
            'recommendations': 'Постельный режим, обильное питьё',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            p = Prescription.query.filter_by(appointment_id=appointment).first()
            assert p is not None
            assert p.diagnosis == 'ОРВИ'
            assert p.patient_id == patient_user
            assert p.doctor_id == doctor_user

    def test_second_prescription_updates_existing(self, client, app, doctor_user, appointment):
        """Regression: the prescription form used to allow creating unlimited
        duplicates. Now submitting twice must edit the existing row — exactly
        one prescription per appointment."""
        with app.app_context():
            a = db.session.get(Appointment, appointment)
            a.status = 'awaiting_report'
            db.session.commit()
        login(client, 'doctor@test.kz')
        client.post(f'/doctor/appointments/{appointment}/prescription', data={
            'diagnosis': 'First diagnosis',
            'medications': 'Med A',
            'recommendations': '',
        }, follow_redirects=True)
        client.post(f'/doctor/appointments/{appointment}/prescription', data={
            'diagnosis': 'Updated diagnosis',
            'medications': 'Med B',
            'recommendations': '',
        }, follow_redirects=True)

        with app.app_context():
            rows = Prescription.query.filter_by(appointment_id=appointment).all()
            assert len(rows) == 1
            assert rows[0].diagnosis == 'Updated diagnosis'
            assert rows[0].medications == 'Med B'

    def test_prescription_wrong_doctor(self, client, app, patient_user, appointment):
        """A different doctor should not be able to create prescription."""
        with app.app_context():
            from app.models import User
            other = User(
                email='other@test.kz', first_name='O', last_name='D',
                role='doctor', is_active=True,
            )
            other.set_password('password123')
            db.session.add(other)
            db.session.commit()

        login(client, 'other@test.kz')
        resp = client.get(f'/doctor/appointments/{appointment}/prescription')
        assert resp.status_code == 403


class TestCreateMedicalRecord:
    def test_record_form_loads(self, client, doctor_user, appointment, patient_user):
        login(client, 'doctor@test.kz')
        resp = client.get(f'/doctor/patients/{patient_user}/medical-record')
        assert resp.status_code == 200

    def test_create_record_success(self, client, app, doctor_user, appointment, patient_user):
        login(client, 'doctor@test.kz')
        resp = client.post(f'/doctor/patients/{patient_user}/medical-record', data={
            'record_type': 'examination',
            'title': 'Первичный осмотр',
            'content': 'Пациент жалуется на головную боль.',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            rec = MedicalRecord.query.filter_by(patient_id=patient_user).first()
            assert rec is not None
            assert rec.title == 'Первичный осмотр'
            assert rec.record_type == 'examination'
            assert rec.doctor_id == doctor_user


class TestVideoCall:
    def test_start_video_call_creates_videocall(self, client, app, doctor_user, appointment):
        login(client, 'doctor@test.kz')
        resp = client.get(f'/doctor/appointments/{appointment}/video', follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            vc = VideoCall.query.filter_by(appointment_id=appointment).first()
            assert vc is not None
            assert vc.status == 'active'
            assert vc.room_id is not None
            # Verify no doctor_id/patient_id on VideoCall (they don't exist in model)
            assert not hasattr(vc, 'doctor_id') or 'doctor_id' not in vc.__table__.columns

    def test_start_video_call_reuses_existing(self, client, app, doctor_user, appointment):
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment,
                room_id=str(uuid.uuid4()),
                status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'doctor@test.kz')
        resp = client.get(f'/doctor/appointments/{appointment}/video', follow_redirects=False)
        assert resp.status_code == 302
        assert room_id in resp.headers['Location']


class TestPatientDetail:
    def test_patient_detail_loads(self, client, doctor_user, patient_user, appointment):
        login(client, 'doctor@test.kz')
        resp = client.get(f'/doctor/patients/{patient_user}')
        assert resp.status_code == 200

    def test_patient_detail_no_appointment_returns_403(self, client, app, doctor_user):
        with app.app_context():
            from app.models import User
            other = User(
                email='lonely@test.kz', first_name='L', last_name='P',
                role='patient', is_active=True,
            )
            other.set_password('password123')
            db.session.add(other)
            db.session.commit()
            other_id = other.id
        login(client, 'doctor@test.kz')
        resp = client.get(f'/doctor/patients/{other_id}')
        assert resp.status_code == 403


class TestDoctorReviews:
    def test_reviews_page_loads(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/doctor/reviews')
        assert resp.status_code == 200

    def test_reviews_shows_data(self, client, app, doctor_user, patient_user, appointment):
        with app.app_context():
            apt = db.session.get(Appointment, appointment)
            apt.status = 'completed'
            db.session.add(Review(
                patient_id=patient_user, doctor_id=doctor_user,
                appointment_id=appointment, rating=4, comment='Good',
            ))
            db.session.commit()
        login(client, 'doctor@test.kz')
        resp = client.get('/doctor/reviews')
        assert resp.status_code == 200


class TestDoctorProfile:
    def test_profile_loads(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/doctor/profile')
        assert resp.status_code == 200

    def test_profile_update_does_not_corrupt_avatar(self, client, app, doctor_user):
        """Ensure populate_obj bug is fixed — avatar should remain a string."""
        login(client, 'doctor@test.kz')
        resp = client.post('/doctor/profile', data={
            'first_name': 'UpdatedName',
            'last_name': 'Test',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import User
            doc = db.session.get(User, doctor_user)
            assert doc.first_name == 'UpdatedName'
            # avatar should be None or a string, never a FileStorage object
            assert doc.avatar is None or isinstance(doc.avatar, str)
