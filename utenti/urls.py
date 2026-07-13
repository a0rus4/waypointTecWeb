# =============================================================================
# ROUTING DELL'APP "utenti"
# =============================================================================

from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

urlpatterns = [
    # --- Registrazione e gestione profilo ---
    path('registrazione/', RegistrazioneUtenteView.as_view(), name='registrazione'),
    path('profilo/', ProfiloUtenteView.as_view(), name='profilo'),
    path('elimina-account/', EliminaUtenteView.as_view(), name='elimina_utente'),

    # --- Autenticazione ---
    path('login/', auth_views.LoginView.as_view(template_name='utenti/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='utenti/logout.html'), name='logout'),
    path('cambia-password/', CambiaPasswordView.as_view(), name='cambio_password'),
]
