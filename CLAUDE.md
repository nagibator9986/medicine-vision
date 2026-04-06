# MediPlatform — Development Guide

## Project Overview
Kazakhstani telemedicine platform (Flask + SQLite/PostgreSQL). Four roles: superadmin, clinic_admin, doctor, patient. Features: appointment booking, video consultations (WebRTC), AI chatbot (OpenAI), e-prescriptions, health tracker.

## Quick Start
```bash
source venv/bin/activate
flask --app run:app init-db   # seed demo data
python run.py                  # http://localhost:5050
python -m pytest tests/ -v     # 85 tests
```

## Architecture
- **Backend**: Flask 3.0, Flask-SQLAlchemy, Flask-Login, Flask-SocketIO, Flask-WTF
- **Frontend**: Jinja2 templates, Bootstrap 5.3, Font Awesome 6, vanilla JS
- **DB**: SQLite (dev), PostgreSQL (prod). Single User model with role field (no STI)
- **AI**: OpenAI GPT-4o-mini for chatbot and video transcription summaries

## Key Conventions
- All routes use blueprint pattern (`auth_bp`, `admin`, `clinic`, `doctor`, `patient_bp`, etc.)
- Role guards via decorators: `@superadmin_required`, `@clinic_admin_required`, `@doctor_required`, `@patient_required`
- Templates extend `base.html` which has role-based navbar
- Currency: Kazakhstani Tenge (₸). Locale: KZ. Emails: `.kz` domain
- Datetime: use `datetime.now(timezone.utc)`, never `datetime.utcnow()`
- DB queries: use `db.session.get(Model, id)`, never `Model.query.get(id)`
- File uploads go to `app/static/uploads/` with UUID-based names
- Forms: Flask-WTF with CSRF. API endpoints exempt via `csrf.exempt()`

## Project Structure
```
app/
  __init__.py        — create_app factory, extensions init
  models.py          — User, Clinic, Appointment, VideoCall, Prescription, MedicalRecord, etc.
  forms.py           — WTForms classes
  routes/            — Blueprints (auth, admin, clinic, doctor, patient, videocall, chatbot, api)
  templates/         — Jinja2 (admin/, auth/, clinic/, doctor/, patient/, videocall/, chatbot/)
  static/css/        — style.css (custom properties theming)
  static/js/         — main.js (notifications, tooltips, ratings)
  static/uploads/    — User uploads (avatars, logos, records)
config.py            — Config class with env vars
run.py               — Entry point + CLI init-db command
tests/               — pytest (conftest.py has fixtures for all roles)
```

## Testing
- Tests use in-memory SQLite, CSRF disabled, `TestConfig` in conftest.py
- Fixtures: `client`, `clinic`, `superadmin`, `doctor_user`, `patient_user`, `clinic_admin_user`, `appointment`
- `login(client, email)` helper for auth in tests
- Test emails use `@test.kz` domain

## Design System
- Primary: `#667eea` (indigo-violet gradient)
- Colors defined as CSS custom properties in `:root`
- Bootstrap 5.3 utilities preferred over custom CSS
- Responsive: mobile-first, Bootstrap grid
- Icons: Font Awesome 6 (`fas fa-*`)
