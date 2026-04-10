import os
import warnings
import pytest

# Suppress known third-party deprecation warnings we cannot fix
warnings.filterwarnings('ignore', category=DeprecationWarning, module='flask_login')
warnings.filterwarnings('ignore', category=DeprecationWarning, module='flask_sqlalchemy')
warnings.filterwarnings('ignore', message='.*datetime.datetime.utcnow.*', category=DeprecationWarning)

# Force test configuration before any app import
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
os.environ['OPENAI_API_KEY'] = ''

from app import create_app, db as _db
from app.models import User, Clinic, Appointment, VideoCall, Prescription, MedicalRecord, Notification, Review
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # in-memory
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost'


@pytest.fixture(scope='session')
def app():
    """Create the application once for the entire test session."""
    application = create_app(TestConfig)
    return application


@pytest.fixture(autouse=True)
def setup_db(app):
    """Create fresh tables for every test."""
    with app.app_context():
        _db.create_all()
        yield
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield _db.session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def clinic(app):
    with app.app_context():
        c = Clinic(
            name='Test Clinic',
            address='Test addr',
            phone='+70001112233',
            email='clinic@test.kz',
            working_hours_start='09:00',
            working_hours_end='18:00',
            working_days='1,2,3,4,5',
            is_active=True,
        )
        _db.session.add(c)
        _db.session.commit()
        return c.id


@pytest.fixture
def superadmin(app, clinic):
    with app.app_context():
        u = User(
            email='admin@test.kz',
            first_name='Admin',
            last_name='Test',
            role='superadmin',
            is_active=True,
        )
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        return u.id


@pytest.fixture
def doctor_user(app, clinic):
    with app.app_context():
        u = User(
            email='doctor@test.kz',
            first_name='Doctor',
            last_name='Test',
            role='doctor',
            clinic_id=clinic,
            specialization='Терапевт',
            experience_years=5,
            consultation_price=2000.0,
            is_active=True,
        )
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        return u.id


@pytest.fixture
def patient_user(app, clinic):
    with app.app_context():
        u = User(
            email='patient@test.kz',
            first_name='Patient',
            last_name='Test',
            role='patient',
            clinic_id=clinic,
            is_active=True,
        )
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        return u.id


@pytest.fixture
def clinic_admin_user(app, clinic):
    with app.app_context():
        u = User(
            email='clinicadmin@test.kz',
            first_name='ClinicAdmin',
            last_name='Test',
            role='clinic_admin',
            clinic_id=clinic,
            is_active=True,
        )
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        return u.id


@pytest.fixture
def appointment(app, clinic, doctor_user, patient_user):
    from datetime import datetime, timedelta, timezone
    with app.app_context():
        a = Appointment(
            patient_id=patient_user,
            doctor_id=doctor_user,
            clinic_id=clinic,
            scheduled_time=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            status='scheduled',
        )
        _db.session.add(a)
        _db.session.commit()
        return a.id


def login(client, email, password='password123'):
    """Helper to login a user via the login form."""
    return client.post('/login', data={
        'email': email,
        'password': password,
    }, follow_redirects=True)
