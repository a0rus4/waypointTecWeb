# =============================================================================
# APP "utenti" — CONFIGURAZIONE ADMIN
# =============================================================================
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Provvedimento

# Rimuoviamo la registrazione standard del modello User fatta di default da
# Django, per sostituirla con una versione personalizzata (CustomUserAdmin)
# che mostra anche il gruppo/ruolo di ciascun utente.
admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Aggiungiamo la colonna personalizzata 'get_gruppi' alle colonne
    # standard già fornite da UserAdmin.
    list_display = ('username', 'email', 'get_gruppi', 'is_staff', 'is_active')
    list_filter = ('groups', 'is_staff', 'is_superuser', 'is_active')

    def get_gruppi(self, obj):
        """Estrae i nomi dei gruppi dell'utente e li unisce in una stringa leggibile."""
        return ", ".join([group.name for group in obj.groups.all()])
    get_gruppi.short_description = 'Ruolo / Gruppi'


@admin.register(Provvedimento)
class ProvvedimentoAdmin(admin.ModelAdmin):
    """
    Pannello dedicato allo storico dei provvedimenti (ban/avvertimenti)
    applicati agli utenti. Nella pratica i Provvedimenti vengono creati
    principalmente tramite le azioni rapide "Applica avvertimento"/"Applica
    ban" disponibili nell'elenco delle Recensioni segnalate (si veda
    recensioni/admin.py); questo pannello permette comunque
    all'amministratore di consultare lo storico completo, o di registrare
    manualmente un provvedimento non legato a una specifica recensione.
    """
    list_display = ('utente', 'tipo', 'amministratore', 'data_creazione')
    list_filter = ('tipo', 'data_creazione')
    search_fields = ('utente__username', 'motivazione')
    readonly_fields = ('data_creazione',)

    def save_model(self, request, obj, form, change):
        """
        Se il provvedimento viene creato manualmente da questo pannello
        (anziché tramite le azioni rapide di recensioni/admin.py):
          - se il campo amministratore non è stato specificato, lo si
            imposta automaticamente all'utente admin che sta operando;
          - se il tipo è 'ban', si sospende automaticamente l'account
            (stesso comportamento delle azioni rapide, per coerenza).
        """
        if not obj.amministratore_id:
            obj.amministratore = request.user
        super().save_model(request, obj, form, change)
        if obj.tipo == 'ban' and obj.utente.is_active:
            obj.utente.is_active = False
            obj.utente.save(update_fields=['is_active'])
