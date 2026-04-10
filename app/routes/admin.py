import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Clinic, Appointment, VideoCall, ClinicSpecialization, Notification
from app.forms import ClinicForm, ProfileForm

admin = Blueprint('admin', __name__, url_prefix='/admin')


def superadmin_required(f):
    """Decorator that checks if the current user is a superadmin."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'superadmin':
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def save_logo(file):
    """Save an uploaded logo file and return the stored filename with 'clinics/' prefix."""
    filename = secure_filename(file.filename)
    # Add timestamp to avoid collisions
    name, ext = os.path.splitext(filename)
    filename = f"{name}_{int(datetime.now(timezone.utc).replace(tzinfo=None).timestamp())}{ext}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'clinics')
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return filename


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin.route('/')
@login_required
@superadmin_required
def dashboard():
    total_clinics = Clinic.query.count()
    total_doctors = User.query.filter_by(role='doctor').count()
    total_patients = User.query.filter_by(role='patient').count()
    total_appointments = Appointment.query.count()

    recent_clinics = Clinic.query.order_by(Clinic.created_at.desc()).limit(5).all()
    recent_appointments = (
        Appointment.query
        .order_by(Appointment.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'admin/dashboard.html',
        total_clinics=total_clinics,
        total_doctors=total_doctors,
        total_patients=total_patients,
        total_appointments=total_appointments,
        recent_clinics=recent_clinics,
        recent_appointments=recent_appointments,
    )


# ---------------------------------------------------------------------------
# Clinics – list
# ---------------------------------------------------------------------------
@admin.route('/clinics')
@login_required
@superadmin_required
def clinics():
    page = request.args.get('page', 1, type=int)
    query = Clinic.query.order_by(Clinic.created_at.desc())

    search = request.args.get('search', '', type=str).strip()
    if search:
        safe_search = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(Clinic.name.ilike(f'%{safe_search}%'))

    clinics = query.paginate(page=page, per_page=20, error_out=False)
    return render_template(
        'admin/clinics.html',
        clinics=clinics,
        search=search,
    )


# ---------------------------------------------------------------------------
# Clinics – create
# ---------------------------------------------------------------------------
@admin.route('/clinics/create', methods=['GET', 'POST'])
@login_required
@superadmin_required
def create_clinic():
    form = ClinicForm()

    if form.validate_on_submit():
        # --- Validate admin fields for new clinic ---
        if not form.admin_email.data or not form.admin_password.data:
            flash('Укажите email и пароль администратора клиники.', 'danger')
            return render_template('admin/clinic_form.html', form=form, title='Создание клиники')

        if User.query.filter_by(email=form.admin_email.data).first():
            flash('Пользователь с таким email уже существует.', 'danger')
            return render_template('admin/clinic_form.html', form=form, title='Создание клиники')

        # --- Create clinic ---
        clinic = Clinic(
            name=form.name.data,
            description=form.description.data,
            address=form.address.data,
            phone=form.phone.data,
            email=form.email.data,
            website=form.website.data,
            primary_color=form.primary_color.data or '#0d6efd',
            secondary_color=form.secondary_color.data or '#6c757d',
            working_hours_start=form.working_hours_start.data or '09:00',
            working_hours_end=form.working_hours_end.data or '18:00',
        )

        # Handle logo upload
        if form.logo.data and form.logo.data.filename:
            clinic.logo = save_logo(form.logo.data)

        db.session.add(clinic)
        db.session.flush()  # get clinic.id before creating admin user

        # --- Create clinic_admin user ---
        clinic_admin = User(
            email=form.admin_email.data,
            first_name=form.admin_first_name.data or 'Admin',
            last_name=form.admin_last_name.data or clinic.name,
            role='clinic_admin',
            clinic_id=clinic.id,
            is_active=True,
        )
        clinic_admin.set_password(form.admin_password.data)
        db.session.add(clinic_admin)

        db.session.commit()
        flash(f'Клиника "{clinic.name}" успешно создана.', 'success')
        return redirect(url_for('admin.clinics'))

    return render_template('admin/clinic_form.html', form=form, title='Создание клиники')


# ---------------------------------------------------------------------------
# Clinics – edit
# ---------------------------------------------------------------------------
@admin.route('/clinics/<int:clinic_id>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_clinic(clinic_id):
    clinic = db.session.get(Clinic, clinic_id) or abort(404)
    form = ClinicForm(obj=clinic)

    # Remove admin fields — they are only needed when creating a new clinic
    del form.admin_email
    del form.admin_password
    del form.admin_first_name
    del form.admin_last_name

    if form.validate_on_submit():
        clinic.name = form.name.data
        clinic.description = form.description.data
        clinic.address = form.address.data
        clinic.phone = form.phone.data
        clinic.email = form.email.data
        clinic.website = form.website.data
        clinic.primary_color = form.primary_color.data or clinic.primary_color
        clinic.secondary_color = form.secondary_color.data or clinic.secondary_color
        clinic.working_hours_start = form.working_hours_start.data or clinic.working_hours_start
        clinic.working_hours_end = form.working_hours_end.data or clinic.working_hours_end

        if form.logo.data and form.logo.data.filename:
            clinic.logo = save_logo(form.logo.data)

        db.session.commit()
        flash(f'Клиника "{clinic.name}" обновлена.', 'success')
        return redirect(url_for('admin.clinics'))

    return render_template('admin/clinic_form.html', form=form, title='Редактирование клиники', clinic=clinic)


# ---------------------------------------------------------------------------
# Clinics – delete
# ---------------------------------------------------------------------------
@admin.route('/clinics/<int:clinic_id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_clinic(clinic_id):
    clinic = db.session.get(Clinic, clinic_id) or abort(404)
    name = clinic.name
    db.session.delete(clinic)
    db.session.commit()
    flash(f'Клиника "{name}" удалена.', 'warning')
    return redirect(url_for('admin.clinics'))


# ---------------------------------------------------------------------------
# Clinics – activate / deactivate
# ---------------------------------------------------------------------------
@admin.route('/clinics/<int:clinic_id>/toggle', methods=['POST'])
@login_required
@superadmin_required
def toggle_clinic(clinic_id):
    clinic = db.session.get(Clinic, clinic_id) or abort(404)
    clinic.is_active = not clinic.is_active
    db.session.commit()
    status = 'активирована' if clinic.is_active else 'деактивирована'
    flash(f'Клиника "{clinic.name}" {status}.', 'info')
    return redirect(url_for('admin.clinics'))


# ---------------------------------------------------------------------------
# Users – list all platform users
# ---------------------------------------------------------------------------
@admin.route('/users')
@login_required
@superadmin_required
def users():
    page = request.args.get('page', 1, type=int)
    role_filter = request.args.get('role', '', type=str)
    search = request.args.get('search', '', type=str)

    query = User.query.order_by(User.created_at.desc())

    if role_filter:
        query = query.filter_by(role=role_filter)
    if search:
        query = query.filter(
            db.or_(
                User.email.ilike(f'%{search}%'),
                User.first_name.ilike(f'%{search}%'),
                User.last_name.ilike(f'%{search}%'),
            )
        )

    users = query.paginate(page=page, per_page=20, error_out=False)
    return render_template(
        'admin/users.html',
        users=users,
        role_filter=role_filter,
        search=search,
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@admin.route('/analytics')
@login_required
@superadmin_required
def analytics():
    # General counts
    total_clinics = Clinic.query.count()
    active_clinics = Clinic.query.filter_by(is_active=True).count()
    total_doctors = User.query.filter_by(role='doctor').count()
    total_patients = User.query.filter_by(role='patient').count()
    total_appointments = Appointment.query.count()
    total_videocalls = VideoCall.query.count()

    # Appointments by status
    appointments_by_status = (
        db.session.query(Appointment.status, db.func.count(Appointment.id))
        .group_by(Appointment.status)
        .all()
    )
    appointments_by_status = dict(appointments_by_status)

    # Appointments over last 30 days
    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    recent_appointments_count = Appointment.query.filter(
        Appointment.created_at >= thirty_days_ago
    ).count()

    # New users over last 30 days
    new_users_count = User.query.filter(
        User.created_at >= thirty_days_ago
    ).count()

    # Top clinics by appointment count
    top_clinics = (
        db.session.query(Clinic, db.func.count(Appointment.id).label('appointment_count'))
        .join(Appointment, Appointment.clinic_id == Clinic.id)
        .group_by(Clinic.id)
        .order_by(db.func.count(Appointment.id).desc())
        .limit(10)
        .all()
    )

    return render_template(
        'admin/analytics.html',
        total_clinics=total_clinics,
        active_clinics=active_clinics,
        total_doctors=total_doctors,
        total_patients=total_patients,
        total_appointments=total_appointments,
        total_videocalls=total_videocalls,
        appointments_by_status=appointments_by_status,
        recent_appointments_count=recent_appointments_count,
        new_users_count=new_users_count,
        top_clinics=top_clinics,
    )


# ---------------------------------------------------------------------------
# Users – toggle active status
# ---------------------------------------------------------------------------
@admin.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@superadmin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.role == 'superadmin':
        flash('Нельзя изменить статус суперадмина.', 'danger')
        return redirect(url_for('admin.users'))
    user.is_active = not user.is_active
    db.session.commit()
    status = 'активирован' if user.is_active else 'деактивирован'
    flash(f'Пользователь "{user.full_name}" {status}.', 'info')
    return redirect(url_for('admin.users'))


# ---------------------------------------------------------------------------
# Users – delete
# ---------------------------------------------------------------------------
@admin.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.role == 'superadmin':
        flash('Нельзя удалить суперадмина.', 'danger')
        return redirect(url_for('admin.users'))
    name = user.full_name
    db.session.delete(user)
    db.session.commit()
    flash(f'Пользователь "{name}" удален.', 'warning')
    return redirect(url_for('admin.users'))


# ---------------------------------------------------------------------------
# Admin profile
# ---------------------------------------------------------------------------
@admin.route('/profile', methods=['GET', 'POST'])
@login_required
@superadmin_required
def profile():
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.phone = form.phone.data

        if form.avatar.data and form.avatar.data.filename:
            avatar_filename = secure_filename(form.avatar.data.filename)
            name, ext = os.path.splitext(avatar_filename)
            avatar_filename = f"{name}_{int(datetime.now(timezone.utc).replace(tzinfo=None).timestamp())}{ext}"
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'avatars')
            os.makedirs(upload_dir, exist_ok=True)
            form.avatar.data.save(os.path.join(upload_dir, avatar_filename))
            current_user.avatar = avatar_filename

        db.session.commit()
        flash('Профиль обновлен.', 'success')
        return redirect(url_for('admin.profile'))

    return render_template('admin/profile.html', form=form)


# ---------------------------------------------------------------------------
# Admin notifications
# ---------------------------------------------------------------------------
@admin.route('/notifications')
@login_required
@superadmin_required
def notifications():
    page = request.args.get('page', 1, type=int)
    notifs = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )

    # Mark all as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()

    return render_template('admin/notifications.html', notifications=notifs)
