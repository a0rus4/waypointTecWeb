# =============================================================================
# APP "escursione" — CONFIGURAZIONE DEL PANNELLO DI AMMINISTRAZIONE
# =============================================================================
# TEORIA — django.contrib.admin: Django genera automaticamente un'interfaccia
# CRUD (Create/Read/Update/Delete) completa per ogni modello registrato, senza
# scrivere una riga di HTML o di view: è lo strumento con cui, in questo
# progetto, gli Amministratori svolgono il requisito di traccia "Approvare la
# creazione delle escursioni, verificandone l'idoneità delle informazioni"
# Si tratta di
# una scelta di design deliberata: evita di scrivere e mantenere viste custom
# per un'operazione (moderazione dei contenuti) che riguarda solo un ruolo
# ristretto (gli amministratori) e per cui Django Admin offre già sicurezza,
# permessi granulari e un'interfaccia funzionale collaudata.
# =============================================================================
from django.contrib import admin
from .models import Escursione, Uscita, Equipaggiamento, ZonaGeografica, Prenotazione


class UscitaInline(admin.TabularInline):
    """
    TEORIA — inline: permette di modificare i record di un modello collegato
    (qui: le Uscite di un'Escursione) direttamente nella pagina di modifica
    del modello "genitore", senza dover navigare in una sezione separata
    dell'admin. extra=1 mostra sempre una riga vuota aggiuntiva, pronta per
    inserire subito una nuova data senza ulteriori click.
    """
    model = Uscita
    extra = 1


@admin.register(Escursione)
class EscursioneAdmin(admin.ModelAdmin):
    # list_display: colonne mostrate nell'elenco; includere 'approvata' rende
    # immediatamente visibile, in un colpo d'occhio, quali itinerari sono
    # ancora in attesa di validazione.
    list_display = ('titolo', 'guida', 'zona_geografica', 'difficolta', 'approvata')
    # list_filter: aggiunge una barra laterale di filtri rapidi, essenziale
    # per l'amministratore che voglia isolare velocemente le sole escursioni
    # NON ancora approvate (approvata=False) da validare.
    list_filter = ('approvata', 'difficolta', 'zona_geografica')
    search_fields = ('titolo', 'descrizione')
    inlines = [UscitaInline]


# Registrazione "semplice" (senza personalizzazioni particolari) degli altri
# modelli, per poterli comunque gestire liberamente dal pannello admin.
admin.site.register(Uscita)
admin.site.register(Equipaggiamento)
admin.site.register(ZonaGeografica)
admin.site.register(Prenotazione)
