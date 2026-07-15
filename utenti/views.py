# =============================================================================
# APP "utenti" — VISTE: REGISTRAZIONE, PROFILO/DASHBOARD, ELIMINAZIONE, PASSWORD
# =============================================================================
from django.urls import reverse_lazy
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import DetailView, CreateView, DeleteView
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.utils import timezone

from .form import RegistrazioneForm
from escursione.models import Escursione, Prenotazione
from core.constants import GRUPPO_GUIDE, GRUPPO_ESCURSIONISTI


class RegistrazioneUtenteView(CreateView):
    """
    Gestisce la creazione di un nuovo account sul portale WayPoint,
    utilizzando RegistrazioneForm per l'assegnazione automatica del gruppo
    (ruolo) scelto dall'utente in fase di iscrizione.
    """
    form_class = RegistrazioneForm
    template_name = 'utenti/registrazione.html'
    success_url = reverse_lazy('login')


class ProfiloUtenteView(LoginRequiredMixin, DetailView):
    """
    Dashboard personalizzata dell'utente autenticato: contenuto diverso a
    seconda del ruolo (Guida vs Escursionista vs Amministratore), come
    richiesto dalla traccia ("gestire il proprio profilo utente",
    "visualizzare lo storico delle attività svolte").

    TEORIA — IDOR (Insecure Direct Object Reference) e get_object():
    una DetailView "standard" recupererebbe l'oggetto da mostrare a partire
    da un parametro nell'URL (tipicamente <int:pk>). Qui invece get_object()
    viene sovrascritto per restituire SEMPRE e SOLO request.user,
    indipendentemente da qualunque parametro presente nell'URL: questo rende
    impossibile per un utente tentare di visualizzare il profilo di un altro
    (es. cambiando un id nell'indirizzo), perché l'URL di questa vista non
    contiene affatto un id — l'identità viene sempre dedotta dalla sessione
    autenticata, mai da input controllabile dal client.
    """
    model = User
    template_name = 'utenti/profilo.html'
    context_object_name = 'user_profile'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()

        context['is_admin'] = user.is_superuser
        context['is_guida'] = user.groups.filter(name=GRUPPO_GUIDE).exists()
        context['is_escursionista'] = user.groups.filter(name=GRUPPO_ESCURSIONISTI).exists()

        # ---------------------------------------------------------------
        # DASHBOARD DELLA GUIDA
        # ---------------------------------------------------------------
        if context['is_guida']:
            escursioni_guida = Escursione.objects.filter(guida=user).order_by('-id')
            context['escursioni_create_count'] = escursioni_guida.count()
            context['storico_escursioni'] = escursioni_guida
        else:
            context['escursioni_create_count'] = 0

        # ---------------------------------------------------------------
        # DASHBOARD DELL'ESCURSIONISTA + SISTEMA DI RACCOMANDAZIONE
        # ---------------------------------------------------------------
        # Funzionalità facoltativa della traccia: "Implementazione di un
        # sistema di suggerimenti nella dashboard utente che proponga nuove
        # escursioni basandosi su livello di esperienza e similarità con
        # escursioni già prenotate."
        if context['is_escursionista']:
            prenotazioni_utente = Prenotazione.objects.filter(
                escursionista=user
            ).select_related('uscita', 'uscita__escursione')
            context['prossime_escursioni_count'] = prenotazioni_utente.count()

            # Separiamo le iscrizioni in base alla data dell'uscita:
            #  - FUTURE: esperienze ancora da vivere, sulle quali ha senso il
            #    tasto "Disdici" (soggetto poi al termine delle 24h lato view);
            #  - PASSATE: lo STORICO delle attività già svolte, che NON si possono
            #    più disdire e che vanno tenute in una sezione a parte per non far
            #    "esplodere" la pagina se l'utente ha molte partecipazioni.
            adesso = timezone.now()
            context['prenotazioni_future'] = prenotazioni_utente.filter(
                uscita__data_ritrovo__gte=adesso
            ).order_by('uscita__data_ritrovo')      # la più imminente per prima
            context['prenotazioni_passate'] = prenotazioni_utente.filter(
                uscita__data_ritrovo__lt=adesso
            ).order_by('-uscita__data_ritrovo')     # la più recente per prima

            raccomandazioni_esperienza = []
            raccomandazioni_simili = []

            # ID di tutte le escursioni già prenotate dall'utente: servono
            # per escluderle dai suggerimenti (non ha senso raccomandare
            # qualcosa che l'utente ha già scelto).
            mie_escursioni_ids = prenotazioni_utente.values_list('uscita__escursione__id', flat=True)

            if mie_escursioni_ids:
                # -----------------------------------------------------
                # STRATEGIA 1 — Content-based sul "livello di esperienza"
                # -----------------------------------------------------
                # TEORIA — questa è una raccomandazione "content-based":
                # si deduce una PREFERENZA IMPLICITA dell'utente (la
                # difficoltà più frequente tra le sue prenotazioni passate,
                # calcolata con un GROUP BY: values() raggruppa, annotate
                # (Count) conta le occorrenze per gruppo, order_by ordina per
                # frequenza decrescente) e si suggeriscono altre escursioni
                # con le STESSE caratteristiche (stessa difficoltà).
                difficolta_preferita = prenotazioni_utente.values('uscita__escursione__difficolta') \
                    .annotate(conteggio=Count('id')) \
                    .order_by('-conteggio') \
                    .first()

                if difficolta_preferita:
                    codice_difficolta = difficolta_preferita['uscita__escursione__difficolta']
                    raccomandazioni_esperienza = Escursione.objects.filter(
                        approvata=True,
                        difficolta=codice_difficolta
                    ).exclude(id__in=mie_escursioni_ids).distinct()[:3]

                # -----------------------------------------------------
                # STRATEGIA 2 — Collaborative filtering semplificato
                # -----------------------------------------------------
                # TEORIA — a differenza della strategia 1 (basata sulle
                # CARATTERISTICHE dei contenuti), il collaborative filtering
                # si basa sul COMPORTAMENTO DI ALTRI UTENTI simili: "chi ha
                # fatto le tue stesse escursioni, cos'altro ha fatto?" — è
                # l'esatta traduzione del testo di traccia "Chi ha
                # partecipato a questa uscita ha apprezzato anche...".
                # Passo A: si individuano gli altri utenti che hanno
                # prenotato ALMENO UNA delle stesse escursioni dell'utente
                # corrente (esclude se stesso).
                altri_utenti_simili_ids = Prenotazione.objects.filter(
                    uscita__escursione__id__in=mie_escursioni_ids
                ).exclude(escursionista=user).values_list('escursionista__id', flat=True)

                # Passo B: tra le escursioni frequentate da questi "utenti
                # simili" (diverse dalle proprie), si contano quante volte
                # ciascuna ricorre (annotate(Count)) e si propongono le più
                # gettonate (order_by('-volte_scelta')).
                if altri_utenti_simili_ids:
                    raccomandazioni_simili = Escursione.objects.filter(
                        uscite_programmate__prenotazioni__escursionista__id__in=altri_utenti_simili_ids,
                        approvata=True
                    ).exclude(id__in=mie_escursioni_ids) \
                        .annotate(volte_scelta=Count('id')) \
                        .order_by('-volte_scelta').distinct()[:3]
            else:
                # TEORIA — "cold-start problem": un sistema di raccomandazione
                # basato sullo storico non ha alcun dato da cui partire per un
                # utente completamente nuovo (nessuna prenotazione pregressa).
                # È un limite intrinseco di ogni approccio content-based o
                # collaborative puro. Il fallback qui proposto (le prime 3
                # escursioni approvate del catalogo) è la strategia più
                # semplice per evitare una dashboard vuota.
                raccomandazioni_esperienza = Escursione.objects.filter(approvata=True)[:3]

            context['raccomandazioni_esperienza'] = raccomandazioni_esperienza
            context['raccomandazioni_simili'] = raccomandazioni_simili
        else:
            context['prossime_escursioni_count'] = 0

        return context


class EliminaUtenteView(LoginRequiredMixin, DeleteView):
    """
    Rimozione definitiva e irreversibile dell'account dell'utente autenticato.
    Come in ProfiloUtenteView, get_object() ignora qualunque parametro
    dell'URL e restituisce sempre request.user: nessun utente può eliminare
    l'account di un altro semplicemente indovinando/modificando un id.
    """
    model = User
    template_name = 'utenti/elimina_conferma.html'
    success_url = reverse_lazy('core:home')

    def get_object(self, queryset=None):
        user = self.request.user

        # Vincolo di sicurezza applicativo: un superuser non può
        # autoeliminarsi da questa interfaccia (evita che un amministratore
        # perda accidentalmente l'accesso amministrativo al sistema; la
        # rimozione di un account amministratore, se davvero necessaria, va
        # fatta da un altro amministratore tramite il pannello Django Admin).
        if user.is_superuser:
            raise PermissionDenied(
                "Gli amministratori di sistema non possono eliminare il proprio account da questa interfaccia."
            )
        return user


class CambiaPasswordView(LoginRequiredMixin, SuccessMessageMixin, PasswordChangeView):
    """
    Cambio password dell'utente autenticato. Riusa PasswordChangeView nativo
    di Django, che applica automaticamente tutte le regole di robustezza
    configurate in AUTH_PASSWORD_VALIDATORS (waypoint_project/settings.py) e
    richiede la password attuale prima di accettarne una nuova.
    """
    template_name = 'utenti/cambia_password.html'
    success_url = reverse_lazy('profilo')
    success_message = "La tua password è stata modificata con successo."
