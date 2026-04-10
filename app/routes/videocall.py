import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
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

    call = {
        'room_id': videocall.room_id,
        'appointment_id': videocall.appointment_id,
        'doctor_name': appointment.doctor.full_name if appointment.doctor else '',
        'patient_name': appointment.patient.full_name if appointment.patient else '',
    }
    return render_template('videocall/room.html', videocall=videocall, appointment=appointment, call=call)


@videocall_bp.route('/start/<int:appointment_id>', methods=['POST'])
@login_required
def start(appointment_id):
    appointment = db.session.get(Appointment, appointment_id) or abort(404)

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    if appointment.videocall:
        return redirect(url_for('videocall.room', room_id=appointment.videocall.room_id))

    room_id = str(uuid.uuid4())

    videocall = VideoCall(
        appointment_id=appointment.id,
        room_id=room_id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status='active'
    )

    appointment.status = 'in_progress'

    db.session.add(videocall)
    db.session.commit()

    return redirect(url_for('videocall.room', room_id=room_id))


@videocall_bp.route('/end/<room_id>', methods=['POST'])
@login_required
def end(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first_or_404()
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    videocall.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if videocall.started_at:
        videocall.duration_seconds = int((videocall.ended_at - videocall.started_at).total_seconds())
    videocall.status = 'ended'

    appointment.status = 'completed'

    db.session.commit()

    flash('Видеозвонок завершён.', 'success')
    return redirect(url_for('patient.index') if current_user.role == 'patient' else url_for('doctor.dashboard'))


@videocall_bp.route('/transcribe/<room_id>', methods=['POST'])
@login_required
@csrf.exempt
def transcribe(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first_or_404()
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    data = request.get_json()
    if not data or not data.get('transcription'):
        return jsonify({'error': 'Текст транскрипции отсутствует'}), 400

    transcription_text = data['transcription'][:50000]  # limit length
    videocall.transcription = transcription_text

    # Generate AI summary
    summary = None
    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Вы — медицинский ассистент. Создайте краткое резюме телемедицинской консультации '
                        'на основе транскрипции разговора врача и пациента. Укажите основные жалобы, '
                        'рекомендации врача и ключевые моменты. Отвечайте на русском языке.'
                    )
                },
                {
                    'role': 'user',
                    'content': f'<transcription>\n{transcription_text}\n</transcription>\n\nСоздайте краткое резюме вышеуказанной транскрипции.'
                }
            ],
            max_tokens=1000,
            temperature=0.3
        )
        if response.choices and response.choices[0].message:
            summary = response.choices[0].message.content
        videocall.summary = summary
    except Exception as e:
        logger.error('OpenAI transcription summary error: %s', e)

    db.session.commit()

    # Create notifications for both doctor and patient
    doctor_notification = Notification(
        user_id=appointment.doctor_id,
        title='Транскрипция консультации готова',
        message=f'Транскрипция видеоконсультации с пациентом {appointment.patient.full_name} сохранена.',
        type='info',
        link=url_for('videocall.room', room_id=room_id)
    )
    patient_notification = Notification(
        user_id=appointment.patient_id,
        title='Транскрипция консультации готова',
        message=f'Транскрипция видеоконсультации с доктором {appointment.doctor.full_name} сохранена.',
        type='info',
        link=url_for('videocall.room', room_id=room_id)
    )

    db.session.add(doctor_notification)
    db.session.add(patient_notification)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'summary': summary
    })


# SocketIO event handlers for WebRTC signaling


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
    join_room(room_id)
    emit('user_joined', {'user_id': current_user.id}, to=room_id, include_self=False)


@socketio.on('offer')
def handle_offer(data):
    room_id = data.get('room_id')
    if not _is_room_participant(room_id):
        return
    emit('offer', data, to=room_id, include_self=False)


@socketio.on('answer')
def handle_answer(data):
    room_id = data.get('room_id')
    if not _is_room_participant(room_id):
        return
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
    if not _is_room_participant(room_id):
        return
    leave_room(room_id)
    emit('user_left', {'user_id': current_user.id}, to=room_id, include_self=False)
