"""Tests for videocall routes — room access, start, end, transcribe."""
import uuid
from app import db
from app.models import Appointment, VideoCall, Notification
from tests.conftest import login


class TestVideoCallRoom:
    def test_room_authorized_doctor(self, client, app, doctor_user, appointment):
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()), status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'doctor@test.kz')
        resp = client.get(f'/videocall/room/{room_id}')
        assert resp.status_code == 200

    def test_room_authorized_patient(self, client, app, patient_user, appointment):
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()), status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'patient@test.kz')
        resp = client.get(f'/videocall/room/{room_id}')
        assert resp.status_code == 200

    def test_room_unauthorized_user(self, client, app, appointment, superadmin):
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()), status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'admin@test.kz')
        resp = client.get(f'/videocall/room/{room_id}')
        assert resp.status_code == 403

    def test_room_not_found(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/videocall/room/nonexistent-room')
        assert resp.status_code == 404


class TestVideoCallStart:
    def test_start_creates_videocall(self, client, app, doctor_user, appointment):
        login(client, 'doctor@test.kz')
        resp = client.post(f'/videocall/start/{appointment}', follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            vc = VideoCall.query.filter_by(appointment_id=appointment).first()
            assert vc is not None
            assert vc.status == 'active'

    def test_start_reuses_existing(self, client, app, doctor_user, appointment):
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()), status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'doctor@test.kz')
        resp = client.post(f'/videocall/start/{appointment}', follow_redirects=False)
        assert resp.status_code == 302
        assert room_id in resp.headers['Location']


class TestVideoCallEnd:
    def test_end_videocall(self, client, app, doctor_user, appointment):
        with app.app_context():
            from datetime import datetime, timezone
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()),
                status='active', started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'doctor@test.kz')
        resp = client.post(f'/videocall/end/{room_id}', follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            vc = VideoCall.query.filter_by(room_id=room_id).first()
            assert vc.status == 'ended'
            assert vc.ended_at is not None
            apt = db.session.get(Appointment, appointment)
            assert apt.status == 'completed'


class TestVideoCallTranscribe:
    def test_transcribe_saves_text(self, client, app, doctor_user, appointment):
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()), status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'doctor@test.kz')
        resp = client.post(f'/videocall/transcribe/{room_id}',
                           json={'transcription': 'Пациент жалуется на боль'},
                           content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'

        with app.app_context():
            vc = VideoCall.query.filter_by(room_id=room_id).first()
            assert vc.transcription == 'Пациент жалуется на боль'
            # Notifications should be created for doctor and patient
            notifs = Notification.query.filter(
                Notification.title == 'Транскрипция консультации готова'
            ).count()
            assert notifs == 2

    def test_transcribe_empty_text_still_creates_notifications(self, client, app, doctor_user, appointment):
        """Empty transcription is accepted — fallback summary, notifications, and
        medical record are still created so participants always see the call happened."""
        with app.app_context():
            vc = VideoCall(
                appointment_id=appointment, room_id=str(uuid.uuid4()), status='active',
            )
            db.session.add(vc)
            db.session.commit()
            room_id = vc.room_id

        login(client, 'doctor@test.kz')
        resp = client.post(f'/videocall/transcribe/{room_id}',
                           json={'transcription': ''},
                           content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['summary']  # fallback summary generated

        with app.app_context():
            notifs = Notification.query.filter(
                Notification.title == 'Транскрипция консультации готова'
            ).count()
            assert notifs == 2
            # Medical record was created from the call
            from app.models import MedicalRecord
            recs = MedicalRecord.query.filter_by(record_type='consultation').count()
            assert recs == 1
