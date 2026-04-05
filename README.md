# MediPlatform

Телемедицинская платформа для казахстанского рынка. Онлайн-запись к врачу, видеоконсультации, AI-чатбот, электронные рецепты и медицинские записи.

## Возможности

- **4 роли**: суперадмин, админ клиники, врач, пациент
- **Запись на прием** с автоматическим расчетом свободных слотов
- **Видеоконсультации** (WebRTC + SocketIO)
- **AI-чатбот** (OpenAI GPT) для медицинских вопросов
- **Электронные рецепты** и медицинские записи
- **Трекер здоровья** — самостоятельная запись симптомов
- **Аналитика и статистика** для клиник и администраторов
- **Уведомления** в реальном времени

## Требования

- Python 3.10+
- pip
- (Опционально) PostgreSQL для продакшена

## Установка и запуск с нуля

### 1. Клонирование репозитория

```bash
git clone https://github.com/nagibator9986/medicine-vision.git
cd medicine-vision
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
```

Активация:

```bash
# macOS / Linux
source venv/bin/activate

# Windows (CMD)
venv\Scripts\activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Скопируйте файл-пример и отредактируйте:

```bash
cp .env-example .env
```

Откройте `.env` в любом текстовом редакторе и заполните:

```env
# Обязательно замените на случайную строку:
SECRET_KEY=ваш-секретный-ключ

# Вставьте ваш OpenAI API ключ (нужен для AI-чатбота):
OPENAI_API_KEY=sk-proj-ваш-ключ
```

Сгенерировать надежный SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> Без `OPENAI_API_KEY` приложение работает, но чат-бот будет отвечать заглушкой "Сервис временно недоступен".

### 5. Инициализация базы данных

```bash
flask --app run:app init-db
```

Будут созданы демо-аккаунты:

| Роль | Email | Пароль |
|---|---|---|
| Суперадмин | `admin@mediplatform.kz` | `admin123` |
| Админ клиники | `clinic@mediplatform.kz` | `clinic123` |
| Врач | `doctor@mediplatform.kz` | `doctor123` |
| Пациент | `patient@mediplatform.kz` | `patient123` |

### 6. Запуск сервера

```bash
python run.py
```

Приложение доступно по адресу: **http://localhost:5050**

## Запуск тестов

```bash
pip install pytest
python -m pytest tests/ -v
```

## Структура проекта

```
medicine-vision/
├── app/
│   ├── __init__.py          # Фабрика приложения Flask
│   ├── models.py            # Модели БД (User, Clinic, Appointment...)
│   ├── forms.py             # WTForms формы
│   ├── routes/
│   │   ├── auth.py          # Авторизация, регистрация
│   │   ├── admin.py         # Панель суперадмина
│   │   ├── clinic.py        # Панель админа клиники
│   │   ├── doctor.py        # Кабинет врача
│   │   ├── patient.py       # Кабинет пациента
│   │   ├── videocall.py     # Видеоконсультации (WebRTC)
│   │   ├── chatbot.py       # AI-чатбот (OpenAI)
│   │   └── api.py           # REST API
│   ├── templates/           # Jinja2 HTML-шаблоны
│   └── static/              # CSS, JS, загруженные файлы
├── tests/                   # Тесты (pytest)
├── config.py                # Конфигурация
├── run.py                   # Точка входа + CLI init-db
├── requirements.txt         # Зависимости Python
├── .env-example             # Пример переменных окружения
└── .gitignore
```

## Технологии

- **Backend**: Flask, Flask-SQLAlchemy, Flask-Login, Flask-SocketIO
- **Frontend**: Jinja2, Bootstrap 5, Font Awesome
- **БД**: SQLite (dev) / PostgreSQL (prod)
- **AI**: OpenAI GPT-4o-mini
- **Видео**: WebRTC + Socket.IO
- **Тесты**: pytest
