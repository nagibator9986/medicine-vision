from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room
from app import db, socketio, csrf
from app.models import User, Appointment, VideoCall, Notification
from datetime import datetime
import uuid
import os

videocall_bp = Blueprint('videocall', __name__)


@videocall_bp.route('/room/<room_id>')
@login_required
def room(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first_or_404()
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    return render_template('videocall/room.html', videocall=videocall, appointment=appointment)


@videocall_bp.route('/start/<int:appointment_id>', methods=['POST'])
@login_required
def start(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    if appointment.videocall:
        return redirect(url_for('videocall.room', room_id=appointment.videocall.room_id))

    room_id = str(uuid.uuid4())

    videocall = VideoCall(
        appointment_id=appointment.id,
        room_id=room_id,
        started_at=datetime.utcnow(),
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

    videocall.ended_at = datetime.utcnow()
    if videocall.started_at:
        videocall.duration_seconds = int((videocall.ended_at - videocall.started_at).total_seconds())
    videocall.status = 'ended'

    appointment.status = 'completed'

    db.session.commit()

    flash('Видеозвонок завершён.', 'success')
    return redirect(url_for('patient.index') if current_user.role == 'patient' else url_for('doctor.dashboard'))


@videocall_bp.route('/transcribe/<room_id>', methods=['POST'])
@login_required
def transcribe(room_id):
    videocall = VideoCall.query.filter_by(room_id=room_id).first_or_404()
    appointment = videocall.appointment

    if current_user.id not in (appointment.doctor_id, appointment.patient_id):
        abort(403)

    data = request.get_json()
    if not data or not data.get('transcription'):
        return jsonify({'error': 'Текст транскрипции отсутствует'}), 400

    transcription_text = data['transcription']
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
                    'content': f'Транскрипция консультации:\n\n{transcription_text}'
                }
            ],
            max_tokens=1000,
            temperature=0.3
        )
        summary = response.choices[0].message.content
        videocall.summary = summary
    except Exception:
        pass

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


csrf.exempt(transcribe)


# SocketIO event handlers for WebRTC signaling

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data.get('room_id')
    if room_id:
        join_room(room_id)
        emit('user_joined', {'user_id': data.get('user_id')}, to=room_id, include_self=False)


@socketio.on('offer')
def handle_offer(data):
    room_id = data.get('room_id')
    if room_id:
        emit('offer', data, to=room_id, include_self=False)


@socketio.on('answer')
def handle_answer(data):
    room_id = data.get('room_id')
    if room_id:
        emit('answer', data, to=room_id, include_self=False)


@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    room_id = data.get('room_id')
    if room_id:
        emit('ice_candidate', data, to=room_id, include_self=False)


@socketio.on('leave_room')
def handle_leave_room(data):
    room_id = data.get('room_id')
    if room_id:
        leave_room(room_id)
        emit('user_left', {'user_id': data.get('user_id')}, to=room_id, include_self=False)
