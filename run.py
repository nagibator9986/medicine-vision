import os

from app import create_app, socketio, db
from app.models import User, Clinic

app = create_app()



def _seed_demo_data():
    """Create demo accounts if the database is empty (first deploy)."""
    # Skip if superadmin already exists
    if User.query.filter_by(email='admin@mediplatform.kz').first():
        return

    admin = User(
        email='admin@mediplatform.kz',
        first_name='Администратор',
        last_name='Платформы',
        role='superadmin',
        is_active=True,
    )
    admin.set_password('admin123')
    db.session.add(admin)

    clinic = Clinic(
        name='Клиника "Денсаулық"',
        description='Заманауи көп бейінді клиника — кең ауқымды медициналық қызметтер',
        address='г. Алматы, ул. Абая, д. 52',
        phone='+7 (727) 123-45-67',
        email='demo@clinic.kz',
        primary_color='#2563eb',
        secondary_color='#10b981',
        working_hours_start='09:00',
        working_hours_end='18:00',
        working_days='1,2,3,4,5',
        is_active=True,
    )
    db.session.add(clinic)
    db.session.flush()

    clinic_admin = User(
        email='clinic@mediplatform.kz',
        first_name='Админ',
        last_name='Клиники',
        role='clinic_admin',
        clinic_id=clinic.id,
        is_active=True,
    )
    clinic_admin.set_password('clinic123')
    db.session.add(clinic_admin)

    doctor = User(
        email='doctor@mediplatform.kz',
        first_name='Арман',
        last_name='Сериков',
        role='doctor',
        clinic_id=clinic.id,
        specialization='Терапевт',
        experience_years=10,
        bio='Тәжірибелі дәрігер-терапевт, 10 жылдық тәжірибе.',
        consultation_price=15000.0,
        is_active=True,
    )
    doctor.set_password('doctor123')
    db.session.add(doctor)

    patient = User(
        email='patient@mediplatform.kz',
        first_name='Айгерим',
        last_name='Нурланова',
        role='patient',
        clinic_id=clinic.id,
        gender='female',
        is_active=True,
    )
    patient.set_password('patient123')
    db.session.add(patient)

    db.session.commit()


# Auto-create tables and seed demo data on startup
with app.app_context():
    db.create_all()
    _seed_demo_data()


@app.cli.command('init-db')
def init_db():
    """Initialize database and create demo accounts."""
    db.create_all()
    _seed_demo_data()
    print('Database initialized successfully!')
    print('')
    print('Demo accounts (see .env-example for passwords):')
    print('  Superadmin:    admin@mediplatform.kz')
    print('  Clinic Admin:  clinic@mediplatform.kz')
    print('  Doctor:        doctor@mediplatform.kz')
    print('  Patient:       patient@mediplatform.kz')


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    socketio.run(
        app,
        debug=debug,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5051)),
        allow_unsafe_werkzeug=debug,
    )
