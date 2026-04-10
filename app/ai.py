"""
OpenAI integration layer — isolates API calls from eventlet monkey-patching.

Eventlet monkey-patches Python sockets which breaks httpx (used by OpenAI SDK).
All OpenAI calls go through eventlet.tpool.execute() which runs them in native
OS threads with unpatched sockets.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Resolve OpenAI API key from all possible sources."""
    from flask import current_app
    return (
        current_app.config.get('OPENAI_API_KEY', '')
        or os.environ.get('OPENAI_API_KEY', '')
    )


def _call_openai_sync(api_key: str, messages: list, max_tokens: int = 1000,
                       temperature: float = 0.7) -> str:
    """
    Make a synchronous OpenAI API call in a clean (unpatched) thread context.
    This function is called via tpool.execute() to bypass eventlet patching.
    """
    import openai
    client = openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=2)
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if response.choices and response.choices[0].message:
        return response.choices[0].message.content
    return ''


def chat_completion(messages: list, max_tokens: int = 1000,
                    temperature: float = 0.7) -> tuple[Optional[str], Optional[str]]:
    """
    Get a chat completion from OpenAI.

    Returns:
        (response_text, error_message) — one of them is always None.
    """
    api_key = _get_api_key()
    if not api_key or api_key == 'your-openai-api-key-here':
        logger.warning('OPENAI_API_KEY not configured')
        return None, 'AI-ассистент не настроен. Обратитесь к администратору.'

    try:
        # Try eventlet.tpool first (production with eventlet worker)
        try:
            import eventlet.tpool
            result = eventlet.tpool.execute(
                _call_openai_sync, api_key, messages, max_tokens, temperature
            )
        except ImportError:
            # No eventlet (local dev with threading) — call directly
            result = _call_openai_sync(api_key, messages, max_tokens, temperature)

        if result:
            return result, None
        return None, 'AI-сервис вернул пустой ответ.'

    except Exception as e:
        logger.error('OpenAI API error: %s: %s', type(e).__name__, e)
        return None, f'Ошибка AI-сервиса: {type(e).__name__}'
