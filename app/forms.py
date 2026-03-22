from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, TextAreaField, SelectField,
                     DateField, FloatField, IntegerField, BooleanField,
                     TimeField, HiddenField)
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, NumberRange
from flask_wtf.file import FileField, FileAllowed


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])


class PatientRegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired(), EqualTo('password')])
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    birth_date = DateField('Дата рождения', validators=[Optional()])
    gender = SelectField('Пол', choices=[('', 'Выберите'), ('male', 'Мужской'), ('female', 'Женский')], validators=[Optional()])


class DoctorForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[Optional(), Length(min=6)])
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    specialization = StringField('Специализация', validators=[DataRequired(), Length(max=128)])
    experience_years = IntegerField('Опыт (лет)', validators=[Optional(), NumberRange(min=0, max=70)])
    bio = TextAreaField('О враче', validators=[Optional()])
    consultation_price = FloatField('Стоимость консультации', validators=[Optional(), NumberRange(min=0)])
    avatar = FileField('Фото', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg'], 'Только изображения')])


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
    logo = FileField('Логотип', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg', 'svg'], 'Только изображения')])

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
    file = FileField('Файл', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg', 'pdf', 'doc', 'docx'])])


class ProfileForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    avatar = FileField('Фото профиля', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg'], 'Только изображения')])
    birth_date = DateField('Дата рождения', validators=[Optional()])
    gender = SelectField('Пол', choices=[('', 'Выберите'), ('male', 'Мужской'), ('female', 'Женский')], validators=[Optional()])
    address = TextAreaField('Адрес', validators=[Optional()])


class ReviewForm(FlaskForm):
    rating = HiddenField('Оценка', validators=[DataRequired()])
    comment = TextAreaField('Комментарий', validators=[Optional()])
