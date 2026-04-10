import logging
import os

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import db, csrf
from app.models import ChatMessage

logger = logging.getLogger(__name__)

chatbot_bp = Blueprint('chatbot', __name__)

SYSTEM_PROMPT = (
    "Вы — медицинский AI-ассистент на платформе телемедицины. "
    "Помогайте пользователям с общими медицинскими вопросами, "
    "напоминайте о важности консультации с врачом для точного диагноза. "
    "Отвечайте на русском языке. Будьте вежливы и профессиональны. "
    "НЕ ставьте диагнозы, а рекомендуйте обратиться к специалисту."
)

MAX_HISTORY_MESSAGES = 50  # Limit messages sent to OpenAI to control token usage


@chatbot_bp.route('/')
@login_required
def chat():
    if current_user.role != 'patient':
        flash('Чат-бот доступен только для пациентов.', 'warning')
        return redirect(url_for('auth.login'))

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
        content=user_message_text
    )
    db.session.add(user_message)
    db.session.commit()

    # Build conversation history for OpenAI — limited to last N messages
    history = (
        ChatMessage.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    history.reverse()  # chronological order

    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for msg in history:
        messages.append({'role': msg.role, 'content': msg.content})

    # Get AI response
    assistant_text = None
    try:
        import openai
        api_key = os.environ.get('OPENAI_API_KEY', '') or current_app.config.get('OPENAI_API_KEY', '')
        if not api_key or api_key == 'your-openai-api-key-here':
            logger.warning('OPENAI_API_KEY not configured — chatbot disabled')
            assistant_text = 'AI-ассистент не настроен. Обратитесь к администратору для настройки OPENAI_API_KEY.'
        else:
            logger.info('Calling OpenAI with key: %s...%s', api_key[:8], api_key[-4:])
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            if response.choices and response.choices[0].message:
                assistant_text = response.choices[0].message.content
            else:
                assistant_text = 'AI-сервис вернул пустой ответ. Попробуйте переформулировать вопрос.'
    except Exception as e:
        logger.error('OpenAI chatbot error: %s', e)
        assistant_text = f'Ошибка AI: {type(e).__name__}. Попробуйте позже.'

    if not assistant_text:
        assistant_text = 'Извините, сервис временно недоступен. Попробуйте позже.'

    # Save assistant response
    assistant_message = ChatMessage(
        user_id=current_user.id,
        role='assistant',
        content=assistant_text
    )
    db.session.add(assistant_message)
    db.session.commit()

    return jsonify({
        'response': assistant_text,
        'timestamp': assistant_message.created_at.strftime('%H:%M')
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


