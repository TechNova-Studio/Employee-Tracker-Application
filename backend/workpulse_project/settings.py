from pathlib import Path
from decouple import AutoConfig, Csv
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
config = AutoConfig(search_path=str(ROOT_DIR))

SECRET_KEY = config('SECRET_KEY', default='unsafe-staging-key-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'workpulse_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'workpulse_project.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=(
            f"postgres://{config('DB_USER', default='postgres')}:"
            f"{config('DB_PASSWORD', default='Password@91')}@"
            f"{config('DB_HOST', default='localhost')}:"
            f"{config('DB_PORT', default='5432')}/"
            f"{config('DB_NAME', default='bold_workpulse')}"
        ),
        conn_max_age=600,
    )
}

# REDIS_URL = config('REDIS_URL', default='')

# if REDIS_URL:
#     CACHES = {
#         'default': {
#             'BACKEND': 'django.core.cache.backends.redis.RedisCache',
#             'LOCATION': REDIS_URL,
#         }
#     }
# else:
#     CACHES = {
#         'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
#     }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = ROOT_DIR / 'local-media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:5174,http://localhost:5174', cast=Csv())
CORS_ALLOW_CREDENTIALS = True

SCREENSHOT_STORAGE_MODE = config('SCREENSHOT_STORAGE_MODE', default='local')
LOCAL_SCREENSHOT_DIR = config('LOCAL_SCREENSHOT_DIR', default='local-media/screenshots')
BACKEND_BASE_URL = config('BACKEND_BASE_URL', default='http://localhost:8000')
DESKTOP_AGENT_DOWNLOAD_URL = config('DESKTOP_AGENT_DOWNLOAD_URL', default='')
DEFAULT_AGENT_LATEST_VERSION = config('DEFAULT_AGENT_LATEST_VERSION', default='1.0.0')
DEFAULT_AGENT_MINIMUM_SUPPORTED_VERSION = config('DEFAULT_AGENT_MINIMUM_SUPPORTED_VERSION', default='1.0.0')
DEFAULT_SCREENSHOT_INTERVAL_SECONDS = config('DEFAULT_SCREENSHOT_INTERVAL_SECONDS', default=300, cast=int)
DEFAULT_IDLE_THRESHOLD_SECONDS = config('DEFAULT_IDLE_THRESHOLD_SECONDS', default=300, cast=int)
AI_PROVIDER = config('AI_PROVIDER', default='mock')
AI_API_KEY = config('AI_API_KEY', default='')
TRIAL_START_MODE = config('TRIAL_START_MODE', default='first_admin_login')


# CRM login providers are backend configuration; see docs/CRM_LOGIN.md.
import json as _json
CRM_SSO_PROVIDERS = _json.loads(config('CRM_SSO_PROVIDERS', default='{}'))
CRM_SSO_ALLOW_LOOPBACK_HTTP = config('CRM_SSO_ALLOW_LOOPBACK_HTTP', default=False, cast=bool)
