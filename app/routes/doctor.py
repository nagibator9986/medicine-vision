import os
import uuid
from datetime import datetime, date, timezone
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app import db
from app.models import (
    User, Appointment, VideoCall, Prescription,
    MedicalRecord, Review, Notification,
)
from app.forms import PrescriptionForm, MedicalRecordForm, ProfileForm

doctor = Blueprint('doctor', __name__, url_prefix='/doctor')


VALID_STATUS_TRANSITIONS = {
    'scheduled': ['in_progress', 'cancelled'],
    'in_progress': ['awaiting_report', 'completed', 'cancelled'],
    'awaiting_report': ['completed', 'cancelled'],
    'completed': [],
    'cancelled': [],
}


def doctor_required(f):
    """Decorator that ensures the current user has the 'doctor' role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'doctor':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def _save_avatar(file_storage):
    """Save an uploaded avatar and return the bare filename for DB storage."""
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None
    filename = secure_filename(file_storage.filename)
    if not filename or '.' not in filename:
        return None
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in ('jpg', 'jpeg', 'png'):
        return None
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, unique_name))
    return unique_name


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@doctor.route('/dashboard')
@login_required
@doctor_required
def dashboard():
    today = date.today()

    today_appointments = Appointment.query.filter(
        Appointment.doctor_id == current_user.id,
        db.func.date(Appointment.scheduled_time) == today,
    ).order_by(Appointment.scheduled_time.asc()).all()

    upcoming_appointments = Appointment.query.filter(
        Appointment.doctor_id == current_user.id,
        db.func.date(Appointment.scheduled_time) > today,
        Appointment.status != 'cancelled',
    ).order_by(Appointment.scheduled_time.asc()).limit(10).all()

    total_appointments = Appointment.query.filter_by(doctor_id=current_user.id).count()
    completed_appointments = Appointment.query.filter_by(
        doctor_id=current_user.id, status='completed'
    ).count()
    total_patients = (
        db.session.query(db.func.count(db.distinct(Appointment.patient_id)))
        .filter(Appointment.doctor_id == current_user.id)
        .scalar()
    )

    stats = {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'total_patients': total_patients,
    }

    return render_template(
        'doctor/dashboard.html',
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        stats=stats,
        total_appointments=total_appointments,
        completed_appointments=completed_appointments,
        unique_patients=total_patients,
    )


# ---------------------------------------------------------------------------
# Appointments list with filtering
# ---------------------------------------------------------------------------

@doctor.route('/appointments')
@login_required
@doctor_required
def appointments():
    status_filter = request.args.get('status', '')
    date_filter = request.args.get('date', '')

    query = Appointment.query.filter_by(doctor_id=current_user.id)

    if status_filter:
        query = query.filter(Appointment.status == status_filter)

    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Appointment.scheduled_time) == filter_date)
        except ValueError:
            pass

    page = request.args.get('page', 1, type=int)
    appointments = query.order_by(
        Appointment.scheduled_time.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'doctor/appointments.html',
        appointments=appointments,
        status_filter=status_filter,
        date_filter=date_filter,
    )


# ---------------------------------------------------------------------------
# Update appointment status
# ---------------------------------------------------------------------------

@doctor.route('/appointments/<int:appointment_id>/status', methods=['POST'])
@login_required
@doctor_required
def update_appointment_status(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)

    if appointment.doctor_id != current_user.id:
        abort(403)

    new_status = request.form.get('status')
    if new_status not in ('in_progress', 'awaiting_report', 'completed', 'cancelled'):
        flash('Недопустимый статус.', 'danger')
        return redirect(url_for('doctor.appointments'))

    allowed = VALID_STATUS_TRANSITIONS.get(appointment.status, [])
    if new_status not in allowed:
        flash(f'Невозможно перевести приём из "{appointment.status}" в "{new_status}".', 'danger')
        return redirect(url_for('doctor.appointments'))

    appointment.status = new_status
    db.session.commit()

    flash('Статус приёма обновлён.', 'success')
    return redirect(url_for('doctor.appointments'))


# ---------------------------------------------------------------------------
# Patient detail (before consultation)
# ---------------------------------------------------------------------------

@doctor.route('/patients/<int:patient_id>')
@login_required
@doctor_required
def patient_detail(patient_id):
    patient = db.session.get(User, patient_id) or abort(404)

    # Ensure the doctor actually has appointments with this patient
    has_appointment = Appointment.query.filter_by(
        doctor_id=current_user.id, patient_id=patient_id
    ).first()
    if not has_appointment:
        abort(403)

    medical_records = MedicalRecord.query.filter_by(
        patient_id=patient_id
    ).order_by(MedicalRecord.created_at.desc()).all()

    # All appointments with this patient (for prescription history + active work)
    appointment_history = (
        Appointment.query
        .filter_by(doctor_id=current_user.id, patient_id=patient_id)
        .order_by(Appointment.scheduled_time.desc())
        .all()
    )

    return render_template(
        'doctor/patient_detail.html',
        patient=patient,
        medical_records=medical_records,
        appointment_history=appointment_history,
    )


# ---------------------------------------------------------------------------
# Video call — redirect to the videocall blueprint
# ---------------------------------------------------------------------------

@doctor.route('/appointments/<int:appointment_id>/video')
@login_required
@doctor_required
def start_video_call(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)

    if appointment.doctor_id != current_user.id:
        abort(403)

    # If a videocall already exists, go straight to it
    if appointment.videocall:
        return redirect(url_for('videocall.room', room_id=appointment.videocall.room_id))

    # Create a new VideoCall using fields that actually exist in the model
    room_id = str(uuid.uuid4())
    video_call = VideoCall(
        appointment_id=appointment_id,
        room_id=room_id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status='active',
    )
    db.session.add(video_call)

    if appointment.status not in ('in_progress', 'awaiting_report', 'completed'):
        appointment.status = 'in_progress'

    db.session.commit()

    return redirect(url_for('videocall.room', room_id=room_id))


# ---------------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------------

@doctor.route('/appointments/<int:appointment_id>/prescription', methods=['GET', 'POST'])
@login_required
@doctor_required
def create_prescription(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)

    if appointment.doctor_id != current_user.id:
        abort(403)

    if appointment.status not in ('in_progress', 'awaiting_report', 'completed'):
        flash('Рецепт можно создать только для активного или завершённого приёма.', 'warning')
        return redirect(url_for('doctor.appointments'))

    # One prescription per appointment — allow editing the existing one instead
    # of creating duplicates.
    existing = appointment.prescription
    form = PrescriptionForm(obj=existing) if existing else PrescriptionForm()

    if form.validate_on_submit():
        if existing:
            existing.diagnosis = form.diagnosis.data
            existing.medications = form.medications.data
            existing.recommendations = form.recommendations.data
            flash('Рецепт обновлён.', 'success')
        else:
            prescription = Prescription(
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                doctor_id=current_user.id,
                diagnosis=form.diagnosis.data,
                medications=form.medications.data,
                recommendations=form.recommendations.data,
            )
            db.session.add(prescription)
            flash('Рецепт успешно создан.', 'success')

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Для этого приёма уже существует рецепт.', 'warning')
            return redirect(url_for('doctor.appointments'))

        return redirect(url_for('doctor.appointments'))

    return render_template(
        'doctor/prescription.html',
        form=form,
        appointment=appointment,
        existing=existing,
    )


# ---------------------------------------------------------------------------
# Medical records
# ---------------------------------------------------------------------------

@doctor.route('/patients/<int:patient_id>/medical-record', methods=['GET', 'POST'])
@login_required
@doctor_required
def create_medical_record(patient_id):
    patient = db.session.get(User, patient_id) or abort(404)

    # Verify the doctor has an appointment with this patient
    has_appointment = Appointment.query.filter_by(
        doctor_id=current_user.id, patient_id=patient_id
    ).first()
    if not has_appointment:
        abort(403)

    form = MedicalRecordForm()

    if form.validate_on_submit():
        file_path = None
        if form.file.data and form.file.data.filename:
            filename = secure_filename(form.file.data.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'records')
            os.makedirs(upload_dir, exist_ok=True)
            full_path = os.path.join(upload_dir, unique_name)
            form.file.data.save(full_path)
            file_path = f"uploads/records/{unique_name}"

        record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=current_user.id,
            record_type=form.record_type.data,
            title=form.title.data,
            content=form.content.data,
            file_path=file_path,
        )
        db.session.add(record)
        db.session.commit()

        flash('Медицинская запись создана.', 'success')
        return redirect(url_for('doctor.patient_detail', patient_id=patient_id))

    return render_template(
        'doctor/medical_record.html',
        form=form,
        patient=patient,
    )


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@doctor.route('/reviews')
@login_required
@doctor_required
def reviews():
    doctor_reviews = Review.query.filter_by(
        doctor_id=current_user.id
    ).order_by(Review.created_at.desc()).all()

    avg_rating = None
    if doctor_reviews:
        avg_rating = round(sum(r.rating for r in doctor_reviews) / len(doctor_reviews), 2)

    return render_template('doctor/reviews.html', reviews=doctor_reviews, avg_rating=avg_rating)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@doctor.route('/profile', methods=['GET', 'POST'])
@login_required
@doctor_required
def profile():
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.first_name = form.first_name.data.strip()
        current_user.last_name = form.last_name.data.strip()
        current_user.phone = form.phone.data.strip() if form.phone.data else None
        current_user.birth_date = form.birth_date.data
        current_user.gender = form.gender.data if form.gender.data else None
        current_user.address = form.address.data.strip() if form.address.data else None

        if form.avatar.data and hasattr(form.avatar.data, 'filename') and form.avatar.data.filename:
            saved = _save_avatar(form.avatar.data)
            if saved:
                current_user.avatar = saved

        db.session.commit()
        flash('Профиль обновлён.', 'success')
        return redirect(url_for('doctor.profile'))

    return render_template('doctor/profile.html', form=form)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@doctor.route('/notifications')
@login_required
@doctor_required
def notifications():
    all_notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template('doctor/notifications.html', notifications=all_notifications)
