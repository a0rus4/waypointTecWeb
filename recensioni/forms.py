# =============================================================================
# APP "recensioni" — FORM
# =============================================================================
from django import forms
from .models import Recensione


class RecensioneForm(forms.ModelForm):
    """
    Modulo utilizzato dagli Escursionisti per lasciare un feedback dopo aver
    partecipato a un'escursione. Espone solo i campi che l'AUTORE della
    recensione deve compilare (voto, testo): escursione e autore vengono
    impostati lato server nella view (recensioni/views.py -> crea_recensione),
    non dal form, per evitare che un utente possa "recensire per conto di
    un altro" o assegnare la recensione a un'escursione diversa da quella
    effettivamente visualizzata.
    """
    class Meta:
        model = Recensione
        fields = ['voto', 'testo']
        labels = {
            'voto': 'Valutazione (da 1 a 5)',
            'testo': 'La tua recensione'
        }
        widgets = {
            'voto': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'testo': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Racconta la tua esperienza sul sentiero e con la guida...'}),
        }


class RispostaGuidaForm(forms.ModelForm):
    """
    Modulo utilizzato dalle Guide per replicare pubblicamente a una recensione
    ricevuta. Espone il SOLO campo risposta_guida: passando instance=recensione
    nella view, il form aggiorna la riga esistente (UPDATE) invece di crearne
    una nuova, e gli altri campi della recensione (voto, testo dell'autore)
    restano invariati.
    """
    class Meta:
        model = Recensione
        fields = ['risposta_guida']
        labels = {
            'risposta_guida': 'La tua risposta come Guida'
        }
        widgets = {
            'risposta_guida': forms.Textarea(attrs={'class': 'form-control border-success', 'rows': 3, 'placeholder': 'Scrivi una risposta ufficiale a questo escursionista...'}),
        }
