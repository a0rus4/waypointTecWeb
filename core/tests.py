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
        """Verifica lo status 200 e il filtro base di sicurezza (approvata=True)."""
        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/home.html')

        # Nel context ci devono essere le 2 approvate, ma NON la terza
        escursioni_mostrate = response.context['escursioni']
        self.assertEqual(len(escursioni_mostrate), 2)
        self.assertNotIn(self.esc_nascosta, escursioni_mostrate)

    def test_filtro_ricerca_testuale(self):
        """Verifica che l'Oggetto Q cerchi correttamente nel Titolo e Descrizione."""
        # Cerchiamo la parola "bosco" (che è nel titolo della prima escursione)
        response = self.client.get(reverse('core:home'), {'q': 'bosco'})
        escursioni_mostrate = response.context['escursioni']

        self.assertEqual(len(escursioni_mostrate), 1)
        self.assertIn(self.esc_facile, escursioni_mostrate)

        # Cerchiamo la parola "arrampicata" (che è nella descrizione della seconda)
        response_desc = self.client.get(reverse('core:home'), {'q': 'arrampicata'})
        self.assertIn(self.esc_difficile, response_desc.context['escursioni'])

    def test_filtro_difficolta(self):
        """Verifica il filtro a tendina/bottoni per la difficoltà."""
        response = self.client.get(reverse('core:home'), {'difficolta': 'EE'})
        escursioni_mostrate = response.context['escursioni']

        self.assertEqual(len(escursioni_mostrate), 1)
        self.assertEqual(escursioni_mostrate[0].titolo, "Scalata del Monte Fato")

    def test_filtro_solo_disponibili(self):
        """Verifica la logica avanzata dell'espressione F (Posti occupati < Totali)."""
        response = self.client.get(reverse('core:home'), {'solo_disponibili': 'true'})
        escursioni_mostrate = response.context['escursioni']

        # L'escursione "Scalata del Monte Fato" è sold out, quindi NON deve esserci
        self.assertEqual(len(escursioni_mostrate), 1)
        self.assertEqual(escursioni_mostrate[0], self.esc_facile)

    def test_gestione_paginazione_errore_testo(self):
        """Verifica la robustezza del Paginator se un utente smanetta con l'URL."""
        # Un utente scrive ?page=pippo invece di un numero
        response = self.client.get(reverse('core:home'), {'page': 'pippo test test'})

        # Il server non deve crashare col 500, ma tornare gentilmente alla pagina 1
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['escursioni'].number, 1)