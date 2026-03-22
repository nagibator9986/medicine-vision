from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import User, Clinic
from app.forms import LoginForm, PatientRegistrationForm

auth_bp = Blueprint('auth', __name__)

ROLE_REDIRECTS = {
    'superadmin': 'admin.dashboard',
    'clinic_admin': 'clinic.dashboard',
    'doctor': 'doctor.dashboard',
    'patient': 'patient.index',
}


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role, 'auth.login')))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()

        if user is None or not user.check_password(form.password.data):
            flash('Неверный email или пароль.', 'danger')
            return render_template('auth/login.html', form=form)

        if not user.is_active:
            flash('Ваш аккаунт деактивирован. Обратитесь к администратору.', 'warning')
            return render_template('auth/login.html', form=form)

        login_user(user, remember=True)
        flash(f'Добро пожаловать, {user.first_name}!', 'success')

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        return redirect(url_for(ROLE_REDIRECTS.get(user.role, 'auth.login')))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role, 'auth.login')))

    form = PatientRegistrationForm()
    clinics = Clinic.query.filter_by(is_active=True).order_by(Clinic.name).all()

    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if existing_user:
            flash('Пользователь с таким email уже зарегистрирован.', 'danger')
            return render_template('auth/register.html', form=form, clinics=clinics)

        clinic_id = request.form.get('clinic_id', type=int)
        if clinic_id:
            clinic = Clinic.query.get(clinic_id)
            if not clinic or not clinic.is_active:
                flash('Выбранная клиника недоступна.', 'danger')
                return render_template('auth/register.html', form=form, clinics=clinics)

        user = User(
            email=form.email.data.lower().strip(),
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            phone=form.phone.data.strip() if form.phone.data else None,
            birth_date=form.birth_date.data,
            gender=form.gender.data if form.gender.data else None,
            role='patient',
            clinic_id=clinic_id,
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash('Регистрация прошла успешно! Войдите в систему.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form, clinics=clinics)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'success')
    return redirect(url_for('auth.login'))
