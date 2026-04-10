"""Tests for admin routes — dashboard, clinics, users, analytics."""
from app import db
from app.models import User, Clinic, Notification
from tests.conftest import login


class TestAdminDashboard:
    def test_dashboard_loads(self, client, superadmin):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/')
        assert resp.status_code == 200

    def test_dashboard_requires_superadmin(self, client, doctor_user):
        login(client, 'doctor@test.kz')
        resp = client.get('/admin/')
        assert resp.status_code == 403


class TestClinicsManagement:
    def test_clinics_list(self, client, superadmin, clinic):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/clinics')
        assert resp.status_code == 200

    def test_clinics_search(self, client, superadmin, clinic):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/clinics?search=Test')
        assert resp.status_code == 200

    def test_create_clinic_form_loads(self, client, superadmin):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/clinics/create')
        assert resp.status_code == 200

    def test_create_clinic_success(self, client, app, superadmin):
        login(client, 'admin@test.kz')
        resp = client.post('/admin/clinics/create', data={
            'name': 'New Clinic',
            'admin_email': 'newadmin@test.kz',
            'admin_password': 'secure123',
            'admin_first_name': 'New',
            'admin_last_name': 'Admin',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            c = Clinic.query.filter_by(name='New Clinic').first()
            assert c is not None
            admin = User.query.filter_by(email='newadmin@test.kz').first()
            assert admin is not None
            assert admin.role == 'clinic_admin'

    def test_toggle_clinic(self, client, app, superadmin, clinic):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/clinics/{clinic}/toggle', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            c = db.session.get(Clinic, clinic)
            assert c.is_active is False

    def test_delete_clinic_cascades(self, client, app, superadmin, clinic, doctor_user, patient_user):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/clinics/{clinic}/delete', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(Clinic, clinic) is None
            assert db.session.get(User, doctor_user) is None
            assert db.session.get(User, patient_user) is None


class TestUsersManagement:
    def test_users_list(self, client, superadmin):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/users')
        assert resp.status_code == 200

    def test_users_filter_by_role(self, client, superadmin, doctor_user):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/users?role=doctor')
        assert resp.status_code == 200


class TestEditClinic:
    def test_edit_clinic_form_loads(self, client, superadmin, clinic):
        login(client, 'admin@test.kz')
        resp = client.get(f'/admin/clinics/{clinic}/edit')
        assert resp.status_code == 200

    def test_edit_clinic_success(self, client, app, superadmin, clinic):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/clinics/{clinic}/edit', data={
            'name': 'Updated Clinic Name',
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            c = db.session.get(Clinic, clinic)
            assert c.name == 'Updated Clinic Name'


class TestToggleUser:
    def test_toggle_user_active(self, client, app, superadmin, doctor_user):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/users/{doctor_user}/toggle', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            u = db.session.get(User, doctor_user)
            assert u.is_active is False

    def test_cannot_toggle_superadmin(self, client, app, superadmin):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/users/{superadmin}/toggle', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            u = db.session.get(User, superadmin)
            assert u.is_active is True  # unchanged


class TestDeleteUser:
    def test_delete_user(self, client, app, superadmin, patient_user):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/users/{patient_user}/delete', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(User, patient_user) is None

    def test_cannot_delete_superadmin(self, client, app, superadmin):
        login(client, 'admin@test.kz')
        resp = client.post(f'/admin/users/{superadmin}/delete', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(User, superadmin) is not None


class TestAdminProfile:
    def test_profile_loads(self, client, superadmin):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/profile')
        assert resp.status_code == 200

    def test_profile_update(self, client, app, superadmin):
        login(client, 'admin@test.kz')
        resp = client.post('/admin/profile', data={
            'first_name': 'Updated',
            'last_name': 'Admin',
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            u = db.session.get(User, superadmin)
            assert u.first_name == 'Updated'


class TestAdminNotifications:
    def test_notifications_page(self, client, app, superadmin):
        with app.app_context():
            db.session.add(Notification(
                user_id=superadmin, title='Test', message='msg', type='info',
            ))
            db.session.commit()
        login(client, 'admin@test.kz')
        resp = client.get('/admin/notifications')
        assert resp.status_code == 200


class TestAnalytics:
    def test_analytics_page(self, client, superadmin):
        login(client, 'admin@test.kz')
        resp = client.get('/admin/analytics')
        assert resp.status_code == 200
