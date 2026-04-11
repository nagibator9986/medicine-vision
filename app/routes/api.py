from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app import db, csrf
from app.models import User, Clinic, Appointment, Notification

api_bp = Blueprint('api', __name__)


@api_bp.route('/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Return user's recent unread notifications as JSON."""
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(20).all()

    return jsonify({
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.type,
            'read': n.is_read,
            'link': n.link,
            'created_at': n.created_at.isoformat() if n.created_at else None,
        } for n in notifications]
    }), 200


@api_bp.route('/notifications/read-all', methods=['POST'])
@login_required
@csrf.exempt
def mark_all_notifications_read():
    """Mark all of the current user's notifications as read."""
    Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True}), 200


@api_bp.route('/notifications/count', methods=['GET'])
@login_required
def notifications_count():
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    return jsonify({'count': count}), 200


@api_bp.route('/notifications/<int:id>/read', methods=['POST'])
@login_required
@csrf.exempt
def mark_notification_read(id):
    notification = db.session.get(Notification, id) or abort(404)

    if notification.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403

    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True}), 200


@api_bp.route('/doctors/<int:clinic_id>', methods=['GET'])
@login_required
def get_doctors(clinic_id):
    clinic = db.session.get(Clinic, clinic_id) or abort(404)
    doctors = User.query.filter_by(
        clinic_id=clinic.id,
        role='doctor',
        is_active=True
    ).all()

    result = []
    for doctor in doctors:
        result.append({
            'id': doctor.id,
            'full_name': doctor.full_name,
            'specialization': doctor.specialization,
            'experience_years': doctor.experience_years,
            'consultation_price': doctor.consultation_price,
            'avatar': doctor.avatar,
        })

    return jsonify(result), 200


@api_bp.route('/time-slots', methods=['GET'])
@login_required
def get_time_slots():
    doctor_id = request.args.get('doctor_id', type=int)
    date_str = request.args.get('date')

    if not doctor_id or not date_str:
        return jsonify({'error': 'Параметры doctor_id и date обязательны'}), 400

    doctor = User.query.filter_by(id=doctor_id, role='doctor').first()
    if not doctor:
        return jsonify({'error': 'Врач не найден'}), 404

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Неверный формат даты. Используйте YYYY-MM-DD'}), 400

    clinic = doctor.clinic
    if not clinic:
        return jsonify({'error': 'Клиника врача не найдена'}), 404

    # Check if target day is a working day
    working_days = [int(d) for d in clinic.working_days.split(',')]
    # isoweekday(): Mon=1 .. Sun=7
    if target_date.isoweekday() not in working_days:
        return jsonify([]), 200

    # Parse working hours
    start_h, start_m = map(int, clinic.working_hours_start.split(':'))
    end_h, end_m = map(int, clinic.working_hours_end.split(':'))

    slot_start = datetime.combine(target_date, datetime.min.time().replace(hour=start_h, minute=start_m))
    work_end = datetime.combine(target_date, datetime.min.time().replace(hour=end_h, minute=end_m))

    # Generate 30-min slots
    slots = []
    while slot_start + timedelta(minutes=30) <= work_end:
        slots.append(slot_start)
        slot_start += timedelta(minutes=30)

    # Get existing appointments for the doctor on this date
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = datetime.combine(target_date, datetime.max.time())

    booked = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.scheduled_time >= day_start,
        Appointment.scheduled_time <= day_end,
        Appointment.status.in_(['scheduled', 'in_progress'])
    ).all()

    booked_times = {appt.scheduled_time for appt in booked}

    available = []
    for slot in slots:
        if slot not in booked_times:
            available.append({
                'time': slot.strftime('%H:%M'),
                'datetime': slot.isoformat(),
            })

    return jsonify(available), 200


@api_bp.route('/search/doctors', methods=['GET'])
@login_required
def search_doctors():
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([]), 200

    search = f'%{query}%'
    doctors = User.query.filter(
        User.role == 'doctor',
        User.is_active == True,
        db.or_(
            User.first_name.ilike(search),
            User.last_name.ilike(search),
            User.specialization.ilike(search),
        )
    ).limit(20).all()

    result = []
    for doctor in doctors:
        result.append({
            'id': doctor.id,
            'full_name': doctor.full_name,
            'specialization': doctor.specialization,
            'clinic_id': doctor.clinic_id,
            'clinic_name': doctor.clinic.name if doctor.clinic else None,
            'avatar': doctor.avatar,
            'consultation_price': doctor.consultation_price,
        })

    return jsonify(result), 200


