"""
OpenAI integration via raw HTTP requests.

Uses requests library directly instead of OpenAI SDK to avoid
httpx dependency conflicts with async workers (eventlet/gevent).
"""
import logging
import os
import time
from typing import Optional

import requests as http

logger = logging.getLogger(__name__)

OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1  # seconds


def _get_api_key() -> str:
    """Resolve OpenAI API key from all possible sources."""
    from flask import current_app
    return (
        current_app.config.get('OPENAI_API_KEY', '')
        or os.environ.get('OPENAI_API_KEY', '')
    )


def chat_completion(messages: list, max_tokens: int = 1000,
                    temperature: float = 0.7,
                    model: str = 'gpt-4o-mini') -> tuple[Optional[str], Optional[str]]:
    """
    Get a chat completion from OpenAI via raw HTTP POST.

    Returns:
        (response_text, error_message) — one of them is always None.
    """
    api_key = _get_api_key()
    if not api_key or api_key == 'your-openai-api-key-here':
        logger.warning('OPENAI_API_KEY not configured')
        return None, 'AI-ассистент не настроен. Обратитесь к администратору.'

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = http.post(
                OPENAI_API_URL,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': messages,
                    'max_tokens': max_tokens,
                    'temperature': temperature,
                },
                timeout=45,
            )

            if resp.status_code == 429:
                # Rate limited — retry with exponential backoff
                retry_after = resp.headers.get('Retry-After')
                delay = float(retry_after) if retry_after else RETRY_BASE_DELAY * (2 ** attempt)
                delay = min(delay, 10)  # cap at 10 seconds
                logger.warning('OpenAI 429 rate limited, retrying in %.1fs (attempt %d/%d)',
                               delay, attempt + 1, MAX_RETRIES)
                last_error = 'AI-сервис перегружен. Попробуйте через несколько секунд.'
                time.sleep(delay)
                continue

            if resp.status_code != 200:
                error_body = resp.text[:300]
                logger.error('OpenAI API %d: %s', resp.status_code, error_body)
                return None, f'Ошибка AI-сервиса (HTTP {resp.status_code}).'

            data = resp.json()
            choices = data.get('choices', [])
            if choices and choices[0].get('message', {}).get('content'):
                return choices[0]['message']['content'], None

            return None, 'AI-сервис вернул пустой ответ.'

        except http.exceptions.Timeout:
            logger.error('OpenAI API timeout (attempt %d/%d)', attempt + 1, MAX_RETRIES)
            last_error = 'AI-сервис не ответил вовремя. Попробуйте позже.'
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
        except http.exceptions.ConnectionError as e:
            logger.error('OpenAI connection error: %s', e)
            return None, 'Не удалось подключиться к AI-сервису.'
        except Exception as e:
            logger.error('OpenAI unexpected error: %s: %s', type(e).__name__, e)
            return None, f'Ошибка: {type(e).__name__}'

    return None, last_error or 'AI-сервис временно недоступен.'
