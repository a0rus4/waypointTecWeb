# =============================================================================
# ROUTING RADICE DEL PROGETTO
# =============================================================================
# TEORIA — routing gerarchico con include(): ogni app definisce il proprio
# file urls.py con le rotte di propria competenza; questo file "radice" le
# aggrega sotto un prefisso (es. tutte le rotte di escursione/urls.py
# risponderanno sotto /escursioni/...). Questo disaccoppia completamente il
# routing interno di un'app dal resto del progetto: un'app può essere
# spostata sotto un prefisso diverso, o rimossa, senza toccare le altre.
# =============================================================================
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('utenti/', include('utenti.urls')),
    path('escursioni/', include('escursione.urls')),
    path('recensioni/', include('recensioni.urls')),
]

# TEORIA — servire i file media in sviluppo: Django, di default, NON serve
# alcun file statico/media tramite il proprio server di sviluppo se non
# esplicitamente configurato. static() aggiunge una rotta che mappa
# MEDIA_URL (es. /media/...) alla cartella fisica MEDIA_ROOT sul disco, ma
# SOLO quando DEBUG=True: in produzione questo compito spetta a un web server
# dedicato (Nginx, Apache, o un servizio di storage/CDN), mai al server di
# sviluppo di Django, per motivi di performance e sicurezza.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
