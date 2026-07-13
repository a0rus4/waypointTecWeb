from django.db import models

# =============================================================================
# APP "utenti" — MODELLO Provvedimento
# =============================================================================
# la traccia richiede che "Gli Amministratori possano gestire le
# segnalazioni relative alle recensioni, applicando provvedimenti (ban o
# avvertimenti) se necessario".
#
# Provvedimento introduce quindi una vera e propria "storia disciplinare"
# dell'utente: ogni volta che un amministratore applica una sanzione, viene
# creato un record che ne conserva tipo, motivazione, autore (quale
# amministratore) e data. Il ban, quando applicato, sospende automaticamente
# l'account (is_active=False) tramite l'azione di amministrazione definita in
# recensioni/admin.py; l'avvertimento resta invece solo un record formale,
# senza impedire l'accesso.
# =============================================================================
from django.db import models
from django.contrib.auth.models import User


class Provvedimento(models.Model):
    TIPO_SCELTE = [
        ('avvertimento', 'Avvertimento'),
        ('ban', 'Ban (sospensione account)'),
    ]

    # L'utente sanzionato. on_delete=CASCADE: se l'account viene eliminato
    # definitivamente, non ha senso conservare provvedimenti "orfani".
    utente = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='provvedimenti'
    )

    # Quale amministratore ha applicato il provvedimento. SET_NULL (anziché
    # CASCADE) perché la cancellazione dell'account di un amministratore non
    # deve far sparire lo storico dei provvedimenti da lui emessi: resta
    # traccia dell'accaduto anche se non si sa più "chi" materialmente lo
    # abbia applicato.
    amministratore = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provvedimenti_emessi'
    )

    tipo = models.CharField(max_length=20, choices=TIPO_SCELTE)
    motivazione = models.TextField(
        help_text="Motivazione del provvedimento, es. riferimento alla segnalazione che lo ha originato."
    )

    # Riferimento facoltativo alla recensione che ha originato il
    # provvedimento (se applicabile: un provvedimento potrebbe in teoria
    # essere emesso anche per altri motivi non legati a una specifica
    # recensione). Si usa un riferimento stringa ('recensioni.Recensione')
    # anziché importare direttamente la classe: questo evita un import
    # circolare a livello di modulo, dato che recensioni/models.py importa
    # già escursione.models (e non utenti.models), mentre qui basterebbe un
    # import diretto — ma il riferimento a stringa è comunque la pratica
    # idiomatica raccomandata da Django per i riferimenti fra app diverse,
    # perché non richiede che l'app "recensioni" sia già stata caricata nel
    # momento in cui questo modulo viene importato.
    recensione_collegata = models.ForeignKey(
        'recensioni.Recensione',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provvedimenti_generati'
    )

    data_creazione = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Provvedimenti"
        ordering = ['-data_creazione']

    def __str__(self):
        return f"{self.get_tipo_display()} a {self.utente.username} del {self.data_creazione:%d/%m/%Y}"
