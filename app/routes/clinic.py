import os
import uuid
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Clinic, Appointment, VideoCall, ClinicSpecialization, Review, Notification
from app.forms import DoctorForm, ClinicForm, ProfileForm

clinic = Blueprint('clinic', __name__)


def clinic_admin_required(f):
    """Decorator that ensures the current user is a clinic admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'clinic_admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
ALLOWED_LOGO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'svg'}


def _save_image(file, subdir, allowed):
    """Save an uploaded image under static/uploads/<subdir>/. Returns bare filename or None."""
    if not file or not getattr(file, 'filename', ''):
        return None
    filename = secure_filename(file.filename)
    if not filename or '.' not in filename:
        return None
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed:
        return None
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subdir)
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, unique_name))
    return unique_name


def save_avatar(file):
    """Save a doctor avatar and return the bare filename."""
    return _save_image(file, 'avatars', ALLOWED_IMAGE_EXTENSIONS)


def save_logo(file):
    """Save a clinic logo and return the bare filename."""
    return _save_image(file, 'clinics', ALLOWED_LOGO_EXTENSIONS)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@clinic.route('/dashboard')
@login_required
@clinic_admin_required
def dashboard():
    clinic_obj = db.session.get(Clinic, current_user.clinic_id) or abort(404)

    doctors_count = User.query.filter_by(
        clinic_id=clinic_obj.id, role='doctor', is_active=True
    ).count()

    # Count patients: those assigned to this clinic OR who have appointments here
    patients_by_clinic = db.session.query(User.id).filter(
        User.clinic_id == clinic_obj.id, User.role == 'patient'
    )
    patients_by_appointment = (
        db.session.query(Appointment.patient_id)
        .filter(Appointment.clinic_id == clinic_obj.id)
    )
    patients_count = (
        db.session.query(User.id)
        .filter(db.or_(
            User.id.in_(patients_by_clinic),
            User.id.in_(patients_by_appointment),
        ))
        .distinct()
        .count()
    )

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    today_appointments = Appointment.query.filter(
        Appointment.clinic_id == clinic_obj.id,
        Appointment.scheduled_time.between(today_start, today_end)
    ).count()

    revenue = (
        db.session.query(db.func.coalesce(db.func.sum(User.consultation_price), 0))
        .join(Appointment, Appointment.doctor_id == User.id)
        .filter(Appointment.clinic_id == clinic_obj.id, Appointment.status == 'completed')
        .scalar()
    ) or 0

    return render_template(
        'clinic/dashboard.html',
        clinic=clinic_obj,
        doctors_count=doctors_count,
        patients_count=patients_count,
        today_appointments=today_appointments,
        revenue=revenue,
    )


# ---------------------------------------------------------------------------
# Manage Doctors
# ---------------------------------------------------------------------------

@clinic.route('/doctors')
@login_required
@clinic_admin_required
def doctors():
    doctors_list = User.query.filter_by(
        clinic_id=current_user.clinic_id, role='doctor', is_active=True
    ).order_by(User.created_at.desc()).all()
    return render_template('clinic/doctors.html', doctors=doctors_list)


@clinic.route('/doctors/add', methods=['GET', 'POST'])
@login_required
@clinic_admin_required
def add_doctor():
    form = DoctorForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data).first()
        if existing:
            flash('Пользователь с таким email уже существует.', 'danger')
            return render_template('clinic/doctor_form.html', form=form, title='Добавить врача')

        doctor = User(
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            phone=form.phone.data,
            specialization=form.specialization.data,
            experience_years=form.experience_years.data,
            bio=form.bio.data,
            consultation_price=form.consultation_price.data,
            role='doctor',
            clinic_id=current_user.clinic_id,
        )
        doctor.set_password(form.password.data)

        if form.avatar.data and getattr(form.avatar.data, 'filename', ''):
            saved = save_avatar(form.avatar.data)
            if saved:
                doctor.avatar = saved

        db.session.add(doctor)
        db.session.commit()
        flash('Врач успешно добавлен.', 'success')
        return redirect(url_for('clinic.doctors'))

    return render_template('clinic/doctor_form.html', form=form, title='Добавить врача')


@clinic.route('/doctors/<int:doctor_id>/edit', methods=['GET', 'POST'])
@login_required
@clinic_admin_required
def edit_doctor(doctor_id):
    doctor = User.query.filter_by(
        id=doctor_id, role='doctor', clinic_id=current_user.clinic_id
    ).first() or abort(404)

    form = DoctorForm(obj=doctor)
    if form.validate_on_submit():
        # Check email uniqueness if changed
        if form.email.data != doctor.email:
            existing = User.query.filter_by(email=form.email.data).first()
            if existing:
                flash('Пользователь с таким email уже существует.', 'danger')
                return render_template('clinic/doctor_form.html', form=form,
                                       title='Редактировать врача', doctor=doctor)

        doctor.email = form.email.data
        doctor.first_name = form.first_name.data
        doctor.last_name = form.last_name.data
        doctor.phone = form.phone.data
        doctor.specialization = form.specialization.data
        doctor.experience_years = form.experience_years.data
        doctor.bio = form.bio.data
        doctor.consultation_price = form.consultation_price.data

        if form.password.data:
            doctor.set_password(form.password.data)

        if form.avatar.data and getattr(form.avatar.data, 'filename', ''):
            saved = save_avatar(form.avatar.data)
            if saved:
                doctor.avatar = saved

        db.session.commit()
        flash('Данные врача обновлены.', 'success')
        return redirect(url_for('clinic.doctors'))

    return render_template('clinic/doctor_form.html', form=form,
                           title='Редактировать врача', doctor=doctor)


@clinic.route('/doctors/<int:doctor_id>/delete', methods=['POST'])
@login_required
@clinic_admin_required
def delete_doctor(doctor_id):
    doctor = User.query.filter_by(
        id=doctor_id, role='doctor', clinic_id=current_user.clinic_id
    ).first() or abort(404)

    doctor.is_active = False
    db.session.commit()
    flash('Врач удалён.', 'success')
    return redirect(url_for('clinic.doctors'))


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

@clinic.route('/patients')
@login_required
@clinic_admin_required
def patients():
    patients_list = (
        db.session.query(User)
        .join(Appointment, Appointment.patient_id == User.id)
        .filter(Appointment.clinic_id == current_user.clinic_id)
        .distinct()
        .order_by(User.last_name)
        .all()
    )
    return render_template('clinic/patients.html', patients=patients_list)


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

@clinic.route('/appointments')
@login_required
@clinic_admin_required
def appointments():
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')

    query = Appointment.query.filter_by(clinic_id=current_user.clinic_id)

    if status_filter:
        query = query.filter_by(status=status_filter)

    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            day_start = datetime.combine(filter_date, datetime.min.time())
            day_end = datetime.combine(filter_date, datetime.max.time())
            query = query.filter(Appointment.scheduled_time.between(day_start, day_end))
        except ValueError:
            pass

    page = request.args.get('page', 1, type=int)
    appointments_list = query.order_by(
        Appointment.scheduled_time.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    return render_template('clinic/appointments.html', appointments=appointments_list)


# ---------------------------------------------------------------------------
# Clinic Settings
# ---------------------------------------------------------------------------

@clinic.route('/settings', methods=['GET', 'POST'])
@login_required
@clinic_admin_required
def settings():
    clinic_obj = db.session.get(Clinic, current_user.clinic_id) or abort(404)
    form = ClinicForm(obj=clinic_obj)

    if form.validate_on_submit():
        clinic_obj.name = form.name.data
        clinic_obj.description = form.description.data
        clinic_obj.address = form.address.data
        clinic_obj.phone = form.phone.data
        clinic_obj.email = form.email.data
        clinic_obj.website = form.website.data
        clinic_obj.primary_color = form.primary_color.data
        clinic_obj.secondary_color = form.secondary_color.data
        clinic_obj.working_hours_start = form.working_hours_start.data
        clinic_obj.working_hours_end = form.working_hours_end.data

        if form.logo.data and getattr(form.logo.data, 'filename', ''):
            new_logo = save_logo(form.logo.data)
            if new_logo:
                clinic_obj.logo = new_logo

        db.session.commit()
        flash('Настройки клиники обновлены.', 'success')
        return redirect(url_for('clinic.settings'))

    return render_template('clinic/settings.html', form=form, clinic=clinic_obj)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@clinic.route('/statistics')
@login_required
@clinic_admin_required
def statistics():
    clinic_obj = db.session.get(Clinic, current_user.clinic_id) or abort(404)

    # Total counts
    total_doctors = User.query.filter_by(
        clinic_id=clinic_obj.id, role='doctor', is_active=True
    ).count()

    total_appointments = Appointment.query.filter_by(clinic_id=clinic_obj.id).count()
    completed_appointments = Appointment.query.filter_by(
        clinic_id=clinic_obj.id, status='completed'
    ).count()
    cancelled_appointments = Appointment.query.filter_by(
        clinic_id=clinic_obj.id, status='cancelled'
    ).count()

    # Revenue (single aggregate query instead of N+1)
    total_revenue = (
        db.session.query(db.func.coalesce(db.func.sum(User.consultation_price), 0))
        .join(Appointment, Appointment.doctor_id == User.id)
        .filter(Appointment.clinic_id == clinic_obj.id, Appointment.status == 'completed')
        .scalar()
    ) or 0

    # Monthly revenue for the last 6 months (correct calendar math)
    from calendar import monthrange
    monthly_revenue = []
    today = date.today()
    for i in range(5, -1, -1):
        # Walk back i months correctly
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)

        rev = (
            db.session.query(db.func.coalesce(db.func.sum(User.consultation_price), 0))
            .join(Appointment, Appointment.doctor_id == User.id)
            .filter(
                Appointment.clinic_id == clinic_obj.id,
                Appointment.status == 'completed',
                Appointment.scheduled_time >= datetime.combine(month_start, datetime.min.time()),
                Appointment.scheduled_time < datetime.combine(month_end, datetime.min.time()),
            )
            .scalar()
        ) or 0
        monthly_revenue.append({
            'month': month_start.strftime('%B %Y'),
            'revenue': rev,
        })

    # Average rating
    doctor_ids = [d.id for d in User.query.filter_by(
        clinic_id=clinic_obj.id, role='doctor'
    ).all()]
    avg_rating = None
    if doctor_ids:
        result = db.session.query(db.func.avg(Review.rating)).filter(
            Review.doctor_id.in_(doctor_ids)
        ).scalar()
        avg_rating = round(result, 2) if result else None

    # Top doctors by appointment count
    top_doctors = (
        db.session.query(
            User,
            db.func.count(Appointment.id).label('apt_count')
        )
        .join(Appointment, Appointment.doctor_id == User.id)
        .filter(Appointment.clinic_id == clinic_obj.id)
        .group_by(User.id)
        .order_by(db.func.count(Appointment.id).desc())
        .limit(5)
        .all()
    )

    return render_template(
        'clinic/statistics.html',
        clinic=clinic_obj,
        total_doctors=total_doctors,
        total_appointments=total_appointments,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments,
        total_revenue=total_revenue,
        monthly_revenue=monthly_revenue,
        avg_rating=avg_rating,
        top_doctors=top_doctors,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@clinic.route('/profile', methods=['GET', 'POST'])
@login_required
@clinic_admin_required
def profile():
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.first_name = form.first_name.data.strip()
        current_user.last_name = form.last_name.data.strip()
        current_user.phone = form.phone.data.strip() if form.phone.data else None

        if form.avatar.data and getattr(form.avatar.data, 'filename', ''):
            saved = save_avatar(form.avatar.data)
            if saved:
                current_user.avatar = saved

        db.session.commit()
        flash('Профиль обновлён.', 'success')
        return redirect(url_for('clinic.profile'))

    return render_template('clinic/profile.html', form=form)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@clinic.route('/notifications')
@login_required
@clinic_admin_required
def notifications():
    all_notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template('clinic/notifications.html', notifications=all_notifications)
