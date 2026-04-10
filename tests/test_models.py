"""Tests for models — schema integrity, cascades, relationships."""
from datetime import datetime, timezone, timedelta
from app import db
from app.models import (
    User, Clinic, Appointment, VideoCall, Prescription,
    MedicalRecord, ChatMessage, Notification, Review, _utcnow,
)


class TestUtcnow:
    def test_returns_naive_datetime(self, app):
        with app.app_context():
            now = _utcnow()
            # _utcnow returns naive UTC for SQLite compatibility
            assert now.tzinfo is None

    def test_is_recent(self, app):
        with app.app_context():
            now = _utcnow()
            reference = datetime.now(timezone.utc).replace(tzinfo=None)
            assert abs((reference - now).total_seconds()) < 2


class TestUserModel:
    def test_set_and_check_password(self, app):
        with app.app_context():
            u = User(email='x@x.ru', first_name='A', last_name='B', role='patient')
            u.set_password('secret')
            assert u.check_password('secret')
            assert not u.check_password('wrong')

    def test_full_name(self, app):
        with app.app_context():
            u = User(email='x@x.ru', first_name='Иван', last_name='Петров', role='patient')
            assert u.full_name == 'Иван Петров'


class TestPrescriptionModel:
    def test_has_patient_and_doctor_fields(self, app, appointment, doctor_user, patient_user):
        """Verify that Prescription now has patient_id and doctor_id columns."""
        with app.app_context():
            p = Prescription(
                appointment_id=appointment,
                patient_id=patient_user,
                doctor_id=doctor_user,
                diagnosis='Test diagnosis',
                medications='Test meds',
                recommendations='Rest',
            )
            db.session.add(p)
            db.session.commit()

            saved = db.session.get(Prescription, p.id)
            assert saved.patient_id == patient_user
            assert saved.doctor_id == doctor_user
            assert saved.diagnosis == 'Test diagnosis'


class TestMedicalRecordNullableDoctor:
    def test_doctor_id_nullable_for_self_log(self, app, patient_user):
        """Health tracker self-logs should allow doctor_id=None."""
        with app.app_context():
            rec = MedicalRecord(
                patient_id=patient_user,
                doctor_id=None,
                record_type='self_log',
                title='Headache',
                content='Severity: moderate',
            )
            db.session.add(rec)
            db.session.commit()

            saved = db.session.get(MedicalRecord, rec.id)
            assert saved.doctor_id is None
            assert saved.record_type == 'self_log'


class TestCascadeDeletes:
    def test_delete_clinic_cascades_users(self, app, clinic, doctor_user, patient_user):
        """Deleting a clinic should cascade-delete its users."""
        with app.app_context():
            c = db.session.get(Clinic, clinic)
            db.session.delete(c)
            db.session.commit()

            assert db.session.get(User, doctor_user) is None
            assert db.session.get(User, patient_user) is None

    def test_delete_clinic_cascades_appointments(self, app, appointment, clinic):
        """Deleting a clinic should cascade-delete its appointments."""
        with app.app_context():
            c = db.session.get(Clinic, clinic)
            db.session.delete(c)
            db.session.commit()

            assert db.session.get(Appointment, appointment) is None

    def test_delete_appointment_cascades_videocall(self, app, appointment):
        """Deleting an appointment should cascade-delete its VideoCall."""
        with app.app_context():
            import uuid
            vc = VideoCall(
                appointment_id=appointment,
                room_id=str(uuid.uuid4()),
                status='waiting',
            )
            db.session.add(vc)
            db.session.commit()
            vc_id = vc.id

            apt = db.session.get(Appointment, appointment)
            db.session.delete(apt)
            db.session.commit()

            assert db.session.get(VideoCall, vc_id) is None

    def test_delete_appointment_cascades_prescription(self, app, appointment, doctor_user, patient_user):
        """Deleting an appointment should cascade-delete its Prescription."""
        with app.app_context():
            p = Prescription(
                appointment_id=appointment,
                patient_id=patient_user,
                doctor_id=doctor_user,
                diagnosis='Diag',
            )
            db.session.add(p)
            db.session.commit()
            p_id = p.id

            apt = db.session.get(Appointment, appointment)
            db.session.delete(apt)
            db.session.commit()

            assert db.session.get(Prescription, p_id) is None

    def test_delete_appointment_cascades_review(self, app, appointment, doctor_user, patient_user):
        """Deleting an appointment should cascade-delete its Review."""
        with app.app_context():
            apt = db.session.get(Appointment, appointment)
            apt.status = 'completed'
            r = Review(
                patient_id=patient_user,
                doctor_id=doctor_user,
                appointment_id=appointment,
                rating=5,
                comment='Great',
            )
            db.session.add(r)
            db.session.commit()
            r_id = r.id

            apt = db.session.get(Appointment, appointment)
            db.session.delete(apt)
            db.session.commit()

            assert db.session.get(Review, r_id) is None
