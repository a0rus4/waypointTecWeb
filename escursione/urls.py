# =============================================================================
# ROUTING DELL'APP "escursione"
# =============================================================================
# Rotte pubbliche (dettaglio) e rotte protette (prenotazione, creazione,
# cancellazione, eliminazione): la protezione vera e propria (login, ruolo,
# ownership) è applicata nelle singole view, non nel routing — questo file si
# limita a mappare URL -> vista.
# =============================================================================
from django.urls import path
from . import views

urlpatterns = [
    # --- Rotte pubbliche ---
    path('dettaglio/<int:pk>/', views.EscursioneDetailView.as_view(), name='dettaglio_escursione'),

    # --- Prenotazione (richiede login + ruolo Escursionista, verificato in views.py) ---
    path('prenota/<int:uscita_id>/', views.prenota_uscita, name='prenota_uscita'),

    # --- Gestione lato Guida (CRUD su itinerari e date) ---
    path('crea/', views.EscursioneCreateView.as_view(), name='crea_escursione'),
    path('<int:escursione_id>/aggiungi-data/', views.UscitaCreateView.as_view(), name='aggiungi_data_uscita'),
    path('prenotazione/<int:prenotazione_id>/cancella/', views.cancella_prenotazione, name='cancella_prenotazione'),
    path('elimina-itinerario/<int:escursione_id>/', views.elimina_escursione, name='elimina_escursione'),
    path('elimina-data/<int:uscita_id>/', views.elimina_uscita, name='elimina_uscita'),
]
