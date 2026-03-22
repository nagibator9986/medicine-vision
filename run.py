from app import create_app, socketio, db
from app.models import User, Clinic

app = create_app()


@app.cli.command('init-db')
def init_db():
    """Initialize database and create superadmin user."""
    db.create_all()

    # Create superadmin if not exists
    admin = User.query.filter_by(email='admin@mediplatform.ru').first()
    if not admin:
        admin = User(
            email='admin@mediplatform.ru',
            first_name='Администратор',
            last_name='Платформы',
            role='superadmin',
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)

    # Create demo clinic
    clinic = Clinic.query.filter_by(email='demo@clinic.ru').first()
    if not clinic:
        clinic = Clinic(
            name='Клиника "Здоровье"',
            description='Современная многопрофильная клиника с широким спектром медицинских услуг',
            address='г. Москва, ул. Примерная, д. 1',
            phone='+7 (495) 123-45-67',
            email='demo@clinic.ru',
            primary_color='#2563eb',
            secondary_color='#10b981',
            working_hours_start='09:00',
            working_hours_end='18:00',
            working_days='1,2,3,4,5',
            is_active=True
        )
        db.session.add(clinic)
        db.session.flush()

        # Create clinic admin
        clinic_admin = User(
            email='clinic@mediplatform.ru',
            first_name='Админ',
            last_name='Клиники',
            role='clinic_admin',
            clinic_id=clinic.id,
            is_active=True
        )
        clinic_admin.set_password('clinic123')
        db.session.add(clinic_admin)

        # Create demo doctor
        doctor = User(
            email='doctor@mediplatform.ru',
            first_name='Иван',
            last_name='Петров',
            role='doctor',
            clinic_id=clinic.id,
            specialization='Терапевт',
            experience_years=10,
            bio='Опытный врач-терапевт с 10-летним стажем работы.',
            consultation_price=2500.0,
            is_active=True
        )
        doctor.set_password('doctor123')
        db.session.add(doctor)

        # Create demo patient
        patient = User(
            email='patient@mediplatform.ru',
            first_name='Мария',
            last_name='Иванова',
            role='patient',
            clinic_id=clinic.id,
            gender='female',
            is_active=True
        )
        patient.set_password('patient123')
        db.session.add(patient)

    db.session.commit()
    print('Database initialized successfully!')
    print('')
    print('Demo accounts:')
    print('  Superadmin:    admin@mediplatform.ru / admin123')
    print('  Clinic Admin:  clinic@mediplatform.ru / clinic123')
    print('  Doctor:        doctor@mediplatform.ru / doctor123')
    print('  Patient:       patient@mediplatform.ru / patient123')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5050, allow_unsafe_werkzeug=True)
