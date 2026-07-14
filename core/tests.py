# =============================================================================
# TEST DELL'APP "core" — MOTORE DI RICERCA E HOMEPAGE PUBBLICA
# =============================================================================
# TEORIA — perché testare le view e non solo i modelli: i modelli da soli
# (Escursione, Uscita) hanno una logica minima; il "cervello" della homepage
# sta tutto dentro core/views.py (filtri combinabili, whitelist di sicurezza,
# paginazione robusta). Un test che si limitasse a verificare "il modello si
# salva" non direbbe nulla su QUESTO codice. Per questo qui si usa
# self.client (il client di test di Django, che simula un vero browser:
# fa richieste HTTP reali contro le view, senza aprire un browser vero) e si
# ispeziona response.context (il dizionario passato al template dalla view)
# per verificare esattamente quali dati sono arrivati dopo aver applicato i
# filtri.
# =============================================================================
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User

# Importiamo i modelli necessari
from escursione.models import Escursione, Uscita


class CoreHomeViewTests(TestCase):
    """
    Testiamo il "Motore di Ricerca" di WayPoint (Filtri, Paginazione, Sicurezza).
    """

    @classmethod
    def setUpTestData(cls):
        """
        TEORIA — setUpTestData viene eseguito UNA
        SOLA VOLTA per l'intera classe di test (non prima di ogni singolo
        metodo test_*).

        Prepariamo qui uno scenario con 3 escursioni pensate apposta per
        coprire i casi limite dei filtri: una con posti liberi, una sold-out,
        una non ancora approvata (che NON deve mai comparire nel catalogo
        pubblico).
        """
        # 1. Creiamo un utente guida fittizio per soddisfare il database
        cls.guida = User.objects.create_user(username='guida_master', password='123')

        # 2. Creiamo ESCURSIONE 1 (Approvata, Difficoltà T, con POSTI DISPONIBILI)
        cls.esc_facile = Escursione.objects.create(
            titolo="Passeggiata nel Bosco Magico",
            descrizione="Un percorso tranquillo e rilassante tra gli alberi.",
            difficolta="T",
            dislivello=150,
            approvata=True,
            guida=cls.guida
        )
        Uscita.objects.create(
            escursione=cls.esc_facile,
            data_ritrovo=timezone.now() + timedelta(days=10),
            posti_totali=20,
            posti_occupati=5  # <--- 15 POSTI LIBERI
        )

        # 3. Creiamo ESCURSIONE 2 (Approvata, Difficoltà EE, SOLD OUT)
        cls.esc_difficile = Escursione.objects.create(
            titolo="Scalata del Monte Fato",
            descrizione="Solo per veri esperti di arrampicata.",
            difficolta="EE",
            dislivello=1200,
            approvata=True,
            guida=cls.guida
        )
        Uscita.objects.create(
            escursione=cls.esc_difficile,
            data_ritrovo=timezone.now() + timedelta(days=5),
            posti_totali=5,
            posti_occupati=5  # <--- SOLD OUT (Posti totali == Posti occupati)
        )

        # 4. Creiamo ESCURSIONE 3 (NON APPROVATA) - Questa non deve MAI comparire
        cls.esc_nascosta = Escursione.objects.create(
            titolo="Itinerario Segreto",
            descrizione="Non ancora validato dagli admin.",
            difficolta="E",
            dislivello=500,
            approvata=False,  # <--- FONDAMENTALE
            guida=cls.guida
        )

    def test_home_page_carica_e_nasconde_non_approvate(self):
        """
        COSA TESTA: il filtro di sicurezza più importante di tutta l'app,
        filter(approvata=True) in home(). Non è un dettaglio estetico: è il
        meccanismo che impedisce a un'escursione in attesa di moderazione di
        finire visibile al pubblico prima che un Amministratore l'abbia
        validata.
        Verifica anche lo status 200 e che il template corretto sia stato usato.
        """
        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/home.html')

        # Nel context ci devono essere le 2 approvate, ma NON la terza
        escursioni_mostrate = response.context['escursioni']
        self.assertEqual(len(escursioni_mostrate), 2)
        self.assertNotIn(self.esc_nascosta, escursioni_mostrate)

    def test_filtro_ricerca_testuale(self):
        """
        COSA TESTA: la ricerca combinata Q(titolo__icontains=...) |
        Q(descrizione__icontains=...) in home(). Il punto delicato da
        verificare non è solo "una parola nel titolo funziona", ma che
        l'OR tra i due campi funzioni davvero: cerchiamo una parola presente
        SOLO nel titolo di un'escursione ("bosco") e una presente SOLO nella
        descrizione di un'altra ("arrampicata"), per essere sicuri che il
        filtro non stia in realtà cercando solo in uno dei due campi.
        """
        # Cerchiamo la parola "bosco" (che è nel titolo della prima escursione)
        response = self.client.get(reverse('core:home'), {'q': 'bosco'})
        escursioni_mostrate = response.context['escursioni']

        self.assertEqual(len(escursioni_mostrate), 1)
        self.assertIn(self.esc_facile, escursioni_mostrate)

        # Cerchiamo la parola "arrampicata" (che è nella descrizione della seconda)
        response_desc = self.client.get(reverse('core:home'), {'q': 'arrampicata'})
        self.assertIn(self.esc_difficile, response_desc.context['escursioni'])

    def test_filtro_difficolta(self):
        """
        COSA TESTA: il filtro a scelta singola sulla difficoltà, con un
        valore VALIDO tra quelli ammessi da SCELTE_DIFFICOLTA ('EE').
        Verifica solo che un valore corretto
        restituisce esattamente l'escursione attesa.
        """
        response = self.client.get(reverse('core:home'), {'difficolta': 'EE'})
        escursioni_mostrate = response.context['escursioni']

        self.assertEqual(len(escursioni_mostrate), 1)
        self.assertEqual(escursioni_mostrate[0].titolo, "Scalata del Monte Fato")

    def test_filtro_difficolta_valore_non_valido_ignorato(self):
        """
        COSA TESTA (NUOVO): la whitelist anti-injection in home() —
        difficolta_valide con un valore che NON fa parte dei choices
        ammessi (qui simuliamo un tentativo di manipolazione dell'URL, tipo
        ?difficolta=HACK). Il comportamento corretto e atteso è che il
        filtro venga ignorato silenziosamente (nessun errore, nessun crash),
        mostrando tutte le escursioni come se il parametro non fosse stato
        passato affatto — mai un errore 500, e soprattutto mai una query
        costruita con quel valore non previsto.
        """
        response = self.client.get(reverse('core:home'), {'difficolta': 'HACK'})

        self.assertEqual(response.status_code, 200)
        # Nessun filtro applicato: tutte e 2 le escursioni approvate restano visibili
        self.assertEqual(len(response.context['escursioni']), 2)

    def test_filtro_dislivello_testo_non_crasha(self):
        """
        COSA TESTA (NUOVO): la conversione sicura in home() —
        if dislivello_max.isdigit(): ... int(dislivello_max) — con un
        valore NON numerico (?dislivello=abc). Senza il controllo
        .isdigit() prima della conversione, int('abc') solleverebbe un
        ValueError non gestito, che Django tradurrebbe in un errore 500
        (Internal Server Error) mostrato all'utente.
        Questo test verifica che, invece, la richiesta
        vada comunque a buon fine (200) ignorando semplicemente il filtro
        non valido.
        """
        response = self.client.get(reverse('core:home'), {'dislivello': 'abc'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['escursioni']), 2)

    def test_filtro_solo_disponibili(self):
        """
        COSA TESTA: la logica con espressioni F, filter(uscite_programmate__
        posti_occupati__lt=F('uscite_programmate__posti_totali')) in home().
        A differenza di un confronto con un valore statico, questo confronta
        due COLONNE della stessa riga direttamente in SQL. Il dataset di
        setUpTestData è costruito apposta con un'uscita sold-out (posti_
        occupati == posti_totali) e una con posti liberi, proprio per
        verificare che il filtro escluda correttamente la prima.
        """
        response = self.client.get(reverse('core:home'), {'solo_disponibili': 'true'})
        escursioni_mostrate = response.context['escursioni']

        # L'escursione "Scalata del Monte Fato" è sold out, quindi NON deve esserci
        self.assertEqual(len(escursioni_mostrate), 1)
        self.assertEqual(escursioni_mostrate[0], self.esc_facile)


