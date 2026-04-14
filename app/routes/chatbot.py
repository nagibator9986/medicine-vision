import logging

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db, csrf
from app.models import ChatMessage
from app.ai import chat_completion

logger = logging.getLogger(__name__)

chatbot_bp = Blueprint('chatbot', __name__)

SYSTEM_PROMPT = (
    "Вы — медицинский AI-ассистент на платформе телемедицины MediPlatform. "
    "Помогайте пользователям с общими медицинскими вопросами, "
    "напоминайте о важности консультации с врачом для точного диагноза. "
    "Отвечайте на русском языке. Будьте вежливы и профессиональны. "
    "НЕ ставьте диагнозы, а рекомендуйте обратиться к специалисту. "
    "Используйте markdown-форматирование: **жирный** для ключевых терминов, "
    "- списки для перечислений симптомов или рекомендаций, "
    "### заголовки для разделения тем. "
    "Держите ответы структурированными и лаконичными."
)

MAX_HISTORY_MESSAGES = 50


@chatbot_bp.route('/')
@login_required
def chat():
    if current_user.role != 'patient':
        flash('Чат-бот доступен только для пациентов.', 'warning')
        from app.routes.auth import ROLE_REDIRECTS
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role, 'auth.login')))

    chat_history = ChatMessage.query.filter_by(user_id=current_user.id)\
        .order_by(ChatMessage.created_at.asc()).all()

    return render_template('chatbot/chat.html', chat_history=chat_history)


@chatbot_bp.route('/send', methods=['POST'])
@login_required
@csrf.exempt
def send():
    if current_user.role != 'patient':
        return jsonify({'error': 'Доступ запрещён'}), 403

    data = request.get_json()
    if not data or not data.get('message'):
        return jsonify({'error': 'Сообщение не может быть пустым'}), 400

    user_message_text = data['message'].strip()
    if not user_message_text:
        return jsonify({'error': 'Сообщение не может быть пустым'}), 400

    # Save user message
    user_message = ChatMessage(
        user_id=current_user.id,
        role='user',
        content=user_message_text,
    )
    db.session.add(user_message)
    db.session.commit()

    # Build conversation history for OpenAI
    history = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    history.reverse()

    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for msg in history:
        messages.append({'role': msg.role, 'content': msg.content})

    # Get AI response via tpool-isolated call
    response_text, error = chat_completion(messages)
    assistant_text = response_text or error or 'Извините, сервис временно недоступен.'

    # Save assistant response
    assistant_message = ChatMessage(
        user_id=current_user.id,
        role='assistant',
        content=assistant_text,
    )
    db.session.add(assistant_message)
    db.session.commit()

    return jsonify({
        'response': assistant_text,
        'timestamp': assistant_message.created_at.strftime('%H:%M'),
    })


@chatbot_bp.route('/clear', methods=['POST'])
@login_required
@csrf.exempt
def clear():
    if current_user.role != 'patient':
        return jsonify({'error': 'Доступ запрещён'}), 403

    ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()

    return jsonify({'status': 'success'})
