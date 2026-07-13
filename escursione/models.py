# =============================================================================
# APP "escursione" — MODELLI DI DOMINIO
# =============================================================================
# TEORIA — ORM (Object-Relational Mapping): ogni classe che eredita da
# models.Model viene tradotta da Django in una tabella del database
# relazionale; ogni attributo di classe (CharField, ForeignKey, ...) diventa
# una colonna. Le relazioni tra tabelle sono espresse con:
#   - ForeignKey: relazione 1-a-N (es. una Escursione ha molte Uscite);
#   - ManyToManyField: relazione N-a-N, gestita da Django tramite una tabella
#     ponte generata automaticamente (es. Escursione <-> Equipaggiamento);
# on_delete definisce cosa succede alle righe collegate quando la riga
# "genitore" viene eliminata: CASCADE elimina a cascata anche le righe figlie,
# SET_NULL azzera il riferimento (utile per FK facoltative, come
# zona_geografica, dove non vogliamo perdere l'escursione se la zona viene
# rimossa dal catalogo).
#
# Lo schema separa deliberatamente due concetti che nel linguaggio comune si
# confondono entrambi come "l'escursione":
#   - Escursione: la scheda "anagrafica" del sentiero, permanente nel tempo;
#   - Uscita: la singola data in cui quel sentiero viene effettivamente
#     proposto, con una propria capienza indipendente.
# Questa normalizzazione evita di duplicare titolo/descrizione/dislivello per
# ogni data e riflette correttamente il dominio: la stessa escursione può
# avere più date con disponibilità di posti diverse.
# =============================================================================

from django.contrib.auth.models import User
from django.db.models import Avg
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


# Scelte per il campo "difficolta": una tupla (valore_salvato, etichetta)
# per ogni opzione. Django genera automaticamente il metodo
# get_difficolta_display() che restituisce l'etichetta leggibile a partire dal
# codice memorizzato nel database (es. 'EE' -> 'Esperti').
SCELTE_DIFFICOLTA = [
    ('T', 'Turistico'),
    ('E', 'Escursionistico'),
    ('EE', 'Esperti'),
]


class Equipaggiamento(models.Model):
    """
    Tabella di lookup per l'equipaggiamento tecnico richiesto (es. "Ramponi",
    "Imbrago"). Tenerla come tabella separata (anziché un campo testo libero
    sull'Escursione) evita errori di battitura/duplicati nei filtri e permette
    di popolare tendine a selezione multipla coerenti in tutto il sito.
    """
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name_plural = "Equipaggiamenti"


class ZonaGeografica(models.Model):
    """Tabella di lookup per le macro-zone geografiche."""
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name_plural = "Zone Geografiche"
        ordering = ['nome']  # Ordina alfabeticamente le regioni nei menu a tendina


class Escursione(models.Model):
    """
    IL MODELLO BASE: rappresenta il sentiero permanente (la "scheda"
    dell'itinerario), indipendentemente da QUANDO viene proposto.

    Il campo `approvata` (default False) implementa il flusso di moderazione
    richiesto dalla traccia: un'escursione appena creata da una Guida non è
    visibile nel catalogo pubblico finché un Amministratore non la valida
    (l'approvazione avviene dal pannello di amministrazione nativo di Django).
    """
    titolo = models.CharField(max_length=100)

    # related_name='escursioni_create' permette di risalire, a partire da uno
    # User, a tutte le escursioni che ha creato con la sintassi
    # user.escursioni_create.all() (usato in utenti/views.py per la dashboard
    # della Guida).
    guida = models.ForeignKey(User, on_delete=models.CASCADE, related_name='escursioni_create')

    # facoltativa: SET_NULL preserva l'escursione anche se la zona
    # geografica venisse rimossa dal catalogo di riferimento.
    zona_geografica = models.ForeignKey(ZonaGeografica, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='escursioni')

    punto_di_ritrovo = models.CharField(max_length=100)

    # Coordinate geografiche del punto di ritrovo, usate dal template di
    # dettaglio per mostrare una mappa interattiva (funzionalità facoltativa
    # "Visualizzazione Geografica" della traccia, realizzata lato client con
    # Leaflet.js/OpenStreetMap: il backend si limita a persistere la coppia
    # di coordinate scelte dalla Guida cliccando sulla mappa in fase di
    # creazione). null=True/blank=True perché non tutte le escursioni
    # potrebbero avere una posizione precisa al momento della creazione.
    latitudine = models.FloatField(null=True, blank=True)
    longitudine = models.FloatField(null=True, blank=True)

    descrizione = models.TextField()
    dislivello = models.PositiveIntegerField()

    # Relazione N-a-N: un'escursione può richiedere più attrezzature, e la
    # stessa attrezzatura può servire a più escursioni.
    equipaggiamento = models.ManyToManyField(Equipaggiamento, blank=True, related_name='escursioni')

    difficolta = models.CharField(max_length=2, choices=SCELTE_DIFFICOLTA)
    foto_copertina = models.ImageField(upload_to='escursione/copertine/')
    approvata = models.BooleanField(default=False)

    def __str__(self):
        return self.titolo

    class Meta:
        verbose_name_plural = "Escursioni"

    # =========================================================================
    # PROPERTY CALCOLATE: RATING E REPUTAZIONE
    # =========================================================================
    # TEORIA — property Python + aggregazione Django (Avg): questi due
    # attributi non sono colonne del database, ma valori calcolati "on the
    # fly" a ogni accesso. Si preferisce questo approccio perché garantisce che il valore restituito sia
    # SEMPRE coerente con lo stato corrente delle recensioni nel database,
    # senza bisogno di codice aggiuntivo per tenerlo sincronizzato.

    @property
    def punteggio_medio(self):
        """
        Rating del singolo sentiero: media dei voti di TUTTE le recensioni
        collegate a questa escursione. self.recensioni è la relazione inversa
        generata automaticamente da Recensione.escursione (related_name=
        'recensioni', definito in recensioni/models.py).
        aggregate(Avg('voto')) esegue un'unica query SQL (AVG(voto)) e
        restituisce un dizionario {'voto__avg': <valore o None>}; se non ci
        sono ancora recensioni il valore è None, gestito col fallback a 0.0.
        """
        media = self.recensioni.aggregate(Avg('voto'))['voto__avg']
        return round(media, 1) if media else 0.0

    @property
    def punteggio_guida(self):
        """
        Reputazione della Guida: media di TUTTI i voti ricevuti dalla guida su
        TUTTE le escursioni che ha organizzato. È il dato
        che la traccia definisce "la reputazione della guida".
        L'import di Recensione è fatto qui dentro (non in cima al file) per
        evitare un import circolare: recensioni/models.py importa già
        escursione.models.Escursione, quindi un import a livello di modulo qui
        (escursione.models -> recensioni.models -> escursione.models) fallirebbe;
        importando dentro il metodo, la risoluzione avviene solo quando la
        property viene effettivamente letta, quando entrambi i moduli sono già
        stati caricati.
        """
        from recensioni.models import Recensione
        media = Recensione.objects.filter(escursione__guida=self.guida).aggregate(Avg('voto'))['voto__avg']
        return round(media, 1) if media else 0.0


class FotoGalleria(models.Model):
    """
    Galleria di immagini aggiuntive di un'escursione (fino a 3, vincolo
    applicato lato form in escursione/forms.py). Modellata come tabella
    separata con ForeignKey verso Escursione
    perché rappresenta una relazione 1-a-N
    """
    escursione = models.ForeignKey(Escursione, on_delete=models.CASCADE, related_name='galleria')
    immagine = models.ImageField(upload_to='escursione/galleria/')

    def __str__(self):
        return f"Foto per {self.escursione.titolo}"

    class Meta:
        verbose_name_plural = "Foto Galleria"


class Uscita(models.Model):
    """
    IL MODELLO DI ISTANZA/EVENTO: rappresenta la specifica data in cui viene
    effettivamente proposta un'Escursione, con la propria capienza
    indipendente (posti_totali / posti_occupati). È l'oggetto su cui si
    prenota effettivamente un escursionista.
    """
    escursione = models.ForeignKey(Escursione, on_delete=models.CASCADE, related_name='uscite_programmate')
    data_ritrovo = models.DateTimeField()

    # La gestione dei posti è legata alla singola data, non all'escursione:
    # la stessa escursione può avere una data quasi vuota e una completamente
    # esaurita nello stesso momento.
    posti_totali = models.PositiveIntegerField()
    posti_occupati = models.PositiveIntegerField(default=0)

    def clean(self):
        """
          1) i posti occupati non possono mai superare i posti totali;
          2) non è possibile PIANIFICARE una nuova uscita con una data già
             passata.
        """
        if self.posti_occupati is not None and self.posti_totali is not None:
            if self.posti_occupati > self.posti_totali:
                raise ValidationError("Errore: I posti occupati non possono superare i posti totali!")
            if self.posti_occupati < 0:
                raise ValidationError("Errore: I posti occupati non possono essere negativi!")

        if self._state.adding and self.data_ritrovo and self.data_ritrovo < timezone.now():
            raise ValidationError("Errore: Non puoi pianificare un'uscita nel passato!")

    def __str__(self):
        return f"{self.escursione.titolo} del {self.data_ritrovo.strftime('%d/%m/%Y %H:%M')}"

    class Meta:
        verbose_name_plural = "Uscite Programmate"

class Prenotazione(models.Model):
    """
    Collega un escursionista a una specifica Uscita (data). Il campo `stato`
    distingue due situazioni: prenotazione confermata (posto garantito) e
    prenotazione in lista d'attesa (l'uscita era già piena al momento della
    richiesta). Non esiste uno stato "cancellata": quando l'utente disdice
    (escursione/views.py -> cancella_prenotazione), la riga viene eliminata
    fisicamente dal database, non marcata con uno stato diverso.
    """
    STATO_SCELTE = [
        ('confermata', 'Confermata'),
        ('attesa', 'In lista d\'attesa'),
    ]
    escursionista = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prenotazioni')
    uscita = models.ForeignKey(Uscita, on_delete=models.CASCADE, related_name='prenotazioni')
    data_prenotazione = models.DateTimeField(auto_now_add=True)
    stato = models.CharField(max_length=20, choices=STATO_SCELTE, default='confermata')

    class Meta:
        # Vincolo di UNICITÀ A LIVELLO DI DATABASE (non solo applicativo): il
        # DBMS stesso rifiuta un secondo INSERT con la stessa coppia
        # (escursionista, uscita), sollevando IntegrityError lato Django. È
        # una doppia protezione rispetto al controllo "soft" fatto nella view
        # prenota_uscita (che verifica prima con un .exists()): anche se due
        # richieste concorrenti superassero entrambe il controllo applicativo
        # il database garantirebbe comunque l'unicità finale.
        unique_together = ('escursionista', 'uscita')
        verbose_name_plural = "Prenotazioni"

    def __str__(self):
        return f"{self.escursionista.username} -> {self.uscita} ({self.stato})"
