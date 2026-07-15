# =============================================================================
# TEST DELL'APP "core" — MOTORE DI RICERCA E HOMEPAGE PUBBLICA
# =============================================================================
# STRATEGIA: la logica interessante di quest'app NON sta nei modelli (che qui
# hanno comportamento minimo), ma dentro core/views.py: filtri combinabili,
# whitelist di sicurezza e ordinamento. Per questo NON testiamo "il modello si
# salva" (sarebbe banale e testerebbe Django, non il nostro codice); testiamo
# invece la VIEW tramite self.client (il client di test di Django, che fa vere
# richieste HTTP contro la view senza aprire un browser) e ispezioniamo
# response.context, cioè i dati realmente passati al template DOPO i filtri.
#
# Dei 6 test originali ne restano 4, scelti perché ognuno verifica un
# comportamento distinto e non ovvio del motore di ricerca (sicurezza,
# combinazione OR, difesa da input ostile, confronto colonna-vs-colonna in SQL).
# =============================================================================
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User

from escursione.models import Escursione, Uscita


class CoreHomeViewTests(TestCase):
    """Test del motore di ricerca di WayPoint (sicurezza, filtri, robustezza)."""

    # Decoratore che istruisce il test runner di eseguire questo metodo una sola volta per la classe.
    @classmethod
    def setUpTestData(cls):
        """
        setUpTestData gira UNA SOLA VOLTA per l'intera classe (non prima di ogni
        test), dentro una transazione che viene annullata alla fine: ogni test
        parte quindi dallo stesso stato pulito senza ricrearlo ogni volta.

        Costruiamo 3 escursioni pensate per coprire i casi limite dei filtri:
          - una APPROVATA, difficoltà T, con posti liberi;
          - una APPROVATA, difficoltà EE, SOLD-OUT (posti_occupati == totali);
          - una NON APPROVATA, che non deve MAI comparire nel catalogo pubblico.
        """
        cls.guida = User.objects.create_user(username='guida_master', password='123')

        # Escursione 1: approvata, T, con 15 posti liberi (20 totali - 5 occupati)
        cls.esc_facile = Escursione.objects.create(
            titolo="Passeggiata nel Bosco Magico",
            descrizione="Un percorso tranquillo e rilassante tra gli alberi.",
            difficolta="T", dislivello=150, approvata=True, guida=cls.guida,
        )
        Uscita.objects.create(
            escursione=cls.esc_facile,
            data_ritrovo=timezone.now() + timedelta(days=10),
            posti_totali=20, posti_occupati=5,
        )

        # Escursione 2: approvata, EE, sold-out (posti occupati == totali)
        cls.esc_difficile = Escursione.objects.create(
            titolo="Scalata del Monte Fato",
            descrizione="Solo per veri esperti di arrampicata.",
            difficolta="EE", dislivello=1200, approvata=True, guida=cls.guida,
        )
        Uscita.objects.create(
            escursione=cls.esc_difficile,
            data_ritrovo=timezone.now() + timedelta(days=5),
            posti_totali=5, posti_occupati=5,
        )

        # Escursione 3: NON approvata -> deve restare invisibile al pubblico
        cls.esc_nascosta = Escursione.objects.create(
            titolo="Itinerario Segreto",
            descrizione="Non ancora validato dagli admin.",
            difficolta="E", dislivello=500, approvata=False, guida=cls.guida,
        )

    def test_home_nasconde_escursioni_non_approvate(self):
        """
        SICUREZZA / MODERAZIONE. Verifica il filtro filter(approvata=True) in
        home(): è ciò che impedisce a un'escursione in attesa di validazione di
        finire nel catalogo pubblico. Controlliamo che la home risponda 200, usi
        il template giusto e che nel context arrivino SOLO le 2 approvate, mai la
        terza.
        """
        # Il test client esegue una chiamata GET fittizia contro il server di test risolvendo l'URL 'core:home'.
        response = self.client.get(reverse('core:home'))

        # Verifica che l'architettura risponda correttamente senza generare eccezioni 500 o permessi negati.
        self.assertEqual(response.status_code, 200)
        # Verifica l'integrità del dispatcher: la view deve fare il render di questo esatto template HTML.
        self.assertTemplateUsed(response, 'core/home.html')
        # Intercetta il QuerySet restituito dalla logica di business e assegnato al context del template.
        escursioni_mostrate = response.context['escursioni']
        # Asserisce che la lunghezza dei record estratti sia esattamente 2 (escludendo il terzo non approvato).
        self.assertEqual(len(escursioni_mostrate), 2)
        # Asserisce qualitativamente che l'istanza esc_nascosta non sia presente nel payload in uscita.
        self.assertNotIn(self.esc_nascosta, escursioni_mostrate)

    def test_ricerca_testuale_cerca_in_titolo_OPPURE_descrizione(self):
        """
        La ricerca usa Q(titolo__icontains=q) |
        Q(descrizione__icontains=q). Il punto delicato non è "una parola nel
        titolo funziona", ma che l'OR interroghi entrambi i campi: per
        provarlo cerchiamo una parola presente SOLO in un titolo ("bosco") e una
        presente SOLO in una descrizione ("arrampicata"). Se il filtro guardasse
        un solo campo, una delle due ricerche fallirebbe.
        """
        # Effettua una GET iniettando la stringa ?q=bosco per testare il matching sul campo titolo.
        r_titolo = self.client.get(reverse('core:home'), {'q': 'bosco'})
        # Verifica di aver ottenuto un solo risultato.
        self.assertEqual(len(r_titolo.context['escursioni']), 1)
        # Verifica che il risultato ottenuto sia esattamente esc_facile, che contiene "bosco" nel titolo.
        self.assertIn(self.esc_facile, r_titolo.context['escursioni'])

        # Effettua una GET indipendente iniettando ?q=arrampicata per testare il matching sul campo descrizione.
        r_descr = self.client.get(reverse('core:home'), {'q': 'arrampicata'})
        # Verifica che l'escursione trovata sia esc_difficile, provando che la clausola OR dell'ORM funziona a dovere.
        self.assertIn(self.esc_difficile, r_descr.context['escursioni'])

    def test_difficolta_con_valore_ostile_viene_ignorata(self):
        """
        DIFESA DA INPUT MANIPOLATO. home() confronta il valore
        ricevuto con l'insieme dei choices ammessi dal modello: un valore
        arbitrario iniettato nell'URL (?difficolta=HACK) NON deve costruire una
        query con quel valore, ma essere ignorato in silenzio. Ci aspettiamo 200
        (nessun 500) e tutte e 2 le approvate visibili, come se il parametro non
        fosse stato passato.
        """
        # Invia intenzionalmente una query string malevola o estranea alle constraint previste (?difficolta=HACK).
        response = self.client.get(reverse('core:home'), {'difficolta': 'HACK'})

        # Assicura che la view scarti i dati sporchi catturandoli correttamente, senza causare crash dell'app.
        self.assertEqual(response.status_code, 200)
        # Assicura che, avendo scartato l'input ostile, il sistema applichi la logica di default (mostra le 2 valide).
        self.assertEqual(len(response.context['escursioni']), 2)
    def test_filtro_solo_disponibili_esclude_sold_out(self):
        """
        CONFRONTO COLONNA-vs-COLONNA IN SQL (F expression). Il filtro usa
        filter(posti_occupati__lt=F('posti_totali')): confronta due colonne
        della STESSA riga direttamente nel database, non un valore fisso. Il
        dataset ha apposta un'uscita sold-out e una con posti liberi: il test
        prova che solo la seconda superi il filtro.
        """
        # Esegue la GET iniettando la flag per attivare il filtraggio su query complesse tramite F objects di Django.
        response = self.client.get(reverse('core:home'), {'solo_disponibili': 'true'})
        # Estrae i dati post-filtro passati al frontend.
        escursioni_mostrate = response.context['escursioni']

        # Verifica che la condizione di "sold-out" simulata nel db di test abbia escluso un elemento dal totale di 2.
        self.assertEqual(len(escursioni_mostrate), 1)
        # Verifica inequivocabilmente che il record scartato sia il sold-out e l'unico ritornato sia quello disponibile.
        self.assertEqual(escursioni_mostrate[0], self.esc_facile)
