# =============================================================================
# APP "escursione" — VISTE: DETTAGLIO, PRENOTAZIONI, GESTIONE LATO GUIDA
# =============================================================================
# Questo file contiene il cuore della logica di business di WayPoint: la
# visualizzazione di un itinerario, l'algoritmo di prenotazione/lista
# d'attesa, la creazione di escursioni e date da parte delle Guide, e le
# operazioni di cancellazione/eliminazione con relative notifiche email.
# =============================================================================

from datetime import timedelta

from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, CreateView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage
from django.db import transaction

from .models import Escursione, Uscita, Prenotazione, FotoGalleria
from .forms import EscursioneForm, UscitaForm
from recensioni.models import Recensione
from core.constants import GRUPPO_GUIDE, GRUPPO_ESCURSIONISTI, ORE_LIMITE_CANCELLAZIONE


def _invia_notifica_di_massa(oggetto, messaggio, destinatari, from_email):
    """
    Funzione di supporto per l'invio di una singola email a più destinatari
    SENZA che questi si vedano a vicenda l'indirizzo altrui.

    TEORIA — To vs Bcc: django.core.mail.send_mail(..., recipient_list=[...])
    inserisce TUTTI gli indirizzi della lista nell'header "To" del messaggio:
    ogni destinatario, aprendo l'email, vedrebbe quindi l'indirizzo di tutti
    gli altri iscritti alla stessa uscita. Per un
    invio "in copia nascosta" occorre costruire un oggetto EmailMessage e
    valorizzare il parametro `bcc` (Blind Carbon Copy): gli indirizzi in bcc
    vengono recapitati normalmente, ma NON compaiono negli header del
    messaggio ricevuto dagli altri destinatari.
    """
    if not destinatari:
        return
    email = EmailMessage(
        subject=oggetto,
        body=messaggio,
        from_email=from_email,
        to=[],
        bcc=destinatari,
    )
    # fail_silently=True: se il server SMTP non è configurato correttamente
    # (in sviluppo si usa il backend "console", si veda settings.py), l'invio
    # fallisce senza interrompere la richiesta HTTP: la logica di dominio
    # (aggiornamento posti, cancellazione) va comunque a buon fine anche se la
    # notifica non può essere recapitata.
    email.send(fail_silently=True)


def _invia_email_singola(oggetto, messaggio, destinatario):
    """
    Invia un'email a UN singolo destinatario (campo "To"), usata per la conferma
    di prenotazione. A differenza di _invia_notifica_di_massa (che usa il Bcc per
    invii a più iscritti), qui il destinatario è uno solo e legittimamente vede
    il proprio indirizzo. fail_silently=True: se l'invio non è configurato (in
    sviluppo si usa il backend "console", si veda settings.py), la prenotazione
    va comunque a buon fine senza sollevare eccezioni.
    """
    if not destinatario:
        return
    EmailMessage(
        subject=oggetto,
        body=messaggio,
        from_email="noreply@waypoint.com",
        to=[destinatario],
    ).send(fail_silently=True)


# =============================================================================
# 1. VISTE PUBBLICHE
# =============================================================================

class EscursioneDetailView(DetailView):
    """
    Scheda di dettaglio di un itinerario: mostra le informazioni tecniche,
    il calendario delle uscite future prenotabili, e — se l'utente è
    autenticato — se ha già una prenotazione attiva e se può lasciare una
    recensione.

    TEORIA — Class-Based View generica (DetailView): Django fornisce viste
    generiche pronte all'uso per pattern ricorrenti (mostrare un singolo
    oggetto, una lista, un form di creazione...). DetailView recupera
    automaticamente l'oggetto tramite la chiave primaria presente nell'URL
    (<int:pk>) e lo espone al template nel contesto (qui rinominato
    "escursione" tramite context_object_name). Estendere get_context_data()
    permette di arricchire il contesto con dati aggiuntivi oltre all'oggetto
    principale, senza dover riscrivere l'intera logica di recupero.
    """
    model = Escursione
    template_name = 'escursione/escursione_detail.html'
    context_object_name = 'escursione'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # IL CALENDARIO: solo le date future, ordinate cronologicamente.
        # self.object.uscite_programmate è la relazione inversa generata da
        # Uscita.escursione (related_name='uscite_programmate').
        context['uscite_future'] = self.object.uscite_programmate.filter(
            data_ritrovo__gte=timezone.now()
        ).order_by('data_ritrovo')

        context['puo_recensire'] = False
        # ha_gia_recensito: distingue, nel template, il motivo per cui il form
        # non è disponibile (già recensita vs mai partecipata).
        context['ha_gia_recensito'] = False

        if self.request.user.is_authenticated:
            # ID delle uscite già prenotate da QUESTO utente per QUESTA
            # escursione: il template li usa per disabilitare il pulsante
            # "Prenota" sulle date già occupate.
            uscite_prenotate = Prenotazione.objects.filter(
                escursionista=self.request.user,
                uscita__escursione=self.object
            ).values_list('uscita_id', flat=True)
            context['uscite_prenotate_utente'] = list(uscite_prenotate)

            # SBLOCCO RECENSIONI: si può recensire solo se (a) non si è già
            # recensita questa escursione (altrimenti violerebbe il vincolo
            # unique_together di Recensione) e (b) si ha almeno una
            # prenotazione CONFERMATA per un'uscita già CONCLUSA. Questo
            # implementa il requisito di traccia "recensioni post-evento":
            # non si può recensire un'escursione a cui non si è partecipato,
            # né prima che si sia effettivamente svolta.
            ha_gia_recensito = Recensione.objects.filter(
                escursione=self.object,
                autore=self.request.user
            ).exists()
            context['ha_gia_recensito'] = ha_gia_recensito

            if not ha_gia_recensito:
                context['puo_recensire'] = Prenotazione.objects.filter(
                    escursionista=self.request.user,
                    uscita__escursione=self.object,
                    uscita__data_ritrovo__lt=timezone.now(),
                    stato='confermata'
                ).exists()
        else:
            context['uscite_prenotate_utente'] = []

        return context


# =============================================================================
# 2. GESTIONE PRENOTAZIONI
# =============================================================================

def is_escursionista(user):
    """Controllo di ruolo: l'utente appartiene al gruppo Escursionisti?"""
    return user.groups.filter(name=GRUPPO_ESCURSIONISTI).exists()


@require_POST
@login_required
def prenota_uscita(request, uscita_id):
    """
    Gestisce la prenotazione di un'uscita: verifica il ruolo dell'utente,
    impedisce doppie prenotazioni, applica l'algoritmo di allocazione posti
    con fallback in lista d'attesa se l'uscita è già piena.

    Requisito di traccia: "Il sistema deve gestire la disponibilità dei posti
    per ogni singola escursione. Nel caso in cui un'escursione sia completa,
    un utente registrato può richiedere di essere inserito in lista d'attesa."

    TEORIA — race condition e transazioni atomiche:
    L'algoritmo "leggi il contatore, decidi in base al valore letto, poi
    scrivi il nuovo valore" (read-modify-write) NON è sicuro se eseguito senza
    protezione quando più richieste HTTP possono arrivare in parallelo sulla
    stessa riga di database (es. due utenti che cliccano "Prenota" nello
    stesso istante sull'ultimo posto disponibile): entrambe le richieste
    potrebbero leggere "1 posto libero" PRIMA che l'altra abbia scritto il
    proprio incremento, risultando in un overbooking (due prenotazioni
    "confermate" per un solo posto).

    quando una transazione scrive, nessun'altra transazione può scrivere finché
    questa non si conclude.
    """
    uscita = get_object_or_404(Uscita, id=uscita_id)

    # Controllo di ruolo: solo gli Escursionisti possono prenotare.
    if not request.user.groups.filter(name=GRUPPO_ESCURSIONISTI).exists():
        messages.error(request, "Operazione non consentita: Solo gli utenti con profilo Escursionista possono prenotare le uscite!")
        return redirect('dettaglio_escursione', pk=uscita.escursione.id)

    # Controllo anti-duplicazione applicativo (rinforzato dal vincolo
    # unique_together a livello di database sul modello Prenotazione).
    if Prenotazione.objects.filter(escursionista=request.user, uscita=uscita).exists():
        messages.warning(request, "Possiedi già una prenotazione attiva per questa data.")
        return redirect('dettaglio_escursione', pk=uscita.escursione.id)


    with transaction.atomic():
        uscita_bloccata = Uscita.objects.get(id=uscita.id)

        if uscita_bloccata.posti_occupati < uscita_bloccata.posti_totali:
            stato_prenotazione = 'confermata'
            uscita_bloccata.posti_occupati += 1

            # full_clean() invoca esplicitamente Uscita.clean(): dato che qui
            # stiamo salvando l'istanza direttamente (non tramite un
            # ModelForm), senza questa chiamata l'invariante "posti_occupati
            # non supera posti_totali" definito nel modello non verrebbe mai
            # verificato in questo punto del codice.
            try:
                uscita_bloccata.full_clean()
            except ValidationError:
                messages.error(request, "Impossibile completare la prenotazione: capienza non valida per questa uscita.")
                return redirect('dettaglio_escursione', pk=uscita.escursione.id)

            uscita_bloccata.save()
            messages.success(request, f"Posto confermato con successo per {uscita.escursione.titolo}! Riceverai i dettagli via email.")
        else:
            stato_prenotazione = 'attesa'
            messages.warning(request, f"Posti esauriti. Sei stato inserito nella lista d'attesa di {uscita.escursione.titolo}. Riceverai una mail qualora se ne liberi uno")

        Prenotazione.objects.create(
            escursionista=request.user,
            uscita=uscita_bloccata,
            stato=stato_prenotazione
        )

    # Email di conferma: inviata SOLO dopo che il blocco transaction.atomic() è
    # terminato con successo (commit), così non promettiamo una mail per una
    # prenotazione che un eventuale rollback avrebbe annullato. La inviamo per il
    # posto confermato; per la lista d'attesa la notifica avverrà invece quando
    # un posto si libererà (flusso di cancellazione). In sviluppo, col backend
    # "console" (settings.py), l'email compare nel terminale di runserver.
    if stato_prenotazione == 'confermata' and request.user.email:
        data_fmt = timezone.localtime(uscita.data_ritrovo).strftime('%d/%m/%Y alle %H:%M')
        _invia_email_singola(
            oggetto=f"Prenotazione confermata: {uscita.escursione.titolo}",
            messaggio=(
                f"Ciao {request.user.first_name or request.user.username},\n\n"
                f"la tua prenotazione per \"{uscita.escursione.titolo}\" è confermata.\n\n"
                f"Data e ora di ritrovo: {data_fmt}\n"
                f"Punto di ritrovo: {uscita.escursione.punto_di_ritrovo}\n\n"
                f"Buona avventura!\nIl team di WayPoint"
            ),
            destinatario=request.user.email,
        )

    return redirect('dettaglio_escursione', pk=uscita.escursione.id)


# =============================================================================
# 3. GESTIONE LATO GUIDA (creazione sentieri e date)
# =============================================================================

class EscursioneCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Permette a una Guida di inserire un nuovo itinerario (Escursione) nel
    sistema, incluse le foto di copertina e la galleria aggiuntiva.

    TEORIA — mixin di autorizzazione:
      - LoginRequiredMixin: blocca l'accesso agli utenti anonimi (redirect al
        login, configurato da settings.LOGIN_URL).
      - UserPassesTestMixin: consente di esprimere una condizione di
        autorizzazione arbitraria tramite test_func(); se restituisce False,
        Django risponde con 403 Forbidden. Qui la condizione è "l'utente
        appartiene al gruppo Guide".
    L'ordine dei mixin nella dichiarazione della classe è significativo per la
    Method Resolution Order (MRO) di Python: i mixin vanno sempre PRIMA della
    view generica base (CreateView), in modo che i loro metodi (come
    dispatch()) intercettino la richiesta prima che raggiunga la logica di
    CreateView.
    """
    model = Escursione
    form_class = EscursioneForm
    template_name = 'escursione/crea_escursione.html'

    def test_func(self):
        return self.request.user.groups.filter(name=GRUPPO_GUIDE).exists()

    def form_valid(self, form):
        # Associa automaticamente l'autore: la Guida non sceglie "chi è il
        # proprietario" nel form (sarebbe un rischio di sicurezza, un utente
        # potrebbe impersonare un'altra guida), viene sempre impostata
        # dall'utente autenticato lato server.
        form.instance.guida = self.request.user

        # super().form_valid() salva l'istanza (self.object) e reindirizza;
        # va chiamato PRIMA di creare le FotoGalleria perché hanno bisogno
        # dell'id dell'Escursione appena creata (self.object).
        response = super().form_valid(form)

        # Gestione della galleria multipla: il campo 'foto_galleria' del form
        # non è collegato al modello Escursione (è dichiarato esplicitamente
        # in EscursioneForm, si veda escursione/forms.py) proprio perché
        # rappresenta N oggetti FotoGalleria correlati, non un singolo campo.
        foto_galleria = self.request.FILES.getlist('foto_galleria')
        for foto in foto_galleria:
            FotoGalleria.objects.create(escursione=self.object, immagine=foto)

        messages.success(self.request, "Itinerario inviato per l'approvazione degli amministratori.")
        return response

    def get_success_url(self):
        return reverse('core:home')


class UscitaCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Permette alla Guida di associare una nuova data (Uscita) e la relativa
    capienza a un proprio itinerario già esistente.
    """
    model = Uscita
    form_class = UscitaForm
    template_name = 'escursione/escursione_form.html'

    def test_func(self):
        return self.request.user.groups.filter(name=GRUPPO_GUIDE).exists()

    def form_valid(self, form):
        escursione = get_object_or_404(Escursione, id=self.kwargs['escursione_id'])

        # Controllo di OWNERSHIP: l'id dell'escursione arriva direttamente
        # dall'URL (self.kwargs) e potrebbe quindi essere manipolato da
        # chiunque sia autenticato come Guida. Senza questo controllo, la
        # Guida B potrebbe aggiungere date arbitrarie a un itinerario di
        # proprietà della Guida A semplicemente cambiando l'id nell'indirizzo
        # (vulnerabilità IDOR — Insecure Direct Object Reference). Il
        # controllo esplicito garantisce che solo il proprietario reale possa
        # modificare il proprio calendario.
        if escursione.guida != self.request.user:
            raise PermissionDenied("Non sei autorizzato a pianificare date per questo itinerario.")

        form.instance.escursione = escursione
        messages.success(self.request, "Nuova data programmata con successo nel calendario.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('dettaglio_escursione', kwargs={'pk': self.kwargs['escursione_id']})


# =============================================================================
# 4. GESTIONE CANCELLAZIONE E SCORRIMENTO CODA
# =============================================================================

@require_POST
@login_required
def cancella_prenotazione(request, prenotazione_id):
    """
    Consente all'utente di disdire una propria prenotazione. Libera il posto
    (se era confermata) e notifica via email gli utenti in lista d'attesa,
    SENZA auto-prenotarli: sarà il primo che accede al portale a prenotarsi
    manualmente sul posto liberato (politica "first-come, first-served" sulla
    azione web, non un'assegnazione automatica lato server).

    Requisito di traccia: "Il sistema deve gestire le cancellazioni,
    notificando la disponibilità agli utenti in attesa" e "possibilità di
    cancellazione entro termini stabiliti".


    """
    prenotazione = get_object_or_404(Prenotazione, id=prenotazione_id, escursionista=request.user)
    uscita = prenotazione.uscita
    stato_cancellato = prenotazione.stato

    # Termine di cancellazione: si applica solo alle prenotazioni CONFERMATE
    # (una prenotazione "in lista d'attesa" non occupa un posto reale, quindi
    # non c'è nulla da "liberare in extremis" e la si può ritirare in ogni
    # momento senza penalizzare l'organizzazione).
    if stato_cancellato == 'confermata':
        tempo_rimanente = uscita.data_ritrovo - timezone.now()
        if tempo_rimanente < timedelta(hours=ORE_LIMITE_CANCELLAZIONE):
            messages.error(
                request,
                f"Non è più possibile cancellare questa prenotazione: mancano meno di "
                f"{ORE_LIMITE_CANCELLAZIONE} ore alla partenza. Contatta la guida per informazioni."
            )
            return redirect('profilo')

    with transaction.atomic():
        # 1. Eliminazione del record di prenotazione.
        prenotazione.delete()

        if stato_cancellato == 'confermata':
            # 2. Liberazione del posto (il lock di scrittura a livello di
            #    intero database, applicato da SQLite per ogni transazione,
            #    rende superfluo select_for_update().
            uscita_bloccata = Uscita.objects.get(id=uscita.id)
            uscita_bloccata.posti_occupati -= 1

            try:
                uscita_bloccata.full_clean()
            except ValidationError:
                # Non dovrebbe mai accadere (stiamo decrementando un
                # contatore che sappiamo essere >= 1), ma un controllo
                # esplicito evita di salvare comunque uno stato incoerente.
                messages.error(request, "Si è verificato un errore nell'aggiornamento dei posti disponibili.")
                return redirect('profilo')

            uscita_bloccata.save()
            messages.success(request, "La tua prenotazione è stata cancellata. Il posto è tornato disponibile.")

            # 3. Notifica agli utenti in lista d'attesa per questa uscita.
            utenti_in_attesa = Prenotazione.objects.filter(uscita=uscita_bloccata, stato='attesa')
            destinatari = [p.escursionista.email for p in utenti_in_attesa if p.escursionista.email]

            _invia_notifica_di_massa(
                oggetto=f"Posto liberato per {uscita_bloccata.escursione.titolo}!",
                messaggio=(
                    f"Ciao! Si è appena liberato un posto per l'uscita del "
                    f"{uscita_bloccata.data_ritrovo.strftime('%d/%m/%Y %H:%M')}. "
                    f"Il primo che accede al portale potrà prenotarlo!"
                ),
                destinatari=destinatari,
                from_email="noreply@waypoint.com",
            )
            if destinatari:
                # Log a console utile in fase di collaudo per dimostrare che
                # la logica di notifica si è attivata correttamente.
                print(f"[SISTEMA] Email di notifica (Bcc) inviata a: {destinatari}")
        else:
            messages.success(request, "Sei stato rimosso dalla lista d'attesa con successo.")

    return redirect('profilo')


@login_required
@require_POST  # Obbliga il metodo POST: impedisce l'eliminazione tramite semplice link/GET.
def elimina_escursione(request, escursione_id):
    """Elimina l'intero itinerario e, a cascata, tutte le uscite/prenotazioni collegate."""
    escursione = get_object_or_404(Escursione, id=escursione_id)

    # Controllo di ownership: solo la guida proprietaria può eliminare.
    if request.user == escursione.guida:
        escursione.delete()
        messages.success(request, f"L'itinerario '{escursione.titolo}' e tutte le sue date sono stati eliminati.")
    else:
        messages.error(request, "Non hai i permessi per eliminare questo itinerario.")

    return redirect('profilo')


@login_required
@require_POST
def elimina_uscita(request, uscita_id):
    """Elimina una singola data e notifica via email (in Bcc) gli iscritti."""
    uscita = get_object_or_404(Uscita, id=uscita_id)

    if request.user == uscita.escursione.guida:
        data_formattata = uscita.data_ritrovo.strftime('%d/%m/%Y alle %H:%M')
        titolo_itinerario = uscita.escursione.titolo

        # Recuperiamo tutti gli utenti iscritti PRIMA di cancellare l'uscita
        # (dopo il delete() la relazione Prenotazione->Uscita non esisterebbe più).
        prenotazioni_coinvolte = Prenotazione.objects.filter(uscita=uscita)
        lista_email = [p.escursionista.email for p in prenotazioni_coinvolte if p.escursionista.email]

        if lista_email:
            oggetto = f"Annullamento Uscita: {titolo_itinerario}"
            messaggio = (
                f"Gentile escursionista,\n\n"
                f"Ti informiamo con rammarico che la guida {uscita.escursione.guida.username} "
                f"ha dovuto annullare l'escursione '{titolo_itinerario}' prevista per il {data_formattata}.\n\n"
                f"La tua prenotazione è stata automaticamente annullata.\n"
                f"Ti invitiamo a visitare il nostro portale per scoprire altre date o nuovi itinerari.\n\n"
                f"A presto,\nIl Team di WayPoint"
            )
            # Notifica in vero Bcc: gli iscritti non si vedono a vicenda l'email.
            _invia_notifica_di_massa(oggetto, messaggio, lista_email, from_email='comunicazioni@waypoint.it')

        uscita.delete()
        messages.success(request,
                         f"La data del {data_formattata} è stata annullata. Sono state inviate {len(lista_email)} email di notifica agli iscritti.")
    else:
        messages.error(request, "Non hai i permessi per modificare questo calendario.")

    return redirect('profilo')
