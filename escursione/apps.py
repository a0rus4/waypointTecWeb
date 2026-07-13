# Configurazione standard dell'app Django "escursione": AppConfig è la classe
# che Django usa per riconoscere e inizializzare l'app (registrata in
# INSTALLED_APPS, waypoint_project/settings.py). Contiene il cuore del
# dominio: Escursione, Uscita, Prenotazione, FotoGalleria e le relative view.
from django.apps import AppConfig


class EscursioniConfig(AppConfig):
    name = 'escursione'
