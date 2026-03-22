import os
import uuid
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Clinic, Appointment, VideoCall, ClinicSpecialization, Review
from app.forms import DoctorForm, ClinicForm

clinic = Blueprint('clinic', __name__)


def clinic_admin_required(f):
    """Decorator that ensures the current user is a clinic admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'clinic_admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def save_avatar(file):
    """Save an uploaded avatar file and return the filename."""
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, unique_name))
    return unique_name


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@clinic.route('/dashboard')
@login_required
@clinic_admin_required
def dashboard():
    clinic_obj = Clinic.query.get_or_404(current_user.clinic_id)

    doctors_count = User.query.filter_by(
        clinic_id=clinic_obj.id, role='doctor', is_active=True
    ).count()

    patients_count = (
        db.session.query(User.id)
        .join(Appointment, Appointment.patient_id == User.id)
        .filter(Appointment.clinic_id == clinic_obj.id)
        .distinct()
        .count()
    )

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    today_appointments = Appointment.query.filter(
        Appointment.clinic_id == clinic_obj.id,
        Appointment.scheduled_time.between(today_start, today_end)
    ).count()

    completed_appointments = Appointment.query.filter_by(
        clinic_id=clinic_obj.id, status='completed'
    ).all()
    revenue = sum(
        a.doctor.consultation_price or 0 for a in completed_appointments
    )

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
        clinic_id=current_user.clinic_id, role='doctor'
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

        if form.avatar.data:
            doctor.avatar = save_avatar(form.avatar.data)

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
    ).first_or_404()

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

        if form.avatar.data:
            doctor.avatar = save_avatar(form.avatar.data)

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
    ).first_or_404()

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

    appointments_list = query.order_by(Appointment.scheduled_time.desc()).all()
    return render_template('clinic/appointments.html', appointments=appointments_list)


# ---------------------------------------------------------------------------
# Clinic Settings
# ---------------------------------------------------------------------------

@clinic.route('/settings', methods=['GET', 'POST'])
@login_required
@clinic_admin_required
def settings():
    clinic_obj = Clinic.query.get_or_404(current_user.clinic_id)
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

        if form.logo.data:
            clinic_obj.logo = save_avatar(form.logo.data)

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
    clinic_obj = Clinic.query.get_or_404(current_user.clinic_id)

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

    # Revenue
    completed = Appointment.query.filter_by(
        clinic_id=clinic_obj.id, status='completed'
    ).all()
    total_revenue = sum(a.doctor.consultation_price or 0 for a in completed)

    # Monthly revenue for the last 6 months
    monthly_revenue = []
    for i in range(5, -1, -1):
        month_date = date.today().replace(day=1) - timedelta(days=i * 30)
        month_start = month_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

        month_completed = Appointment.query.filter(
            Appointment.clinic_id == clinic_obj.id,
            Appointment.status == 'completed',
            Appointment.scheduled_time >= datetime.combine(month_start, datetime.min.time()),
            Appointment.scheduled_time < datetime.combine(month_end, datetime.min.time()),
        ).all()
        rev = sum(a.doctor.consultation_price or 0 for a in month_completed)
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
