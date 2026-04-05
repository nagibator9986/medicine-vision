"""Tests for authentication routes — login, register, logout, open redirect fix."""
from app import db
from app.models import User
from tests.conftest import login


class TestLogin:
    def test_login_page_loads(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200

    def test_login_success_patient(self, client, patient_user):
        resp = client.post('/login', data={
            'email': 'patient@test.kz',
            'password': 'password123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert '/patient' in resp.headers['Location']

    def test_login_success_doctor(self, client, doctor_user):
        resp = client.post('/login', data={
            'email': 'doctor@test.kz',
            'password': 'password123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert '/doctor' in resp.headers['Location']

    def test_login_wrong_password(self, client, patient_user):
        resp = login(client, 'patient@test.kz', 'wrongpassword')
        assert 'Неверный email или пароль' in resp.data.decode()

    def test_login_nonexistent_user(self, client):
        resp = login(client, 'nobody@test.kz', 'pass')
        assert 'Неверный email или пароль' in resp.data.decode()

    def test_login_inactive_user(self, client, app):
        with app.app_context():
            u = User(
                email='inactive@test.kz',
                first_name='In',
                last_name='Active',
                role='patient',
                is_active=False,
            )
            u.set_password('password123')
            db.session.add(u)
            db.session.commit()

        resp = login(client, 'inactive@test.kz', 'password123')
        assert 'деактивирован' in resp.data.decode()


class TestOpenRedirect:
    def test_safe_next_url_works(self, client, patient_user):
        resp = client.post('/login?next=/patient/profile', data={
            'email': 'patient@test.kz',
            'password': 'password123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert '/patient/profile' in resp.headers['Location']

    def test_external_next_url_blocked(self, client, patient_user):
        resp = client.post('/login?next=https://evil.com', data={
            'email': 'patient@test.kz',
            'password': 'password123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        # Should redirect to role default, NOT to evil.com
        assert 'evil.com' not in resp.headers['Location']

    def test_protocol_relative_url_blocked(self, client, patient_user):
        resp = client.post('/login?next=//evil.com', data={
            'email': 'patient@test.kz',
            'password': 'password123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert 'evil.com' not in resp.headers['Location']


class TestRegister:
    def test_register_page_loads(self, client):
        resp = client.get('/register')
        assert resp.status_code == 200

    def test_register_new_patient(self, client, clinic):
        resp = client.post('/register', data={
            'email': 'newpatient@test.kz',
            'password': 'secure123',
            'confirm_password': 'secure123',
            'first_name': 'New',
            'last_name': 'Patient',
            'clinic_id': clinic,
        }, follow_redirects=False)
        assert resp.status_code == 302  # redirect to login

    def test_register_duplicate_email(self, client, patient_user, clinic):
        resp = client.post('/register', data={
            'email': 'patient@test.kz',
            'password': 'secure123',
            'confirm_password': 'secure123',
            'first_name': 'Dup',
            'last_name': 'User',
        }, follow_redirects=True)
        assert 'уже зарегистрирован' in resp.data.decode()


class TestLogout:
    def test_logout_redirects(self, client, patient_user):
        login(client, 'patient@test.kz')
        resp = client.get('/logout', follow_redirects=False)
        assert resp.status_code == 302
