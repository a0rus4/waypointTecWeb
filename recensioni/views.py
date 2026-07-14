# =============================================================================
# APP "recensioni" — VISTE: CREAZIONE, RISPOSTA, SEGNALAZIONE
# =============================================================================
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError
from django.utils import timezone

from escursione.models import Escursione, Prenotazione
from .models import Recensione
from .forms import RecensioneForm, RispostaGuidaForm
from core.constants import GRUPPO_ESCURSIONISTI


@login_required
def crea_recensione(request, escursione_id):
    """
    Gestisce l'inserimento di una recensione da parte di un Escursionista.

    Requisito di traccia: "Iscriversi alle uscite e lasciare recensioni
    post-evento." occorre dimostrare un'effettiva
    partecipazione PASSATA e CONFERMATA, non una semplice iscrizione futura.
    """
    escursione = get_object_or_404(Escursione, id=escursione_id)

    # Controllo di ruolo.
    if not request.user.groups.filter(name=GRUPPO_ESCURSIONISTI).exists():
        messages.error(request, "Operazione negata. Solo gli escursionisti possono valutare gli itinerari.")
        return redirect('dettaglio_escursione', pk=escursione.id)

    # Controllo di partecipazione effettiva: almeno una prenotazione
    # CONFERMATA su un'uscita di QUESTA escursione la cui data sia già
    # trascorsa (data_ritrovo__lt=ora). Impedisce sia recensioni "a freddo" da
    # chi non ha mai partecipato, sia recensioni premature prima che l'evento
    # si sia concluso.
    ha_partecipato = Prenotazione.objects.filter(
        escursionista=request.user,
        uscita__escursione=escursione,
        stato='confermata',
        uscita__data_ritrovo__lt=timezone.now(),
    ).exists()

    if not ha_partecipato:
        messages.error(request,
                       "Puoi recensire l'itinerario a cui ti sei prenotato solo dopo che l'evento si è concluso. Se ti sei appena iscritto, attendi la fine dell'escursione!")
        return redirect('dettaglio_escursione', pk=escursione.id)

    if request.method == 'POST':
        form = RecensioneForm(request.POST)
        if form.is_valid():
            recensione = form.save(commit=False)
            recensione.escursione = escursione
            recensione.autore = request.user

            try:
                # TEORIA — perché il try/except invece di un controllo
                # preventivo con .exists(): il vincolo unique_together
                # (escursione, autore) del modello Recensione è imposto anche
                # a livello di database. Anche se in teoria si potrebbe
                # controllare prima con Recensione.objects.filter(...).exists(),
                # rimane comunque una finestra temporale (check-then-act) in
                # cui due richieste quasi simultanee dello stesso utente
                # (doppio click, doppia scheda del browser) potrebbero
                # superare entrambe il controllo preventivo. Affidarsi al
                # vincolo di database e intercettare l'eccezione risultante
                # è la protezione ultima e definitiva, indipendente da
                # eventuali race condition applicative.
                recensione.save()
                messages.success(request, "Recensione pubblicata con successo. Grazie per il tuo contributo!")
            except IntegrityError:
                messages.warning(request, "Hai già lasciato una valutazione per questo specifico itinerario.")

    return redirect('dettaglio_escursione', pk=escursione.id)


@login_required
def rispondi_recensione(request, recensione_id):
    """
    Consente alla Guida titolare dell'escursione di replicare ufficialmente a
    una recensione ricevuta (requisito di traccia: "Visualizzare le
    recensioni degli utenti e rispondere alle stesse").
    """
    recensione = get_object_or_404(Recensione, id=recensione_id)

    # Controllo di OWNERSHIP: solo la guida che ha organizzato questa
    # specifica escursione può rispondere alla recensione, non una guida
    # qualsiasi. recensione.escursione.guida attraversa due relazioni ForeignKey
    # (Recensione -> Escursione -> User) in una singola espressione grazie
    # all'accesso per attributo dell'ORM Django.
    if request.user != recensione.escursione.guida:
        messages.error(request, "Errore di sicurezza: non sei autorizzato a rispondere a questa recensione.")
        return redirect('dettaglio_escursione', pk=recensione.escursione.id)

    if request.method == 'POST':
        # instance=recensione: il form aggiorna il record esistente
        # (UPDATE del solo campo risposta_guida) invece di crearne uno nuovo.
        form = RispostaGuidaForm(request.POST, instance=recensione)
        if form.is_valid():
            form.save()
            messages.success(request, "La tua replica ufficiale è stata pubblicata.")

    return redirect('dettaglio_escursione', pk=recensione.escursione.id)
# =============================================================================
# TEORIA — @login_required e @require_POST:
# =============================================================================
# @login_required (django.contrib.auth.decorators): verifica
# request.user.is_authenticated PRIMA di eseguire la funzione. Se l'utente è
# anonimo, lo reindirizza alla pagina di login (settings.LOGIN_URL) invece di
# lasciarlo proseguire.
#
# @require_POST (django.views.decorators.http): verifica request.method.
# Se la richiesta non è una POST (es. è una GET), risponde 405 Method Not
# Allowed e la funzione sottostante non viene nemmeno eseguita.
#
#   - Una richiesta GET può essere generata SENZA alcuna azione volontaria
#     dell'utente
#     Se questa vista fosse raggiungibile via GET, chiunque potrebbe indurre
#     un utente già loggato a eseguirla a sua insaputa
#   - La protezione CSRF (CsrfViewMiddleware, attiva globalmente in
#     settings.py) si applica SOLO alle richieste POST: controlla che il
#     modulo che le invia sia stato davvero generato dal
#     nostro sito per la sessione corrente, e non da una pagina esterna.
# =============================================================================
@require_POST
@login_required
def segnala_recensione(request, recensione_id):
    """
    Consente a un Escursionista di segnalare una recensione altrui sospetta
    per la moderazione amministrativa (requisito di traccia: "Segnalare
    recensioni di altri utenti").

    La segnalazione si limita a impostare il flag `segnalata=True`: la
    decisione su come intervenire (nessuna azione, avvertimento, ban) spetta
    all'Amministratore, che dal pannello Django Admin (recensioni/admin.py)
    visualizza tutte le recensioni segnalate e può applicare un Provvedimento
    all'autore direttamente da lì (si veda utenti/models.py -> Provvedimento
    e le azioni admin definite in recensioni/admin.py).
    """
    recensione = get_object_or_404(Recensione, id=recensione_id)

    if request.user.groups.filter(name=GRUPPO_ESCURSIONISTI).exists():
        recensione.segnalata = True
        recensione.save()
        messages.info(request, "La recensione è stata inoltrata all'amministratore per la moderazione.")
    else:
        messages.error(request,
                       "Solo gli utenti accreditati come escursionisti possono usare il sistema di segnalazione.")

    return redirect('dettaglio_escursione', pk=recensione.escursione.id)
