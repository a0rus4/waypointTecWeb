# =============================================================================
# APP "recensioni" — MODELLO Recensione
# =============================================================================
# Implementa la funzionalità facoltativa "Sistema di Recensioni" della
# traccia: feedback post-evento con voto numerico, che alimenta sia il rating
# del singolo sentiero sia la "reputazione" della guida (si vedano le
# property Escursione.punteggio_medio e Escursione.punteggio_guida in
# escursione/models.py), oltre al flusso di moderazione (segnalazione da
# parte degli escursionisti, gestione dei provvedimenti da parte degli
# amministratori — si veda utenti/models.py -> Provvedimento).
# =============================================================================
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from escursione.models import Escursione


class Recensione(models.Model):
    escursione = models.ForeignKey(
        Escursione,
        on_delete=models.CASCADE,
        related_name='recensioni'
    )
    autore = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='recensioni_scritte'
    )

    # TEORIA — validators: MinValueValidator/MaxValueValidator sono
    # validatori nativi di Django applicati automaticamente da full_clean()
    # (quindi da qualunque ModelForm, come RecensioneForm) e riportati anche
    # negli schemi generati per l'admin. Vincolano il voto all'intervallo
    # [1, 5] richiesto dalla traccia ("voti numerici").
    voto = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    testo = models.TextField()
    data_creazione = models.DateTimeField(auto_now_add=True)

    # Campi per l'interazione asimmetrica prevista dalla traccia:
    #   - segnalata: valorizzato dagli Escursionisti (chiunque può segnalare
    #     una recensione altrui sospetta), letto dagli Amministratori per la
    #     moderazione (si veda recensioni/admin.py).
    #   - risposta_guida: valorizzato dalla Guida titolare dell'escursione
    #     recensita, per "rispondere alle recensioni" (requisito di traccia).
    #     È un semplice campo di testo sulla STESSA riga della recensione
    #     (relazione 1-a-1 implicita), non un modello separato: scelta
    #     ragionevole perché esiste al massimo UNA risposta ufficiale per
    #     recensione.
    segnalata = models.BooleanField(default=False)
    risposta_guida = models.TextField(
        blank=True,
        default='',
        verbose_name="Risposta della Guida"
    )

    class Meta:
        # Vincolo di unicità a livello di database: un utente può lasciare
        # AL MASSIMO una recensione per ogni escursione (non per ogni Uscita:
        # anche partecipando a più date della stessa escursione, la recensione
        # complessiva sull'itinerario resta una sola).
        unique_together = ('escursione', 'autore')
        verbose_name_plural = "Recensioni"
        ordering = ['-data_creazione']

    def __str__(self):
        return f"[{self.voto}/5] {self.autore.username} - {self.escursione.titolo}"
