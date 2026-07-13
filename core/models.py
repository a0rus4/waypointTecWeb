from django.db import models

# L'app "core" non definisce modelli propri: il suo unico compito è esporre la
# homepage pubblica e il motore di ricerca (vedi core/views.py), che opera sui
# modelli definiti nell'app "escursione" (Escursione, Uscita).

