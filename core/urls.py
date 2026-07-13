# =============================================================================
# ROUTING DELL'APP "core"
# =============================================================================
# TEORIA — namespacing delle URL: app_name definisce un "namespace" per questo
# set di rotte. Nei template si potrà quindi scrivere {% url 'core:home' %}
# invece del semplice {% url 'home' %}: questo evita collisioni di nomi se in
# futuro un'altra app definisse una view chiamata anch'essa "home", e rende
# esplicita da quale app proviene ogni rotta quando il progetto cresce.
# =============================================================================
from django.urls import path
from .views import home

app_name = 'core'

urlpatterns = [
    # Stringa vuota '' perché è la radice del sito (es. http://localhost:8000/).
    # Il file waypoint_project/urls.py include questo modulo con
    # path('', include('core.urls')), quindi il prefisso finale resta vuoto.
    path('', home, name='home'),
]
