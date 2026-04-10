"""
OpenAI integration via raw HTTP — bypasses httpx/eventlet conflicts.

The OpenAI Python SDK uses httpx which breaks under eventlet monkey-patching.
Instead, we call the OpenAI Chat Completions API directly via requests,
which is eventlet-compatible.
"""
import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'

# Force DNS resolution via Google/Cloudflare if system DNS fails
def _patch_dns():
    """Add fallback DNS resolvers for Railway containers with broken DNS."""
    try:
        import socket
        # Test if we can resolve openai
        socket.getaddrinfo('api.openai.com', 443, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        logger.warning('System DNS cannot resolve api.openai.com, patching resolv.conf')
        try:
            with open('/etc/resolv.conf', 'a') as f:
                f.write('\nnameserver 8.8.8.8\nnameserver 1.1.1.1\n')
        except PermissionError:
            logger.error('Cannot write to /etc/resolv.conf')

_patch_dns()


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

    try:
        resp = requests.post(
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

        if resp.status_code != 200:
            error_body = resp.text[:300]
            logger.error('OpenAI API %d: %s', resp.status_code, error_body)
            return None, f'Ошибка AI-сервиса (HTTP {resp.status_code}).'

        data = resp.json()
        choices = data.get('choices', [])
        if choices and choices[0].get('message', {}).get('content'):
            return choices[0]['message']['content'], None

        return None, 'AI-сервис вернул пустой ответ.'

    except requests.exceptions.Timeout:
        logger.error('OpenAI API timeout')
        return None, 'AI-сервис не ответил вовремя. Попробуйте позже.'
    except requests.exceptions.ConnectionError as e:
        logger.error('OpenAI connection error: %s', e)
        return None, 'Не удалось подключиться к AI-сервису.'
    except Exception as e:
        logger.error('OpenAI unexpected error: %s: %s', type(e).__name__, e)
        return None, f'Ошибка: {type(e).__name__}'
