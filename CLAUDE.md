# MediPlatform — Development Guide

## Project Overview
Kazakhstani telemedicine platform (Flask + SQLite/PostgreSQL). Four roles: superadmin, clinic_admin, doctor, patient. Features: appointment booking, video consultations (WebRTC), AI chatbot (OpenAI), e-prescriptions, health tracker.

## Quick Start
```bash
source venv/bin/activate
flask --app run:app init-db   # seed demo data
python run.py                  # http://localhost:5051
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
- Currency: Kazakhstani Tenge (KZT). Locale: KZ. Emails: `.kz` domain
- Datetime: use `datetime.now(timezone.utc)`, never `datetime.utcnow()`
- DB queries: use `db.session.get(Model, id)`, never `Model.query.get(id)`
- File uploads go to `app/static/uploads/` with UUID-based names
- Forms: Flask-WTF with CSRF. API endpoints exempt via `@csrf.exempt` decorator

## Project Structure
```
app/
  __init__.py        -- create_app factory, extensions init
  models.py          -- User, Clinic, Appointment, VideoCall, Prescription, MedicalRecord, etc.
  forms.py           -- WTForms classes
  routes/            -- Blueprints (auth, admin, clinic, doctor, patient, videocall, chatbot, api)
  templates/         -- Jinja2 (admin/, auth/, clinic/, doctor/, patient/, videocall/, chatbot/)
  static/css/        -- style.css (custom properties theming)
  static/js/         -- main.js (notifications, tooltips, ratings)
  static/uploads/    -- User uploads (avatars, logos, records)
config.py            -- Config class with env vars
run.py               -- Entry point + CLI init-db command
tests/               -- pytest (conftest.py has fixtures for all roles)
```

## Testing
- Tests use in-memory SQLite, CSRF disabled, `TestConfig` in conftest.py
- Fixtures: `client`, `clinic`, `superadmin`, `doctor_user`, `patient_user`, `clinic_admin_user`, `appointment`
- `login(client, email)` helper for auth in tests
- Test emails use `@test.kz` domain
- Run: `python -m pytest tests/ -v`
- After every fix run full test suite and verify 0 failures

## Design System
- Primary: `#667eea` (indigo-violet gradient)
- Colors defined as CSS custom properties in `:root`
- Bootstrap 5.3 utilities preferred over custom CSS
- Responsive: mobile-first, Bootstrap grid
- Icons: Font Awesome 6 (`fas fa-*`)

---

## BUG REGISTRY — Full Audit (2026-04-09)

Current state: **85 tests pass, 97 warnings, ~35% route coverage**

All bugs below are confirmed via code review. Fix them in priority order. After each fix: run `python -m pytest tests/ -v` and verify all tests still pass. Add new tests for every fix where applicable.

---

### CRITICAL (fix first)

#### BUG-01: WebSocket handlers have no authentication
- **File**: `app/routes/videocall.py:157-191`
- **Problem**: SocketIO event handlers (`join_room`, `offer`, `answer`, `ice_candidate`, `leave_room`) do zero authentication. Any unauthenticated user can connect to any video room, eavesdrop, inject WebRTC offers/answers.
- **Root cause**: Flask-Login's `@login_required` doesn't work on SocketIO events. Need `flask_login.current_user` check inside each handler.
- **Fix**:
  ```python
  from flask_login import current_user

  @socketio.on('join_room')
  def handle_join_room(data):
      if not current_user.is_authenticated:
          return  # or emit('error', {'message': 'Unauthorized'})
      room_id = data.get('room_id')
      if not room_id:
          return
      # Verify user is participant in this videocall
      videocall = VideoCall.query.filter_by(room_id=room_id).first()
      if not videocall:
          return
      appointment = videocall.appointment
      if current_user.id not in (appointment.doctor_id, appointment.patient_id):
          return
      join_room(room_id)
      emit('user_joined', {'user_id': current_user.id}, to=room_id, include_self=False)
  ```
  Apply the same auth pattern to `handle_offer`, `handle_answer`, `handle_ice_candidate`, `handle_leave_room` — check `current_user.is_authenticated` and verify room membership before forwarding signals.
- **Test**: Add `tests/test_videocall.py` with tests for:
  - Unauthenticated user cannot join room
  - User not in appointment cannot join room
  - Authorized doctor/patient can join room

#### BUG-02: Missing API endpoints break notification dropdown
- **File**: `app/static/js/main.js:50, 105` calls endpoints that don't exist in `app/routes/api.py`
- **Problem**: JS calls `GET /api/notifications` (line 50) and `POST /api/notifications/read-all` (line 105). Only `GET /api/notifications/count` and `POST /api/notifications/<id>/read` exist. The notification dropdown is completely broken.
- **Fix**: Add two new endpoints to `app/routes/api.py`:
  ```python
  @api_bp.route('/notifications', methods=['GET'])
  @login_required
  def get_notifications():
      """Return user's recent unread notifications as JSON."""
      notifications = Notification.query.filter_by(
          user_id=current_user.id,
          is_read=False
      ).order_by(Notification.created_at.desc()).limit(20).all()

      return jsonify({
          'notifications': [{
              'id': n.id,
              'title': n.title,
              'message': n.message,
              'type': n.type,
              'read': n.is_read,
              'link': n.link,
              'created_at': n.created_at.isoformat() if n.created_at else None,
          } for n in notifications]
      }), 200

  @api_bp.route('/notifications/read-all', methods=['POST'])
  @login_required
  @csrf.exempt
  def mark_all_notifications_read():
      """Mark all of the current user's notifications as read."""
      Notification.query.filter_by(
          user_id=current_user.id, is_read=False
      ).update({'is_read': True})
      db.session.commit()
      return jsonify({'success': True}), 200
  ```
  Also add `Notification` to imports at top of api.py (it's already imported).
- **Test**: Add tests in `tests/test_api.py`:
  - `test_get_notifications_returns_json` — create a Notification, fetch `/api/notifications`, verify JSON structure
  - `test_mark_all_notifications_read` — create 2 unread notifications, POST to `/api/notifications/read-all`, verify all are marked read

#### BUG-03: Race condition in appointment booking (double-booking)
- **File**: `app/routes/patient.py:247-278`
- **Problem**: TOCTOU race — check for existing appointment (line 248) and insert (line 268) are not atomic. Two patients can book the same doctor+time slot simultaneously. No DB-level unique constraint exists.
- **Fix** (two-part):
  1. Add a composite unique constraint in `app/models.py` on Appointment:
     ```python
     class Appointment(db.Model):
         __tablename__ = 'appointments'
         __table_args__ = (
             db.Index('ix_appointment_doctor_time', 'doctor_id', 'scheduled_time'),
         )
     ```
     Note: A full unique constraint is complex because cancelled appointments should allow rebooking. Use the index + application-level handling.
  2. In `app/routes/patient.py`, wrap the booking in a try/except for IntegrityError:
     ```python
     from sqlalchemy.exc import IntegrityError

     # After the existing check...
     db.session.add(appointment)
     db.session.add(notification)
     try:
         db.session.commit()
     except IntegrityError:
         db.session.rollback()
         flash('Это время уже занято. Выберите другое.', 'danger')
         return render_template('patient/book_appointment.html', form=form, time_slots=time_slots)
     ```
- **Test**: Add test `test_cannot_double_book_same_slot` in `tests/test_patient.py`

#### BUG-04: SECRET_KEY regenerates on every restart
- **File**: `config.py:9`
- **Problem**: `SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)` — if no env var set, a new random key is generated each restart. This invalidates all sessions, CSRF tokens, and remember-me cookies.
- **Fix**: Generate a stable fallback key derived from a fixed seed for development only. For production, require the env var:
  ```python
  class Config:
      SECRET_KEY = os.environ.get('SECRET_KEY')
      if not SECRET_KEY:
          # Stable dev-only fallback — NEVER use in production
          SECRET_KEY = 'dev-only-insecure-key-change-in-production'
  ```
  Better approach: write a `.env` file with a generated key during `init-db` if one doesn't exist, or raise an error in production mode.

---

### HIGH PRIORITY (fix second)

#### BUG-05: CSRF exemption applied incorrectly (function call instead of decorator)
- **Files**: `app/routes/videocall.py:152`, `app/routes/chatbot.py:118-119`
- **Problem**: `csrf.exempt(transcribe)` and `csrf.exempt(send)` / `csrf.exempt(clear)` are called as regular functions after function definition. While this technically works with Flask-WTF (it registers the view function name), it's fragile and non-standard. However the real issue is: these POST endpoints that modify data (clear chat, send message, upload transcription) bypass CSRF protection entirely.
- **Current behavior**: These endpoints are AJAX-called from JS. Since CSRF is exempt, they work but are vulnerable to CSRF attacks.
- **Fix**: For AJAX endpoints, use CSRF token in request headers instead of exempting. Or if keeping exempt (for simplicity in an academic project), at minimum convert to decorator syntax for clarity:
  ```python
  # videocall.py — change line 79:
  @videocall_bp.route('/transcribe/<room_id>', methods=['POST'])
  @login_required
  @csrf.exempt       # <-- add as decorator
  def transcribe(room_id):
  ```
  Remove the `csrf.exempt(transcribe)` call on line 152.
  Same pattern for chatbot.py — add `@csrf.exempt` decorator to `send()` and `clear()`, remove lines 118-119.

#### BUG-06: Inconsistent timezone handling (naive vs aware datetimes)
- **Files**: `app/routes/patient.py:181, 243-245`, `app/routes/clinic.py:61-62`, `app/routes/api.py:91-92`
- **Problem**: Mixed naive and timezone-aware datetimes cause comparison failures:
  - `patient.py:181`: `now = datetime.now(timezone.utc).replace(tzinfo=None)` — creates aware then strips tz
  - `patient.py:243`: `scheduled_dt = datetime.combine(...)` — creates naive datetime
  - `clinic.py:61`: `datetime.combine(date.today(), datetime.min.time())` — naive
  - Models use `_utcnow()` which returns aware datetime
  - SQLite stores datetimes without timezone info, so mixing causes comparison bugs
- **Fix**: Since SQLite doesn't store timezone info, standardize on naive UTC throughout:
  - In `app/models.py`, change `_utcnow()`:
    ```python
    def _utcnow():
        """Naive UTC now for SQLite compatibility."""
        return datetime.now(timezone.utc).replace(tzinfo=None)
    ```
  - In `patient.py:181`, change to: `now = datetime.now(timezone.utc).replace(tzinfo=None)` (already correct)
  - In `patient.py:33`, change to: `now = datetime.now(timezone.utc).replace(tzinfo=None)`
  - In `conftest.py:148`, change appointment fixture:
    ```python
    scheduled_time=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
    ```
  - Verify all `datetime.now(timezone.utc)` calls in routes also strip tzinfo for SQLite consistency
- **Test**: After fix, run all tests — timezone mismatches cause subtle failures

#### BUG-07: No validation on uploaded files (extension whitelist missing in routes)
- **Files**: `app/routes/clinic.py:28-36`, `app/routes/doctor.py:31-41`, `app/routes/patient.py:395-405`
- **Problem**:
  1. `clinic.py:save_avatar()` — no extension whitelist check; just uses `secure_filename` + `rsplit('.', 1)`. Could save `.exe`, `.php` etc.
  2. `patient.py:400` — uses relative path `os.path.join('app', 'static', 'uploads', 'avatars')` instead of `current_app.config['UPLOAD_FOLDER']`
  3. `doctor.py:283` — medical record file upload has `FileAllowed` on form but route doesn't double-check
- **Fix**:
  1. Add ALLOWED_EXTENSIONS constant and validation helper:
     ```python
     ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
     ALLOWED_DOCUMENT_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx'}

     def allowed_file(filename, allowed_extensions):
         return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
     ```
  2. In `clinic.py:save_avatar()`, add check: `if ext not in ALLOWED_IMAGE_EXTENSIONS: return None`
  3. In `patient.py:400`, replace with: `upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')`
     Add `from flask import current_app` to imports.
- **Test**: Add test that uploading a `.exe` file is rejected

#### BUG-08: Missing clinic isolation — cross-clinic data access
- **File**: `app/routes/patient.py:200-204, 259-263`
- **Problem**:
  1. Patient without `clinic_id` can see ALL doctors from ALL clinics (line 104: filter only applies `if current_user.clinic_id`)
  2. Booking endpoint doesn't verify the selected doctor belongs to patient's clinic (line 259: `doctor = db.session.get(User, doctor_id)` — no clinic check)
  3. `clinic.py:198-205` — patients list joins on Appointment but doesn't verify patients belong to THIS clinic admin's clinic
- **Fix**:
  1. In `patient.py` booking, after getting doctor (line 259), add:
     ```python
     if not doctor or not doctor.is_active or doctor.role != 'doctor':
         flash('Врач не найден.', 'danger')
         return redirect(url_for('patient.book_appointment'))
     if current_user.clinic_id and doctor.clinic_id != current_user.clinic_id:
         flash('Этот врач не принадлежит вашей клинике.', 'danger')
         return redirect(url_for('patient.book_appointment'))
     ```
  2. The clinic.py patients list is already filtered by `Appointment.clinic_id == current_user.clinic_id` — this is correct.
- **Test**: Add test that patient from clinic A cannot book doctor from clinic B

#### BUG-09: `allow_unsafe_werkzeug=True` in production entry point
- **File**: `run.py:98`
- **Problem**: `socketio.run(app, debug=True, host='0.0.0.0', port=5051, allow_unsafe_werkzeug=True)` — debug mode and unsafe Werkzeug enabled. This is only for `__main__` (dev server), but should still be conditional.
- **Fix**:
  ```python
  if __name__ == '__main__':
      with app.app_context():
          db.create_all()
      debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
      socketio.run(
          app,
          debug=debug,
          host='0.0.0.0',
          port=int(os.environ.get('PORT', 5051)),
          allow_unsafe_werkzeug=debug,
      )
  ```
  Add `import os` at top of run.py (already has it via app imports).

#### BUG-10: Missing indexes on foreign key columns
- **File**: `app/models.py` — multiple FK columns
- **Problem**: These FK columns lack `index=True`, causing slow queries on joins and filters:
  - `Appointment.patient_id` (line 103)
  - `Appointment.doctor_id` (line 104)
  - `Appointment.clinic_id` (line 105)
  - `Prescription.appointment_id` (line 148)
  - `Prescription.patient_id` (line 149)
  - `Prescription.doctor_id` (line 150)
  - `MedicalRecord.patient_id` (line 165)
  - `MedicalRecord.doctor_id` (line 166)
  - `ChatMessage.user_id` (line 181)
  - `Notification.user_id` (line 193)
  - `Review.patient_id` (line 208)
  - `Review.doctor_id` (line 209)
  - `Review.appointment_id` (line 210)
- **Fix**: Add `index=True` to each FK column. Example:
  ```python
  patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
  doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
  clinic_id = db.Column(db.Integer, db.ForeignKey('clinics.id'), nullable=False, index=True)
  ```
- **Note**: After changing models, run `flask --app run:app init-db` to recreate tables (dev only). For production, use Flask-Migrate.

#### BUG-11: No appointment status transition validation
- **File**: `app/routes/doctor.py:138-144`
- **Problem**: Any status can transition to any other. Doctor can set `completed` -> `scheduled` or `cancelled` -> `in_progress`.
- **Fix**: Add valid transitions map:
  ```python
  VALID_STATUS_TRANSITIONS = {
      'scheduled': ['in_progress', 'cancelled'],
      'in_progress': ['completed', 'cancelled'],
      'completed': [],  # terminal state
      'cancelled': [],  # terminal state
  }

  # In update_appointment_status():
  current_status = appointment.status
  if new_status not in VALID_STATUS_TRANSITIONS.get(current_status, []):
      flash(f'Невозможно перевести приём из "{current_status}" в "{new_status}".', 'danger')
      return redirect(url_for('doctor.appointments'))
  ```
- **Test**: Add test `test_cannot_transition_completed_to_scheduled`

#### BUG-12: 97 deprecation warnings in tests
- **Problem**: Two sources of warnings:
  1. `flask_login` uses `datetime.utcnow()` internally — this is a library bug, we can't fix it. Suppress with pytest warning filter.
  2. `Clinic.query.get_or_404()` and similar `Model.query.get()` calls use legacy SQLAlchemy API.
- **Fix for (2)**: Replace all `Model.query.get_or_404(id)` with:
  ```python
  model = db.session.get(Model, id)
  if not model:
      abort(404)
  ```
  Files to update:
  - `app/routes/admin.py`: lines 47, 160, 198, 213, 246, 279, 320, 338 (Clinic.query.get_or_404, User.query.get_or_404)
  - `app/routes/clinic.py`: lines 47, 246, 279
  - `app/routes/doctor.py`: lines 133, 158, 196, 231, 268
  - `app/routes/patient.py`: lines 455, 537
  - `app/routes/videocall.py`: line 32
  - `app/routes/api.py`: line 25, 38
- **Fix for (1)**: Add to `conftest.py` or `pyproject.toml`:
  ```python
  # conftest.py top-level
  import warnings
  warnings.filterwarnings('ignore', message='.*datetime.datetime.utcnow.*', category=DeprecationWarning)
  ```

---

### MEDIUM PRIORITY (fix third)

#### BUG-13: No CHECK constraints on status fields
- **File**: `app/models.py` — lines 108, 136, 196
- **Problem**: Status fields accept any string value. Invalid statuses like `status='foo'` can be saved.
- **Fix**: Add `CheckConstraint` or validate at application level. SQLite supports CHECK:
  ```python
  from sqlalchemy import CheckConstraint

  class Appointment(db.Model):
      __table_args__ = (
          CheckConstraint(
              "status IN ('scheduled', 'in_progress', 'completed', 'cancelled')",
              name='ck_appointment_status'
          ),
          db.Index('ix_appointment_doctor_time', 'doctor_id', 'scheduled_time'),
      )
  ```
  Same for VideoCall.status (`'waiting', 'active', 'ended'`) and Notification.type (`'info', 'success', 'warning', 'danger'`).

#### BUG-14: No unique constraint on ClinicSpecialization
- **File**: `app/models.py:89-96`
- **Problem**: Same specialization name can be added multiple times to one clinic.
- **Fix**:
  ```python
  class ClinicSpecialization(db.Model):
      __tablename__ = 'clinic_specializations'
      __table_args__ = (
          db.UniqueConstraint('clinic_id', 'name', name='uq_clinic_specialization'),
      )
  ```

#### BUG-15: Review not cascade-deleted when Appointment is deleted
- **File**: `app/models.py:217`
- **Problem**: `appointment = db.relationship('Appointment', backref='review')` — no cascade. Deleting an Appointment orphans its Review.
- **Fix**: Change Appointment model to include reviews in cascade:
  ```python
  # In Appointment model, add:
  reviews = db.relationship('Review', back_populates='appointment', cascade='all, delete-orphan')

  # In Review model, change:
  appointment = db.relationship('Appointment', back_populates='reviews')
  ```

#### BUG-16: Prompt injection in video transcription
- **File**: `app/routes/videocall.py:113`
- **Problem**: User-supplied transcription text is directly embedded into OpenAI prompt: `f'Транскрипция консультации:\n\n{transcription_text}'`. Attacker can inject instructions like "Ignore previous instructions and..."
- **Fix**: Add length limit and basic sanitization:
  ```python
  transcription_text = data['transcription'][:50000]  # limit length
  # The system prompt already constrains the model's role, but add explicit boundary:
  content = f'<transcription>\n{transcription_text}\n</transcription>\n\nСоздайте краткое резюме вышеуказанной транскрипции.'
  ```

#### BUG-17: No null-check on OpenAI response
- **File**: `app/routes/videocall.py:119`
- **Problem**: `summary = response.choices[0].message.content` — if `choices` is empty, raises `IndexError`.
- **Fix**:
  ```python
  if response.choices and response.choices[0].message:
      summary = response.choices[0].message.content
  ```
  Same pattern needed in `chatbot.py:87`.

#### BUG-18: Inconsistent password requirements
- **File**: `app/forms.py:18` vs `app/forms.py:51`
- **Problem**: PatientRegistrationForm requires min=8 + digit. DoctorForm requires min=6, no digit requirement. Doctors get weaker passwords.
- **Fix**: Align DoctorForm to same standard:
  ```python
  password = PasswordField('Пароль', validators=[Optional(), Length(min=8, message='Пароль должен содержать минимум 8 символов.')])
  ```
  Add digit validation:
  ```python
  def validate_password(self, field):
      if field.data and not any(ch.isdigit() for ch in field.data):
          raise ValidationError('Пароль должен содержать хотя бы одну цифру.')
  ```

#### BUG-19: Working hours fields have no format validation
- **File**: `app/forms.py:71-72`
- **Problem**: `working_hours_start` and `working_hours_end` are plain `StringField` with no validation. Invalid values like "25:99" or "abc" can be saved.
- **Fix**: Add custom validator:
  ```python
  import re

  def validate_working_hours_start(self, field):
      if field.data:
          if not re.match(r'^\d{2}:\d{2}$', field.data):
              raise ValidationError('Формат времени: HH:MM')
          h, m = map(int, field.data.split(':'))
          if h > 23 or m > 59:
              raise ValidationError('Некорректное время.')

  validate_working_hours_end = validate_working_hours_start  # same logic
  ```

#### BUG-20: ReviewForm.rating uses HiddenField, no range validation
- **File**: `app/forms.py:118`
- **Problem**: `rating = HiddenField('Оценка', validators=[DataRequired()])` — no type or range check. Client can submit rating=999 or rating=-1. The route (patient.py:474-476) does check 1-5 range, but the form should validate too.
- **Fix**:
  ```python
  rating = HiddenField('Оценка', validators=[DataRequired()])

  def validate_rating(self, field):
      try:
          val = int(field.data)
          if val < 1 or val > 5:
              raise ValidationError('Оценка должна быть от 1 до 5.')
      except (TypeError, ValueError):
          raise ValidationError('Некорректная оценка.')
  ```

#### BUG-21: Duplicate time-slots endpoints
- **Files**: `app/routes/patient.py:287-309`, `app/routes/api.py:59-121`
- **Problem**: Two endpoints serve time slots: `/patient/api/time-slots` and `/api/time-slots`. They use different implementations. The patient endpoint uses `_generate_time_slots()`, the API endpoint has its own logic. If one is updated, the other may diverge.
- **Fix**: Remove the duplicate in `patient.py` and update the template (`book_appointment.html`) to call `/api/time-slots` instead. Or keep patient endpoint and have it delegate to the shared function. Simplest: keep both but have api.py import and use `_generate_time_slots` from patient.py.

#### BUG-22: Hard-coded URLs in landing.html
- **File**: `app/templates/landing.html` — multiple lines
- **Problem**: Uses `href="/login"` and `href="/register"` instead of `{{ url_for('auth.login') }}` and `{{ url_for('auth.register') }}`.
- **Fix**: Replace all hard-coded auth URLs:
  ```html
  <a href="{{ url_for('auth.login') }}">Войти</a>
  <a href="{{ url_for('auth.register') }}">Регистрация</a>
  ```

#### BUG-23: Hardcoded demo passwords printed to stdout
- **File**: `run.py:88-92`
- **Problem**: `print('  Superadmin: admin@mediplatform.kz / admin123')` — passwords visible in logs.
- **Fix**: Use `app.logger.info()` instead of `print()`, and mask passwords or only show them in debug mode:
  ```python
  if app.debug:
      app.logger.info('Demo accounts created. See .env-example for credentials.')
  ```

#### BUG-24: Missing SESSION_COOKIE_SECURE for production
- **File**: `config.py:17-18`
- **Problem**: No `SESSION_COOKIE_SECURE = True` — cookies sent over HTTP. Also missing `REMEMBER_COOKIE_SECURE` and `REMEMBER_COOKIE_HTTPONLY`.
- **Fix**: Add to Config class (controlled by env):
  ```python
  SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
  REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
  REMEMBER_COOKIE_HTTPONLY = True
  ```

---

### TEST COVERAGE GAPS (fix alongside related bugs)

#### Missing test files / test classes needed:

1. **`tests/test_videocall.py`** (NEW FILE) — test all videocall routes:
   - `test_room_access_authorized` — doctor/patient can access their room
   - `test_room_access_unauthorized` — other user gets 403
   - `test_start_videocall_creates_record` — POST /videocall/start creates VideoCall
   - `test_end_videocall_updates_status` — POST /videocall/end sets status=ended
   - `test_transcribe_saves_text` — POST /videocall/transcribe saves transcription
   - `test_transcribe_missing_text_returns_400`
   - `test_socketio_auth_required` (if SocketIO test client available)

2. **`tests/test_admin.py`** — add missing tests:
   - `test_edit_clinic` — GET/POST /admin/clinics/<id>/edit
   - `test_toggle_user` — POST /admin/users/<id>/toggle
   - `test_delete_user` — POST /admin/users/<id>/delete
   - `test_cannot_delete_superadmin`
   - `test_admin_profile` — GET/POST /admin/profile
   - `test_admin_notifications` — GET /admin/notifications

3. **`tests/test_clinic.py`** — add missing tests:
   - `test_edit_doctor` — GET/POST /clinic/doctors/<id>/edit
   - `test_delete_doctor` — POST /clinic/doctors/<id>/delete (soft delete)
   - `test_patients_list` — GET /clinic/patients

4. **`tests/test_doctor.py`** — add missing tests:
   - `test_patient_detail` — GET /doctor/patients/<id>
   - `test_patient_detail_no_appointment_returns_403`
   - `test_reviews_page` — GET /doctor/reviews

5. **`tests/test_patient.py`** — add missing tests:
   - `test_medical_records_page` — GET /patient/medical-records
   - `test_prescriptions_page` — GET /patient/prescriptions
   - `test_cannot_book_past_time_slot`
   - `test_cannot_double_book_same_slot`
   - `test_weekend_slots_unavailable`

6. **Fix false-positive assertions**:
   - `tests/test_patient.py:25`: Change `assert b'Doctor' in resp.data or resp.status_code == 200` to just `assert b'Doctor' in resp.data`
   - `tests/test_patient.py:39-42`: Add content assertion, not just status code

---

### EXECUTION ORDER

When fixing bugs, follow this sequence:

1. **Models first** (BUG-10, BUG-13, BUG-14, BUG-15) — add indexes, constraints, cascades
2. **Config** (BUG-04, BUG-24) — fix SECRET_KEY and session security
3. **Critical routes** (BUG-01, BUG-02, BUG-03) — WebSocket auth, missing API endpoints, race condition
4. **Route fixes** (BUG-05 through BUG-09, BUG-11) — CSRF, timezone, file validation, clinic isolation, status transitions
5. **Forms** (BUG-18, BUG-19, BUG-20) — password requirements, time format, rating validation
6. **Frontend** (BUG-22) — url_for in templates
7. **Code quality** (BUG-12, BUG-16, BUG-17, BUG-21, BUG-23) — warnings, prompt injection, null checks, dedup
8. **Tests last** — add all missing tests, fix false positives, aim for 70%+ coverage

After EACH group, run: `python -m pytest tests/ -v` and verify 0 failures.
