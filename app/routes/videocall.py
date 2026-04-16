import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room
from app import db, socketio, csrf
from app.models import User, Appointment, VideoCall, Notification

logger = logging.getLogger(__name__)

videocall_bp = Blueprint('videocall', __name__)


@videocall_bp.route('/room/<room_id>')
@login_required
def room(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first()
    if not videocall:
        abort(404)
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    # If call ended and has transcription/summary, show the summary page instead
    if videocall.status == 'ended' and (videocall.transcription or videocall.summary):
        return render_template('videocall/summary.html', videocall=videocall, appointment=appointment)

    call = {
        'room_id': videocall.room_id,
        'appointment_id': videocall.appointment_id,
        'doctor_name': appointment.doctor.full_name if appointment.doctor else '',
        'patient_name': appointment.patient.full_name if appointment.patient else '',
    }
    return render_template('videocall/room.html', videocall=videocall, appointment=appointment, call=call)


@videocall_bp.route('/start/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
def start(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    # If videocall already exists, rejoin the room
    if appointment.videocall:
        return redirect(url_for('videocall.room', room_id=appointment.videocall.room_id))

    # Only allow starting a call from valid statuses
    if appointment.status in ('completed', 'cancelled'):
        flash('Нельзя начать звонок для завершённого или отменённого приёма.', 'danger')
        return redirect(url_for('patient.index') if current_user.role == 'patient' else url_for('doctor.dashboard'))

    room_id = str(uuid.uuid4())

    videocall = VideoCall(
        appointment_id=appointment.id,
        room_id=room_id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status='active',
    )

    if appointment.status == 'scheduled':
        appointment.status = 'in_progress'

    db.session.add(videocall)
    db.session.commit()

    return redirect(url_for('videocall.room', room_id=room_id))


@videocall_bp.route('/end/<room_id>', methods=['POST'])
@login_required
@csrf.exempt
def end(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first() or abort(404)
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    videocall.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if videocall.started_at:
        videocall.duration_seconds = int((videocall.ended_at - videocall.started_at).total_seconds())
    videocall.status = 'ended'

    # Auto-complete appointment once the call ends
    if appointment.status in ('scheduled', 'in_progress', 'awaiting_report'):
        appointment.status = 'completed'

    db.session.commit()

    flash('Видеозвонок завершён.', 'success')
    if current_user.role == 'patient':
        return redirect(url_for('patient.index'))
    # Redirect doctor to patient detail so they can fill prescription/records
    return redirect(url_for('doctor.patient_detail', patient_id=appointment.patient_id))


@videocall_bp.route('/transcribe/<room_id>', methods=['POST'])
@login_required
@csrf.exempt
def transcribe(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first() or abort(404)
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    data = request.get_json()
    if not data or not data.get('transcription'):
        return jsonify({'error': 'Текст транскрипции отсутствует'}), 400

    # Skip if transcription was already saved (prevents duplicate notifications
    # when both participants end the call and send transcription)
    if videocall.transcription:
        return jsonify({'status': 'already_saved', 'summary': videocall.summary})

    transcription_text = data['transcription'][:50000]  # limit length
    videocall.transcription = transcription_text

    # Generate AI summary via tpool-isolated call
    from app.ai import chat_completion
    summary_messages = [
        {
            'role': 'system',
            'content': (
                'Вы — медицинский ассистент. Создайте краткое резюме телемедицинской консультации '
                'на основе транскрипции разговора врача и пациента. Укажите основные жалобы, '
                'рекомендации врача и ключевые моменты. Отвечайте на русском языке.'
            ),
        },
        {
            'role': 'user',
            'content': f'<transcription>\n{transcription_text}\n</transcription>\n\nСоздайте краткое резюме.',
        },
    ]
    summary, error = chat_completion(summary_messages, max_tokens=1000, temperature=0.3)
    if summary:
        videocall.summary = summary
    elif error:
        logger.warning('Transcription summary failed: %s', error)

    db.session.commit()

    # Create notifications for both doctor and patient
    patient_name = appointment.patient.full_name if appointment.patient else 'Пациент'
    doctor_name = appointment.doctor.full_name if appointment.doctor else 'Врач'
    room_link = url_for('videocall.room', room_id=room_id)

    doctor_notification = Notification(
        user_id=appointment.doctor_id,
        title='Транскрипция консультации готова',
        message=f'Транскрипция видеоконсультации с пациентом {patient_name} сохранена.',
        type='info',
        link=room_link,
    )
    patient_notification = Notification(
        user_id=appointment.patient_id,
        title='Транскрипция консультации готова',
        message=f'Транскрипция видеоконсультации с доктором {doctor_name} сохранена.',
        type='info',
        link=room_link,
    )

    db.session.add(doctor_notification)
    db.session.add(patient_notification)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'summary': summary
    })


# SocketIO event handlers for WebRTC signaling

# Track active participants per room: {room_id: set(sid)}
_room_participants = {}


def _is_room_participant(room_id):
    """Check if current_user is authenticated and is a participant of the given room."""
    if not current_user.is_authenticated:
        return False
    if not room_id:
        return False
    videocall = VideoCall.query.filter_by(room_id=room_id).first()
    if not videocall:
        return False
    appointment = videocall.appointment
    return current_user.id in (appointment.doctor_id, appointment.patient_id)


@socketio.on('join_room')
def handle_join_room(data):
    room_id = data.get('room_id')
    if not _is_room_participant(room_id):
        emit('error', {'message': 'Доступ запрещён'})
        return

    from flask import request as flask_request
    sid = flask_request.sid

    # Check how many participants are already in the room
    participants = _room_participants.setdefault(room_id, set())
    is_first = len(participants) == 0
    participants.add(sid)

    join_room(room_id)
    logger.info('User %s joined room %s (sid=%s, first=%s, total=%d)',
                current_user.id, room_id, sid, is_first, len(participants))

    # Tell the joining client if they're the initiator (first) or not
    emit('joined', {
        'user_id': current_user.id,
        'is_initiator': is_first,
        'participants_count': len(participants),
    })

    # Notify others that someone joined (they become the offerer)
    if not is_first:
        emit('peer_joined', {'user_id': current_user.id}, to=room_id, include_self=False)


@socketio.on('offer')
def handle_offer(data):
    room_id = data.get('room_id')
    if not _is_room_participant(room_id):
        return
    logger.info('Relaying offer in room %s', room_id)
    emit('offer', data, to=room_id, include_self=False)


@socketio.on('answer')
def handle_answer(data):
    room_id = data.get('room_id')
    if not _is_room_participant(room_id):
        return
    logger.info('Relaying answer in room %s', room_id)
    emit('answer', data, to=room_id, include_self=False)


@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    room_id = data.get('room_id')
    if not _is_room_participant(room_id):
        return
    emit('ice_candidate', data, to=room_id, include_self=False)


@socketio.on('leave_room')
def handle_leave_room(data):
    room_id = data.get('room_id')
    if not room_id:
        return

    from flask import request as flask_request
    sid = flask_request.sid
    if room_id in _room_participants:
        _room_participants[room_id].discard(sid)
        if not _room_participants[room_id]:
            del _room_participants[room_id]

    leave_room(room_id)
    uid = current_user.id if current_user.is_authenticated else None
    emit('user_left', {'user_id': uid}, to=room_id, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    """Clean up room participants on disconnect."""
    from flask import request as flask_request
    sid = flask_request.sid
    for room_id in list(_room_participants.keys()):
        if sid in _room_participants[room_id]:
            _room_participants[room_id].discard(sid)
            if not _room_participants[room_id]:
                del _room_participants[room_id]
            emit('user_left', {}, to=room_id)
