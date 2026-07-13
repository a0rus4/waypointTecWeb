# =============================================================================
# APP "utenti" — FORM DI REGISTRAZIONE
# =============================================================================
from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from core.constants import GRUPPO_GUIDE, GRUPPO_ESCURSIONISTI


class RegistrazioneForm(UserCreationForm):
    """
    Form di registrazione: estende UserCreationForm (nativo di Django, che
    gestisce già validazione e hashing sicuro della password) aggiungendo un
    campo virtuale `ruolo`, NON persistito direttamente sul modello User, ma
    usato in save() per decidere a quale Group iscrivere il nuovo utente.

    TEORIA — perché i ruoli sono Gruppi e non un campo su User: Django
    fornisce nativamente un sistema di Gruppi e Permessi (django.contrib.auth)
    pensato esattamente per modellare ruoli come "Guide" ed "Escursionisti"
    senza dover creare un modello Utente personalizzato. Riutilizzarlo evita
    di duplicare la logica di autenticazione (già solida e testata) e
    sfrutta le API già pronte per verificare l'appartenenza a un ruolo
    (user.groups.filter(name=...).exists(), usato in tutte le view di
    escursione/ e recensioni/).
    """
    SCELTA_RUOLO = [
        ('escursionista', 'Escursionista (Voglio partecipare alle escursioni)'),
        ('guida', 'Guida Ambientale (Voglio organizzare e pubblicare itinerari)'),
    ]

    ruolo = forms.ChoiceField(
        choices=SCELTA_RUOLO,
        label="Seleziona il tipo di profilo",
        required=True
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Applica le classi Bootstrap a tutti i campi generati automaticamente
        # da UserCreationForm (username, password1, password2, ...) oltre a
        # quelli aggiunti qui, per uniformità grafica col resto del sito.
        for field_name, field in self.fields.items():
            if field_name == 'ruolo':
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

    def save(self, commit=True):
        """
        Dopo aver salvato l'utente (che gestisce anche l'hashing della
        password tramite UserCreationForm.save()), lo si iscrive al Group
        corretto in base alla scelta fatta nel form. get_or_create() rende
        l'operazione sicura anche alla primissima registrazione, quando il
        gruppo potrebbe non esistere ancora nel database.
        """
        user = super().save(commit=commit)
        if commit:
            ruolo_scelto = self.cleaned_data.get('ruolo')
            nome_gruppo = GRUPPO_GUIDE if ruolo_scelto == 'guida' else GRUPPO_ESCURSIONISTI
            gruppo, _ = Group.objects.get_or_create(name=nome_gruppo)
            user.groups.add(gruppo)
        return user
