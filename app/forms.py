import re
from datetime import date

from flask_wtf import FlaskForm
from werkzeug.datastructures import FileStorage
from wtforms import (StringField, PasswordField, TextAreaField, SelectField,
                     DateField, FloatField, IntegerField, BooleanField,
                     TimeField, HiddenField)
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, NumberRange, ValidationError
from flask_wtf.file import FileField, FileAllowed


def _uploaded_extension(field_data):
    """Return lowercase extension of an uploaded file, or '' if no file was sent.

    Works around a quirk in some Flask-WTF/Werkzeug versions where an empty
    FileField still produces a FileStorage object — meaning FileAllowed()
    raises 'file type not allowed' on edit-forms where the user kept the
    existing file. Callers should treat '' as "nothing was uploaded".
    """
    if not isinstance(field_data, FileStorage):
        return ''
    filename = field_data.filename or ''
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])


class PatientRegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=8, message='Пароль должен содержать минимум 8 символов.')])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired(), EqualTo('password')])
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    birth_date = DateField('Дата рождения', validators=[Optional()])
    gender = SelectField('Пол', choices=[('', 'Выберите'), ('male', 'Мужской'), ('female', 'Женский')], validators=[Optional()])

    def validate_password(self, field):
        if not any(ch.isdigit() for ch in field.data):
            raise ValidationError('Пароль должен содержать хотя бы одну цифру.')

    def validate_phone(self, field):
        if field.data:
            phone = field.data.strip()
            if phone and not phone.startswith('+7'):
                raise ValidationError('Телефон должен начинаться с +7.')
            if phone and (len(phone) < 11 or len(phone) > 16):
                raise ValidationError('Некорректная длина номера телефона.')

    def validate_birth_date(self, field):
        if field.data:
            today = date.today()
            if field.data > today:
                raise ValidationError('Дата рождения не может быть в будущем.')
            # Check at least 1 year old
            one_year_ago = today.replace(year=today.year - 1)
            if field.data > one_year_ago:
                raise ValidationError('Пациент должен быть старше 1 года.')


class DoctorForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[Optional(), Length(min=8, message='Пароль должен содержать минимум 8 символов.')])
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    specialization = StringField('Специализация', validators=[DataRequired(), Length(max=128)])
    experience_years = IntegerField('Опыт (лет)', validators=[Optional(), NumberRange(min=0, max=70)])
    bio = TextAreaField('О враче', validators=[Optional()])
    consultation_price = FloatField('Стоимость консультации', validators=[Optional(), NumberRange(min=0)])
    avatar = FileField('Фото')

    def validate_password(self, field):
        if field.data and not any(ch.isdigit() for ch in field.data):
            raise ValidationError('Пароль должен содержать хотя бы одну цифру.')

    def validate_avatar(self, field):
        ext = _uploaded_extension(field.data)
        if ext and ext not in ('jpg', 'jpeg', 'png'):
            raise ValidationError('Допустимы только изображения (jpg, png).')


class ClinicForm(FlaskForm):
    name = StringField('Название клиники', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Описание', validators=[Optional()])
    address = StringField('Адрес', validators=[Optional(), Length(max=300)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Email()])
    website = StringField('Вебсайт', validators=[Optional(), Length(max=200)])
    primary_color = StringField('Основной цвет', validators=[Optional()])
    secondary_color = StringField('Дополнительный цвет', validators=[Optional()])
    working_hours_start = StringField('Начало работы', validators=[Optional()])
    working_hours_end = StringField('Конец работы', validators=[Optional()])

    def _validate_time_format(self, field):
        if field.data:
            # Accept H:MM, HH:MM, or HH:MM:SS from browser type="time" input
            val = field.data.strip()
            m = re.match(r'^(\d{1,2}):(\d{2})(?::\d{2})?$', val)
            if not m:
                raise ValidationError('Формат времени: HH:MM')
            h, mn = int(m.group(1)), int(m.group(2))
            if h > 23 or mn > 59:
                raise ValidationError('Некорректное время.')
            # Normalize to HH:MM
            field.data = f'{h:02d}:{mn:02d}'

    def validate_working_hours_start(self, field):
        self._validate_time_format(field)

    def validate_working_hours_end(self, field):
        self._validate_time_format(field)
    logo = FileField('Логотип')

    def validate_logo(self, field):
        ext = _uploaded_extension(field.data)
        if ext and ext not in ('jpg', 'jpeg', 'png', 'svg'):
            raise ValidationError('Допустимы только изображения (jpg, png, svg).')

    # Admin user for clinic
    admin_email = StringField('Email администратора', validators=[Optional(), Email()])
    admin_password = PasswordField('Пароль администратора', validators=[Optional(), Length(min=6)])
    admin_first_name = StringField('Имя администратора', validators=[Optional(), Length(max=64)])
    admin_last_name = StringField('Фамилия администратора', validators=[Optional(), Length(max=64)])


class AppointmentForm(FlaskForm):
    doctor_id = SelectField('Врач', coerce=int, validators=[DataRequired()])
    scheduled_date = DateField('Дата', validators=[DataRequired()])
    scheduled_time = SelectField('Время', validators=[DataRequired()])
    symptoms = TextAreaField('Опишите симптомы', validators=[Optional()])


class PrescriptionForm(FlaskForm):
    diagnosis = TextAreaField('Диагноз', validators=[DataRequired()])
    medications = TextAreaField('Назначения', validators=[Optional()])
    recommendations = TextAreaField('Рекомендации', validators=[Optional()])


class MedicalRecordForm(FlaskForm):
    record_type = SelectField('Тип записи', choices=[
        ('examination', 'Осмотр'),
        ('lab_result', 'Результат анализов'),
        ('imaging', 'Снимки'),
        ('note', 'Заметка')
    ], validators=[DataRequired()])
    title = StringField('Заголовок', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Содержание', validators=[Optional()])
    file = FileField('Файл')

    def validate_file(self, field):
        ext = _uploaded_extension(field.data)
        if ext and ext not in ('jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx'):
            raise ValidationError('Допустимые форматы: jpg, png, pdf, doc, docx.')


class ProfileForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    avatar = FileField('Фото профиля')
    birth_date = DateField('Дата рождения', validators=[Optional()])
    gender = SelectField('Пол', choices=[('', 'Выберите'), ('male', 'Мужской'), ('female', 'Женский')], validators=[Optional()])
    address = TextAreaField('Адрес', validators=[Optional()])

    def validate_avatar(self, field):
        ext = _uploaded_extension(field.data)
        if ext and ext not in ('jpg', 'jpeg', 'png'):
            raise ValidationError('Допустимы только изображения (jpg, png).')


class ReviewForm(FlaskForm):
    rating = HiddenField('Оценка', validators=[DataRequired()])
    comment = TextAreaField('Комментарий', validators=[Optional()])

    def validate_rating(self, field):
        try:
            val = int(field.data)
            if val < 1 or val > 5:
                raise ValidationError('Оценка должна быть от 1 до 5.')
        except (TypeError, ValueError):
            raise ValidationError('Некорректная оценка.')
