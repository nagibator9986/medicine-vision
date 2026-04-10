"""Tests for API routes and chatbot."""
from app import db
from app.models import Notification, ChatMessage
from tests.conftest import login


class TestNotificationsApi:
    def test_notifications_count(self, client, app, patient_user):
        with app.app_context():
            for i in range(3):
                db.session.add(Notification(
                    user_id=patient_user, title=f'N{i}', message='m', type='info',
                ))
            db.session.commit()

        login(client, 'patient@test.kz')
        resp = client.get('/api/notifications/count')
        assert resp.status_code == 200
        assert resp.get_json()['count'] == 3

    def test_mark_notification_read_api(self, client, app, patient_user):
        with app.app_context():
            n = Notification(
                user_id=patient_user, title='T', message='m', type='info',
            )
            db.session.add(n)
            db.session.commit()
            nid = n.id

        login(client, 'patient@test.kz')
        resp = client.post(f'/api/notifications/{nid}/read')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


class TestNotificationsListApi:
    def test_get_notifications_returns_json(self, client, app, patient_user):
        with app.app_context():
            db.session.add(Notification(
                user_id=patient_user, title='Hello', message='World', type='info',
            ))
            db.session.commit()
        login(client, 'patient@test.kz')
        resp = client.get('/api/notifications')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'notifications' in data
        assert len(data['notifications']) == 1
        assert data['notifications'][0]['title'] == 'Hello'

    def test_mark_all_read_api(self, client, app, patient_user):
        with app.app_context():
            for i in range(2):
                db.session.add(Notification(
                    user_id=patient_user, title=f'N{i}', message='m', type='info',
                ))
            db.session.commit()
        login(client, 'patient@test.kz')
        resp = client.post('/api/notifications/read-all')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        # Verify all are read
        resp2 = client.get('/api/notifications/count')
        assert resp2.get_json()['count'] == 0


class TestDoctorsApi:
    def test_get_doctors_by_clinic(self, client, patient_user, doctor_user, clinic):
        login(client, 'patient@test.kz')
        resp = client.get(f'/api/doctors/{clinic}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        assert data[0]['specialization'] == 'Терапевт'

    def test_search_doctors(self, client, patient_user, doctor_user):
        login(client, 'patient@test.kz')
        resp = client.get('/api/search/doctors?q=Doctor')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1


class TestTimeSlotsApi:
    def test_time_slots_requires_params(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/api/time-slots')
        assert resp.status_code == 400

    def test_time_slots_returns_list(self, client, patient_user, doctor_user):
        from datetime import date, timedelta
        login(client, 'patient@test.kz')
        d = date.today() + timedelta(days=1)
        while d.isoweekday() > 5:
            d += timedelta(days=1)
        resp = client.get(f'/api/time-slots?doctor_id={doctor_user}&date={d.isoformat()}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


class TestChatbot:
    def test_chat_page_loads(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/chatbot/')
        assert resp.status_code == 200

    def test_send_message(self, client, app, patient_user):
        login(client, 'patient@test.kz')
        resp = client.post('/chatbot/send',
                           json={'message': 'Привет'},
                           content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'response' in data

        with app.app_context():
            msgs = ChatMessage.query.filter_by(user_id=patient_user).count()
            assert msgs == 2  # user + assistant

    def test_send_empty_message_rejected(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.post('/chatbot/send',
                           json={'message': ''},
                           content_type='application/json')
        assert resp.status_code == 400

    def test_clear_chat(self, client, app, patient_user):
        with app.app_context():
            db.session.add(ChatMessage(
                user_id=patient_user, role='user', content='test',
            ))
            db.session.commit()

        login(client, 'patient@test.kz')
        resp = client.post('/chatbot/clear')
        assert resp.status_code == 200

        with app.app_context():
            assert ChatMessage.query.filter_by(user_id=patient_user).count() == 0

    def test_chatbot_requires_patient_role(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/chatbot/')
        assert resp.status_code == 302  # redirect
