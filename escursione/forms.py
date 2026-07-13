# =============================================================================
# APP "escursione" — FORM
# =============================================================================
from django import forms
from .models import Escursione, Uscita


# =============================================================================
# UPLOAD MULTIPLO DI FILE: CLASSI DI SUPPORTO
# =============================================================================
# TEORIA — perché servono classi custom: Django non fornisce nativamente un
# campo di form per il caricamento di PIÙ file contemporaneamente in un unico
# controllo <input type="file">. Il pattern qui implementato è quello
# raccomandato dalla documentazione ufficiale di Django per questo caso d'uso:
#
#   1) MultipleFileInput: sottoclasse del widget ClearableFileInput che
#      imposta l'attributo HTML "multiple" (allow_multiple_selected = True),
#      permettendo all'utente di selezionare più file dal proprio dispositivo
#      in un'unica finestra di dialogo.
#
#   2) MultipleFileField: sottoclasse di FileField che sovrascrive clean().
#      Un FileField "normale" si aspetta un SINGOLO file in ingresso, quindi
#      il suo clean() chiamerebbe le validazioni su
#      un solo oggetto. Qui invece request.FILES.getlist('foto_galleria')
#      restituisce una LISTA di file quando l'input HTML ha l'attributo
#      "multiple": il clean() sovrascritto rileva se il dato in ingresso è una
#      lista/tupla, e in tal caso applica la validazione standard del singolo
#      file (single_file_clean) a OGNUNO degli elementi, restituendo la lista
#      di file validati.
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={'class': 'form-control'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


# --- 1. FORM PRINCIPALE (La Scheda dell'Escursione/Sentiero) ---
class EscursioneForm(forms.ModelForm):
    """
     Form per la creazione (e potenziale modifica) degli itinerari base.

     È un ModelForm: i campi vengono generati automaticamente a partire dal
     modello Escursione (Meta.model), invece di riscriverli tutti a mano uno
     per uno. Un vantaggio pratico: quando si chiama save() su questo form,
     Django controlla in automatico anche le regole scritte nel metodo
     clean() del modello (es. Uscita.clean() in models.py). Questo controllo
     scatta SOLO passando da un form come questo: se invece un pezzo di
     codice modifica e salva un'escursione direttamente, senza form, quel
     controllo va richiamato a mano

     foto_galleria è scritto a parte, fuori dalla lista fields di Meta:
     non è una colonna vera del modello Escursione (che ha solo
     foto_copertina), è solo un campo "di passaggio" che serve a raccogliere
     le foto della galleria; una volta validato, la view
     (EscursioneCreateView.form_valid) lo legge a mano e crea le singole
     FotoGalleria collegate all'escursione appena salvata.
     """
    foto_galleria = MultipleFileField(
        required=False,
        label="Galleria Immagini Aggiuntive",
        help_text="Puoi caricare un massimo di 3 foto in una volta sola. Tieni premuto CTRL (o CMD su Mac) mentre selezioni i file."
    )

    class Meta:
        model = Escursione
        fields = [
            'titolo',
            'zona_geografica',
            'descrizione',
            'foto_copertina',
            'punto_di_ritrovo',
            'latitudine',
            'longitudine',
            'difficolta',
            'dislivello',
            'equipaggiamento'
        ]

        widgets = {
            'titolo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'es. Traversata del Gran Sasso o Sentiero degli Dei'
            }),
            'zona_geografica': forms.Select(attrs={'class': 'form-select'}),
            'descrizione': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Descrivi il percorso, i punti panoramici, il tipo di terreno...'
            }),
            'foto_copertina': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'punto_di_ritrovo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Coordinate o Rifugio (Cerca sulla mappa)'
            }),
            # latitudine/longitudine sono "readonly" nel form: il valore non è
            # digitato a mano dall'utente ma compilato via JavaScript dal
            # click sulla mappa Leaflet nel template (funzionalità facoltativa
            # "Visualizzazione Geografica" della traccia). Mantenerli readonly
            # evita coordinate incoerenti inserite manualmente.
            'latitudine': forms.NumberInput(attrs={
                'class': 'form-control bg-light',
                'readonly': 'readonly',
                'id': 'id_latitudine'
            }),
            'longitudine': forms.NumberInput(attrs={
                'class': 'form-control bg-light',
                'readonly': 'readonly',
                'id': 'id_longitudine'
            }),
            'difficolta': forms.Select(attrs={'class': 'form-select'}),
            'dislivello': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'es. 850'
            }),
            'equipaggiamento': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'title': 'Tieni premuto CTRL (o CMD su Mac) per selezionare più elementi',
                'style': 'height: 120px;'
            }),
        }

        labels = {
            'dislivello': 'Dislivello Positivo (m)',
            'foto_copertina': 'Immagine di Copertina'
        }

    def clean_foto_galleria(self):
        """
         Django, quando form.is_valid(), cerca automaticamente un metodo
         chiamato clean_<nome del campo> per ogni campo del form: se esiste,
         lo esegue e usa quello che restituisce come valore validato. Qui
         sfruttiamo questo per controllare che le foto caricate non siano più
         di 3, come richiesto dalla traccia.

         self.files.getlist('foto_galleria') prende direttamente i file
         inviati con quel nome dal form (non passiamo da self.cleaned_data
         perché foto_galleria, come spiegato sopra, non è un campo collegato
         al modello).
         """
        foto_multiple = self.files.getlist('foto_galleria')

        if len(foto_multiple) > 3:
            raise forms.ValidationError("Attenzione: puoi caricare un massimo di 3 foto aggiuntive!")

        return foto_multiple


# --- 2. FORM PER LA DATA SPECIFICA (L'Uscita prenotabile) ---
class UscitaForm(forms.ModelForm):
    """
    Form per la pianificazione di una singola data (Uscita) su un itinerario
    già esistente. Contiene solo data/ora di ritrovo e capienza massima: il
    resto delle informazioni tecniche (dislivello, difficoltà, ecc.)
    appartiene all'Escursione "genitore" e non va ripetuto qui.
    """
    class Meta:
        model = Uscita
        # Rimuoviamo i campi della mappa, teniamo solo data e posti!
        fields = [
            'data_ritrovo',
            'posti_totali'
        ]

        widgets = {
            'data_ritrovo': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'posti_totali': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Capienza massima (es. 15)',
                'min': '1'
            }),
        }

        labels = {
            'data_ritrovo': 'Data e Ora di Ritrovo',
            'posti_totali': 'Numero Massimo Partecipanti',
        }