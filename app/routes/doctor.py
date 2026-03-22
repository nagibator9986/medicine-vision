from datetime import datetime, date

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app import db
from app.models import (
    User, Appointment, VideoCall, Prescription,
    MedicalRecord, Review, Notification,
)
from app.forms import PrescriptionForm, MedicalRecordForm, ProfileForm

doctor = Blueprint('doctor', __name__, url_prefix='/doctor')


def doctor_required(f):
    """Decorator that ensures the current user has the 'doctor' role."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'doctor':
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


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
    appointments = query.order_by(Appointment.scheduled_time.desc()).paginate(page=page, per_page=20, error_out=False)

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
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.doctor_id != current_user.id:
        abort(403)

    new_status = request.form.get('status')
    if new_status not in ('in_progress', 'completed', 'cancelled'):
        flash('Недопустимый статус.', 'danger')
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
    patient = User.query.get_or_404(patient_id)

    # Ensure the doctor actually has appointments with this patient
    has_appointment = Appointment.query.filter_by(
        doctor_id=current_user.id, patient_id=patient_id
    ).first()
    if not has_appointment:
        abort(403)

    medical_records = MedicalRecord.query.filter_by(patient_id=patient_id).order_by(
        MedicalRecord.created_at.desc()
    ).all()

    prescriptions = Prescription.query.filter_by(patient_id=patient_id).order_by(
        Prescription.created_at.desc()
    ).all()

    return render_template(
        'doctor/patient_detail.html',
        patient=patient,
        medical_records=medical_records,
        prescriptions=prescriptions,
    )


# ---------------------------------------------------------------------------
# Video call
# ---------------------------------------------------------------------------

@doctor.route('/appointments/<int:appointment_id>/video')
@login_required
@doctor_required
def start_video_call(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.doctor_id != current_user.id:
        abort(403)

    video_call = VideoCall.query.filter_by(appointment_id=appointment_id).first()
    if not video_call:
        video_call = VideoCall(
            appointment_id=appointment_id,
            doctor_id=current_user.id,
            patient_id=appointment.patient_id,
            started_at=datetime.utcnow(),
        )
        db.session.add(video_call)

        # Mark appointment as in progress
        if appointment.status not in ('in_progress', 'completed'):
            appointment.status = 'in_progress'

        db.session.commit()

    return redirect(url_for('doctor.video_room', call_id=video_call.id))


@doctor.route('/video/<int:call_id>')
@login_required
@doctor_required
def video_room(call_id):
    video_call = VideoCall.query.get_or_404(call_id)

    if video_call.doctor_id != current_user.id:
        abort(403)

    return render_template('doctor/video_room.html', video_call=video_call)


# ---------------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------------

@doctor.route('/appointments/<int:appointment_id>/prescription', methods=['GET', 'POST'])
@login_required
@doctor_required
def create_prescription(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.doctor_id != current_user.id:
        abort(403)

    form = PrescriptionForm()

    if form.validate_on_submit():
        prescription = Prescription(
            appointment_id=appointment.id,
            doctor_id=current_user.id,
            patient_id=appointment.patient_id,
            medication=form.medication.data,
            dosage=form.dosage.data,
            instructions=form.instructions.data,
            created_at=datetime.utcnow(),
        )
        db.session.add(prescription)
        db.session.commit()

        flash('Рецепт успешно создан.', 'success')
        return redirect(url_for('doctor.appointments'))

    return render_template(
        'doctor/prescription.html',
        form=form,
        appointment=appointment,
    )


# ---------------------------------------------------------------------------
# Medical records
# ---------------------------------------------------------------------------

@doctor.route('/patients/<int:patient_id>/medical-record', methods=['GET', 'POST'])
@login_required
@doctor_required
def create_medical_record(patient_id):
    patient = User.query.get_or_404(patient_id)

    # Verify the doctor has an appointment with this patient
    has_appointment = Appointment.query.filter_by(
        doctor_id=current_user.id, patient_id=patient_id
    ).first()
    if not has_appointment:
        abort(403)

    form = MedicalRecordForm()

    if form.validate_on_submit():
        record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=current_user.id,
            diagnosis=form.diagnosis.data,
            description=form.description.data,
            created_at=datetime.utcnow(),
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
    doctor_reviews = Review.query.filter_by(doctor_id=current_user.id).order_by(
        Review.created_at.desc()
    ).all()

    return render_template('doctor/reviews.html', reviews=doctor_reviews)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@doctor.route('/profile', methods=['GET', 'POST'])
@login_required
@doctor_required
def profile():
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        form.populate_obj(current_user)
        db.session.commit()
        flash('Профиль обновлён.', 'success')
        return redirect(url_for('doctor.profile'))

    return render_template('doctor/profile.html', form=form)
