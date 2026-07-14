import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent



SECRET_KEY = 'django-insecure-c$%(x_d8ru^xfw6fzln*z^_kjrob8sd^t#p#k3i0kqqihg^8#t'
DEBUG = True
ALLOWED_HOSTS = []


# =============================================================================
# APPLICAZIONI E MIDDLEWARE
# =============================================================================
# TEORIA — INSTALLED_APPS: elenca ogni app Python che Django deve caricare
# (modelli, migrazioni, template tag, admin). Oltre alle app di sistema
# (admin, auth, contenttypes, sessions, messages, staticfiles) figurano le
# quattro app applicative del progetto: core (homepage/ricerca), escursione
# (dominio principale), utenti (autenticazione/profilo/ruoli), recensioni
# (feedback e moderazione).
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'escursione',
    'utenti',
    'recensioni',
]

# TEORIA — MIDDLEWARE: catena di componenti che processano OGNI richiesta/
# risposta HTTP in ordine (in entrata dall'alto verso il basso, in uscita in
# ordine inverso). Rilevanti per la sicurezza applicativa discussa in questo
# progetto: AuthenticationMiddleware popola request.user su ogni richiesta
# (da cui dipendono @login_required, LoginRequiredMixin, i controlli sui
# Group); CsrfViewMiddleware protegge le richieste POST (prenotazioni,
# cancellazioni, eliminazioni) da Cross-Site Request Forgery, verificando il
# token CSRF incluso nei form.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'waypoint_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'waypoint_project.wsgi.application'


# =============================================================================
# DATABASE
# =============================================================================
# SQLite: database su singolo file, senza necessità di un server dedicato.

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# =============================================================================
# VALIDAZIONE PASSWORD
# =============================================================================
# Applicati automaticamente da UserCreationForm (RegistrazioneForm) e da
# PasswordChangeView (CambiaPasswordView in utenti/views.py): impediscono
# password troppo simili ai dati dell'utente, troppo corte, troppo comuni o
# interamente numeriche.
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internazionalizzazione
LANGUAGE_CODE = 'it-it'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# =============================================================================
# FILE STATICI E MEDIA
# =============================================================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# MEDIA_URL: prefisso URL pubblico con cui il browser richiede i file
# caricati dagli utenti (es. /media/escursione/copertine/foto.jpg).
# MEDIA_ROOT: percorso fisico sul disco dove Django salva effettivamente
# quei file (foto di copertina e gallerie delle escursioni, ImageField in
# escursione/models.py).
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# =============================================================================
# AUTENTICAZIONE
# =============================================================================
# Usati da @login_required, LoginRequiredMixin e dal flusso di login/logout
# nativo di Django (utenti/urls.py): dopo il login l'utente viene
# reindirizzato a 'profilo' (la dashboard, si veda utenti/views.py); se un
# utente anonimo tenta di accedere a una vista protetta viene reindirizzato a
# 'login'.
LOGIN_REDIRECT_URL = 'profilo'
LOGIN_URL = 'login'

# EMAIL_BACKEND "console": in sviluppo le email (notifiche di cancellazione,
# lista d'attesa) non vengono realmente inviate a un server SMTP, ma
# semplicemente stampate nel terminale del server di sviluppo. Permette di
# collaudare e dimostrare che la logica di invio si attiva correttamente
# senza dover configurare credenziali SMTP reali. In produzione andrebbe
# sostituito con un vero backend (SMTP, o un servizio transazionale esterno).
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
