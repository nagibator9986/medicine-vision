from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    cors_env = os.environ.get('CORS_ORIGINS', '').strip()
    allowed_origins = cors_env.split(',') if cors_env else '*'

    # Auto-detect async mode: gevent for production, threading for local dev
    async_mode = os.environ.get('SOCKETIO_ASYNC_MODE', '')
    if not async_mode:
        try:
            import gevent          # noqa: F401
            import geventwebsocket  # noqa: F401
            async_mode = 'gevent'
        except ImportError:
            async_mode = 'threading'

    # manage_session=False makes Flask-SocketIO share the Flask-Login session
    # so current_user works in SocketIO event handlers
    socketio.init_app(
        app,
        cors_allowed_origins=allowed_origins,
        async_mode=async_mode,
        manage_session=False,
    )
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите в систему.'
    login_manager.login_message_category = 'warning'

    # Ensure upload folder exists
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'app/static/uploads'), exist_ok=True)

    from app.routes.auth import auth_bp
    from app.routes.admin import admin as admin_bp
    from app.routes.clinic import clinic as clinic_bp
    from app.routes.doctor import doctor as doctor_bp
    from app.routes.patient import patient_bp
    from app.routes.videocall import videocall_bp
    from app.routes.chatbot import chatbot_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(clinic_bp, url_prefix='/clinic')
    app.register_blueprint(doctor_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(videocall_bp, url_prefix='/videocall')
    app.register_blueprint(chatbot_bp, url_prefix='/chatbot')
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            from app.routes.auth import ROLE_REDIRECTS
            return redirect(url_for(ROLE_REDIRECTS.get(current_user.role, 'auth.login')))
        return render_template('landing.html')

    @app.route('/landing')
    def landing():
        return render_template('landing.html')

    @app.context_processor
    def inject_now():
        from datetime import datetime, timezone
        return {'now': datetime.now(timezone.utc).replace(tzinfo=None)}

    return app
