from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date, timezone
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import (User, Clinic, Appointment, VideoCall, Prescription,
                        MedicalRecord, ChatMessage, Notification, Review)
from app.forms import AppointmentForm, ProfileForm, ReviewForm

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')


def patient_required(f):
    """Decorator that checks the current user has the patient role."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'patient':
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@patient_bp.route('/')
@login_required
@patient_required
def index():
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    upcoming_appointments = (
        Appointment.query
        .filter_by(patient_id=current_user.id)
        .filter(Appointment.status.in_(['scheduled', 'in_progress', 'awaiting_report']))
        .filter(Appointment.scheduled_time >= now)
        .order_by(Appointment.scheduled_time.asc())
        .limit(5)
        .all()
    )

    recent_records = (
        MedicalRecord.query
        .filter_by(patient_id=current_user.id)
        .order_by(MedicalRecord.created_at.desc())
        .limit(5)
        .all()
    )

    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    total_appointments = Appointment.query.filter_by(patient_id=current_user.id).count()
    completed_appointments = Appointment.query.filter_by(
        patient_id=current_user.id, status='completed'
    ).count()
    total_records = MedicalRecord.query.filter_by(patient_id=current_user.id).count()
    total_prescriptions = (
        Prescription.query
        .join(Appointment)
        .filter(Appointment.patient_id == current_user.id)
        .count()
    )

    health_summary = {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'total_records': total_records,
        'total_prescriptions': total_prescriptions,
    }

    return render_template(
        'patient/dashboard.html',
        upcoming_appointments=upcoming_appointments,
        recent_records=recent_records,
        notifications=notifications,
        health_summary=health_summary,
        total_appointments=total_appointments,
        upcoming_count=len(upcoming_appointments),
        records_count=total_records,
        unread_notifications=len(notifications),
    )


# ---------------------------------------------------------------------------
# Browse doctors
# ---------------------------------------------------------------------------

@patient_bp.route('/doctors')
@login_required
@patient_required
def doctors():
    search = request.args.get('search', '').strip()
    specialization = request.args.get('specialization', '').strip()

    query = User.query.filter_by(role='doctor', is_active=True)

    # Show doctors from the patient's clinic
    if current_user.clinic_id:
        query = query.filter_by(clinic_id=current_user.clinic_id)

    if search:
        like_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                User.first_name.ilike(like_pattern),
                User.last_name.ilike(like_pattern),
                User.specialization.ilike(like_pattern),
            )
        )

    if specialization:
        query = query.filter(User.specialization.ilike(f'%{specialization}%'))

    doctors_list = query.order_by(User.last_name).all()

    # Collect unique specializations for the filter dropdown
    spec_query = (
        db.session.query(User.specialization)
        .filter(User.role == 'doctor', User.is_active == True, User.specialization.isnot(None))
    )
    if current_user.clinic_id:
        spec_query = spec_query.filter(User.clinic_id == current_user.clinic_id)
    specializations = sorted({row[0] for row in spec_query.all() if row[0]})

    return render_template(
        'patient/doctors.html',
        doctors=doctors_list,
        specializations=specializations,
        search=search,
        selected_specialization=specialization,
    )


# ---------------------------------------------------------------------------
# Book appointment
# ---------------------------------------------------------------------------

def _generate_time_slots(clinic, selected_date, doctor_id):
    """Return a list of available 30-min time slot strings for the given date."""
    if not clinic:
        return []

    working_days = [int(d) for d in clinic.working_days.split(',') if d.strip()]
    # Python isoweekday: Mon=1 .. Sun=7
    if selected_date.isoweekday() not in working_days:
        return []

    start_h, start_m = map(int, clinic.working_hours_start.split(':'))
    end_h, end_m = map(int, clinic.working_hours_end.split(':'))

    slot_start = datetime.combine(selected_date, datetime.min.time()).replace(
        hour=start_h, minute=start_m
    )
    slot_end = datetime.combine(selected_date, datetime.min.time()).replace(
        hour=end_h, minute=end_m
    )

    # Fetch already booked slots for this doctor on the selected date
    day_start = datetime.combine(selected_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    booked = {
        a.scheduled_time.strftime('%H:%M')
        for a in Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.scheduled_time >= day_start,
            Appointment.scheduled_time < day_end,
            Appointment.status.in_(['scheduled', 'in_progress']),
        ).all()
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    slots = []
    current = slot_start
    while current < slot_end:
        time_str = current.strftime('%H:%M')
        if time_str not in booked and current > now:
            slots.append(time_str)
        current += timedelta(minutes=30)

    return slots


@patient_bp.route('/book', methods=['GET', 'POST'])
@login_required
@patient_required
def book_appointment():
    form = AppointmentForm()

    # Populate doctor choices
    doctor_query = User.query.filter_by(role='doctor', is_active=True)
    if current_user.clinic_id:
        doctor_query = doctor_query.filter_by(clinic_id=current_user.clinic_id)
    doctor_list = doctor_query.order_by(User.last_name).all()
    form.doctor_id.choices = [(d.id, f'{d.full_name} — {d.specialization or ""}') for d in doctor_list]

    # Determine selected date & doctor for slot generation
    selected_date = None
    time_slots = []

    if request.method == 'POST':
        selected_date = form.scheduled_date.data
        doctor_id = form.doctor_id.data
    else:
        date_str = request.args.get('date')
        doctor_id = request.args.get('doctor_id', type=int)
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = None

    # Get clinic from the selected doctor (allows patients without clinic_id to book)
    clinic = None
    if doctor_id:
        selected_doctor = db.session.get(User, doctor_id)
        if selected_doctor and selected_doctor.clinic_id:
            clinic = db.session.get(Clinic, selected_doctor.clinic_id)

    if selected_date and doctor_id and clinic:
        time_slots = _generate_time_slots(clinic, selected_date, doctor_id)

    form.scheduled_time.choices = [('', 'Выберите время')] + [(s, s) for s in time_slots]

    if form.validate_on_submit():
        time_val = form.scheduled_time.data
        if not time_val:
            flash('Пожалуйста, выберите время приёма.', 'warning')
            return render_template(
                'patient/book_appointment.html', form=form, time_slots=time_slots,
                doctors=doctor_list, doctor_id=doctor_id,
            )

        hour, minute = map(int, time_val.split(':'))
        scheduled_dt = datetime.combine(selected_date, datetime.min.time()).replace(
            hour=hour, minute=minute
        )

        # Double-check that the slot is still free
        existing = Appointment.query.filter_by(
            doctor_id=doctor_id,
            scheduled_time=scheduled_dt,
        ).filter(Appointment.status.in_(['scheduled', 'in_progress'])).first()

        if existing:
            flash('Это время уже занято. Выберите другое.', 'danger')
            return render_template(
                'patient/book_appointment.html', form=form, time_slots=time_slots,
                doctors=doctor_list, doctor_id=doctor_id,
            )

        doctor = db.session.get(User, doctor_id)
        if not doctor or not doctor.is_active or doctor.role != 'doctor':
            flash('Врач не найден.', 'danger')
            return redirect(url_for('patient.book_appointment'))
        if current_user.clinic_id and doctor.clinic_id != current_user.clinic_id:
            flash('Этот врач не принадлежит вашей клинике.', 'danger')
            return redirect(url_for('patient.book_appointment'))
        appointment = Appointment(
            patient_id=current_user.id,
            doctor_id=doctor_id,
            clinic_id=doctor.clinic_id if doctor else current_user.clinic_id,
            scheduled_time=scheduled_dt,
            symptoms=form.symptoms.data,
            status='scheduled',
        )
        db.session.add(appointment)
        notification = Notification(
            user_id=doctor_id,
            title='Новая запись на приём',
            message=f'Пациент {current_user.full_name} записался на {scheduled_dt.strftime("%d.%m.%Y %H:%M")}.',
            type='info',
            link=url_for('doctor.dashboard'),
        )
        db.session.add(notification)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Это время уже занято. Выберите другое.', 'danger')
            return render_template(
                'patient/book_appointment.html', form=form, time_slots=time_slots,
                doctors=doctor_list, doctor_id=doctor_id,
            )
        flash('Вы успешно записались на приём!', 'success')
        return redirect(url_for('patient.appointments'))

    return render_template(
        'patient/book_appointment.html', form=form, time_slots=time_slots,
        doctors=doctor_list, doctor_id=form.doctor_id.data,
    )


@patient_bp.route('/api/time-slots')
@login_required
@patient_required
def api_time_slots():
    """AJAX endpoint returning available time slots as JSON."""
    doctor_id = request.args.get('doctor_id', type=int)
    date_str = request.args.get('date')

    if not doctor_id or not date_str:
        return jsonify([])

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify([])

    # Get clinic from the selected doctor (allows patients without clinic_id to book)
    clinic = None
    doctor = db.session.get(User, doctor_id)
    if doctor and doctor.clinic_id:
        clinic = db.session.get(Clinic, doctor.clinic_id)
    slots = _generate_time_slots(clinic, selected_date, doctor_id) if clinic else []
    return jsonify({'slots': slots})


# ---------------------------------------------------------------------------
# Appointments list
# ---------------------------------------------------------------------------

@patient_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@login_required
@patient_required
def cancel_appointment(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)
    if appointment.patient_id != current_user.id:
        abort(403)
    if appointment.status != 'scheduled':
        flash('Можно отменить только запланированный приём.', 'warning')
        return redirect(url_for('patient.appointments'))
    appointment.status = 'cancelled'
    db.session.commit()
    flash('Запись отменена.', 'success')
    return redirect(url_for('patient.appointments'))


@patient_bp.route('/appointments')
@login_required
@patient_required
def appointments():
    status_filter = request.args.get('status', '').strip()

    query = Appointment.query.filter_by(patient_id=current_user.id)

    if status_filter:
        query = query.filter_by(status=status_filter)

    page = request.args.get('page', 1, type=int)
    appointments_list = query.order_by(
        Appointment.scheduled_time.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'patient/appointments.html',
        appointments=appointments_list,
        status_filter=status_filter,
    )


# ---------------------------------------------------------------------------
# Medical records
# ---------------------------------------------------------------------------

@patient_bp.route('/medical-records')
@login_required
@patient_required
def medical_records():
    record_type = request.args.get('type', '').strip()

    query = MedicalRecord.query.filter_by(patient_id=current_user.id)
    if record_type:
        query = query.filter_by(record_type=record_type)

    records = query.order_by(MedicalRecord.created_at.desc()).all()

    return render_template('patient/medical_records.html', records=records, record_type=record_type)


# ---------------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------------

@patient_bp.route('/prescriptions')
@login_required
@patient_required
def prescriptions():
    prescriptions_list = (
        Prescription.query
        .join(Appointment)
        .filter(Appointment.patient_id == current_user.id)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    return render_template('patient/prescriptions.html', prescriptions=prescriptions_list)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@patient_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@patient_required
def profile():
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.first_name = form.first_name.data.strip()
        current_user.last_name = form.last_name.data.strip()
        current_user.phone = form.phone.data.strip() if form.phone.data else None
        current_user.birth_date = form.birth_date.data
        current_user.gender = form.gender.data if form.gender.data else None
        current_user.address = form.address.data.strip() if form.address.data else None

        if form.avatar.data and getattr(form.avatar.data, 'filename', ''):
            from werkzeug.utils import secure_filename
            import os, uuid
            filename = secure_filename(form.avatar.data.filename)
            if filename:
                ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                if ext not in ('jpg', 'jpeg', 'png'):
                    flash('Допустимы только изображения (jpg, png).', 'danger')
                    return redirect(url_for('patient.profile'))
                unique_name = f'{uuid.uuid4().hex}.{ext}'
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, unique_name)
                form.avatar.data.save(filepath)
                current_user.avatar = unique_name

        db.session.commit()
        flash('Профиль успешно обновлён.', 'success')
        return redirect(url_for('patient.profile'))

    return render_template('patient/profile.html', form=form)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@patient_bp.route('/reviews')
@login_required
@patient_required
def reviews():
    # Completed appointments that have not been reviewed yet
    reviewed_appointment_ids = {
        r.appointment_id
        for r in Review.query.filter_by(patient_id=current_user.id).all()
    }

    completed_appointments = (
        Appointment.query
        .filter_by(patient_id=current_user.id, status='completed')
        .order_by(Appointment.scheduled_time.desc())
        .all()
    )

    pending_reviews = [a for a in completed_appointments if a.id not in reviewed_appointment_ids]

    my_reviews = (
        Review.query
        .filter_by(patient_id=current_user.id)
        .order_by(Review.created_at.desc())
        .all()
    )

    return render_template(
        'patient/reviews.html',
        pending_reviews=pending_reviews,
        my_reviews=my_reviews,
    )


@patient_bp.route('/reviews/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
@patient_required
def leave_review(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)

    if appointment.patient_id != current_user.id:
        abort(403)

    if appointment.status != 'completed':
        flash('Отзыв можно оставить только после завершённого приёма.', 'warning')
        return redirect(url_for('patient.reviews'))

    existing_review = Review.query.filter_by(
        patient_id=current_user.id, appointment_id=appointment_id
    ).first()
    if existing_review:
        flash('Вы уже оставили отзыв на этот приём.', 'info')
        return redirect(url_for('patient.reviews'))

    form = ReviewForm()

    if form.validate_on_submit():
        rating = int(form.rating.data)
        comment_text = (form.comment.data or '').strip() or None
        review = Review(
            patient_id=current_user.id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment.id,
            rating=rating,
            comment=comment_text,
        )
        db.session.add(review)

        notification = Notification(
            user_id=appointment.doctor_id,
            title='Новый отзыв',
            message=f'Пациент {current_user.full_name} оставил отзыв ({rating}/5).',
            type='info',
        )
        db.session.add(notification)

        db.session.commit()
        flash('Спасибо за ваш отзыв!', 'success')
        return redirect(url_for('patient.reviews'))

    return render_template(
        'patient/leave_review.html',
        form=form,
        appointment=appointment,
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@patient_bp.route('/notifications')
@login_required
@patient_required
def notifications():
    all_notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    return render_template('patient/notifications.html', notifications=all_notifications)


@patient_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
@patient_required
def mark_notification_read(notification_id):
    notification = db.session.get(Notification, notification_id) or abort(404)

    if notification.user_id != current_user.id:
        abort(403)

    notification.is_read = True
    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})

    flash('Уведомление отмечено как прочитанное.', 'success')
    return redirect(url_for('patient.notifications'))


@patient_bp.route('/notifications/read-all', methods=['POST'])
@login_required
@patient_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})

    flash('Все уведомления отмечены как прочитанные.', 'success')
    return redirect(url_for('patient.notifications'))


# ---------------------------------------------------------------------------
# Health tracker (symptom log)
# ---------------------------------------------------------------------------

@patient_bp.route('/health-tracker', methods=['GET', 'POST'])
@login_required
@patient_required
def health_tracker():
    if request.method == 'POST':
        symptom = request.form.get('symptom', '').strip()
        severity = request.form.get('severity', '').strip()
        notes = request.form.get('notes', '').strip()

        if not symptom:
            flash('Введите описание симптома.', 'warning')
        else:
            record = MedicalRecord(
                patient_id=current_user.id,
                doctor_id=None,
                record_type='self_log',
                title=f'Симптом: {symptom}',
                content=f'Тяжесть: {severity}\n{notes}' if severity else notes,
            )
            db.session.add(record)
            db.session.commit()
            flash('Симптом записан.', 'success')
            return redirect(url_for('patient.health_tracker'))

    symptom_logs = (
        MedicalRecord.query
        .filter_by(patient_id=current_user.id, record_type='self_log')
        .order_by(MedicalRecord.created_at.desc())
        .all()
    )

    return render_template('patient/health_tracker.html', symptom_logs=symptom_logs)
