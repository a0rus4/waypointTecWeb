# =============================================================================
# APP "recensioni" — CONFIGURAZIONE ADMIN + MODERAZIONE
# =============================================================================
# Oltre alla normale gestione CRUD delle recensioni, questo file collega
# direttamente il flusso di moderazione descritto dalla traccia
# ("Amministratori: gestire le segnalazioni relative alle recensioni,
# applicando provvedimenti - ban o avvertimenti - se necessario") tramite due
# ADMIN ACTIONS: operazioni disponibili come menu a tendina sopra l'elenco
# delle recensioni nel pannello di amministrazione, applicabili in un solo
# click alle recensioni selezionate (tipicamente quelle con segnalata=True).
#
# TEORIA — admin actions: sono funzioni con firma (modeladmin, request,
# queryset) decorate con @admin.action(...), registrate nell'attributo
# `actions` di un ModelAdmin. Django le espone automaticamente come opzioni
# selezionabili nella tendina "Azione" dell'elenco changelist, applicabili in
# blocco a tutte le righe selezionate dall'amministratore.
# =============================================================================
from django.contrib import admin
from .models import Recensione
from utenti.models import Provvedimento


@admin.action(description="Applica un AVVERTIMENTO formale all'autore delle recensioni selezionate")
def applica_avvertimento(modeladmin, request, queryset):
    """
    Crea un Provvedimento di tipo 'avvertimento' per l'autore di ciascuna
    recensione selezionata. Un avvertimento è un provvedimento FORMALE ma non
    bloccante: non sospende l'account, resta solo come precedente registrato
    nello storico disciplinare dell'utente (Provvedimento.utente.provvedimenti).
    """
    contatore = 0
    for recensione in queryset:
        Provvedimento.objects.create(
            utente=recensione.autore,
            amministratore=request.user,
            tipo='avvertimento',
            motivazione=f"Avvertimento applicato in seguito alla segnalazione sulla recensione #{recensione.id} "
                        f"(\"{recensione.testo[:80]}...\").",
            recensione_collegata=recensione,
        )
        contatore += 1
    modeladmin.message_user(request, f"Avvertimento applicato all'autore di {contatore} recensione/i.")


@admin.action(description="Applica un BAN (sospensione account) all'autore delle recensioni selezionate")
def applica_ban(modeladmin, request, queryset):
    """
    Crea un Provvedimento di tipo 'ban' per l'autore di ciascuna recensione
    selezionata e sospende immediatamente l'account (User.is_active=False):
    da questo momento l'utente non potrà più autenticarsi sul portale, in
    linea con il requisito di traccia "ban... se necessario".
    """
    contatore = 0
    utenti_gia_sospesi = set()
    for recensione in queryset:
        Provvedimento.objects.create(
            utente=recensione.autore,
            amministratore=request.user,
            tipo='ban',
            motivazione=f"Ban applicato in seguito alla segnalazione sulla recensione #{recensione.id} "
                        f"(\"{recensione.testo[:80]}...\").",
            recensione_collegata=recensione,
        )
        if recensione.autore_id not in utenti_gia_sospesi:
            recensione.autore.is_active = False
            recensione.autore.save(update_fields=['is_active'])
            utenti_gia_sospesi.add(recensione.autore_id)
        contatore += 1
    modeladmin.message_user(
        request,
        f"Ban applicato: {contatore} provvedimento/i creato/i, {len(utenti_gia_sospesi)} account sospeso/i."
    )


@admin.register(Recensione)
class RecensioneAdmin(admin.ModelAdmin):
    list_display = ('escursione', 'autore', 'voto', 'segnalata', 'data_creazione')
    list_filter = ('segnalata', 'voto', 'data_creazione')
    search_fields = ('autore__username', 'escursione__titolo', 'testo')
    # list_editable permette di deselezionare rapidamente 'segnalata' una
    # volta che una segnalazione è stata esaminata e chiusa dall'amministratore.
    list_editable = ('segnalata',)
    actions = [applica_avvertimento, applica_ban]
