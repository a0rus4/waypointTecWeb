from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from datetime import timedelta

from .models import Escursione, Uscita, Prenotazione


class EscursioneBaseTestCase(TestCase):
    """
    Classe base che prepara il database fantasma con i ruoli, gli utenti
    e i dati minimi necessari per tutti i test successivi.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Creazione dei Gruppi
        cls.gruppo_guide = Group.objects.create(name='Guide')
        cls.gruppo_escursionisti = Group.objects.create(name='Escursionisti')

        # 2. Creazione Utenti di Test
        cls.guida_1 = User.objects.create_user(username='guida_mario', password='password123')
        cls.guida_1.groups.add(cls.gruppo_guide)

        cls.guida_2 = User.objects.create_user(username='guida_luigi', password='password123')
        cls.guida_2.groups.add(cls.gruppo_guide)

        cls.escursionista = User.objects.create_user(username='trekker_luca', password='password123')
        cls.escursionista.groups.add(cls.gruppo_escursionisti)

        # 3. Creazione di un'Escursione Base e di un'Uscita futura
        cls.escursione = Escursione.objects.create(
            titolo="Sentiero degli Dei",
            descrizione="Un percorso bellissimo.",
            difficolta="E",
            dislivello=500,
            approvata=True,
            guida=cls.guida_1  # Proprietario: guida_mario
        )

        cls.uscita = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() + timedelta(days=5),
            posti_totali=2,
            posti_occupati=0
        )


class VistePubblicheTests(EscursioneBaseTestCase):
    def test_dettaglio_escursione_carica_correttamente(self):
        """Verifica che la pagina di dettaglio sia accessibile a tutti (status 200)."""
        url = reverse('dettaglio_escursione', kwargs={'pk': self.escursione.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'escursione/escursione_detail.html')
        self.assertContains(response, "Sentiero degli Dei")


class GestioneLatiGuidaTests(EscursioneBaseTestCase):
    def test_guida_puo_creare_uscita_per_propria_escursione(self):
        """Verifica che la guida proprietaria possa aggiungere date al suo itinerario."""
        self.client.login(username='guida_mario', password='password123')
        url = reverse('aggiungi_data_uscita', kwargs={'escursione_id': self.escursione.id})

        # Test di caricamento della pagina form
        response_get = self.client.get(url)
        self.assertEqual(response_get.status_code, 200)

    def test_guida_NON_puo_aggiungere_date_a_escursioni_altrui(self):
        """Verifica il vincolo di sicurezza: una guida non può modificare i sentieri di altre guide."""
        # Facciamo login con la Guida 2 (che non è proprietaria del 'Sentiero degli Dei')
        self.client.login(username='guida_luigi', password='password123')
        url = reverse('aggiungi_data_uscita', kwargs={'escursione_id': self.escursione.id})

        form_data = {
            'data_ritrovo': timezone.now() + timedelta(days=10),
            'posti_totali': 15
        }
        response = self.client.post(url, form_data)

        # Deve generare un 403 Forbidden (PermissionDenied) lanciato dalla vista
        self.assertEqual(response.status_code, 403)

    def test_solo_proprietario_puo_eliminare_escursione(self):
        """Verifica la sicurezza sull'eliminazione: solo l'autore può distruggere il record."""
        self.client.login(username='guida_luigi', password='password123')  # Guida sbagliata
        url = reverse('elimina_escursione', kwargs={'escursione_id': self.escursione.id})

        self.client.post(url)

        # L'escursione deve ancora esistere nel database!
        self.assertTrue(Escursione.objects.filter(id=self.escursione.id).exists())


class PrenotazioneBusinessLogicTests(EscursioneBaseTestCase):
    def setUp(self):
        self.url_prenota = reverse('prenota_uscita', kwargs={'uscita_id': self.uscita.id})

    def test_prenotazione_confermata_successo(self):
        """Verifica che l'escursionista prenda il posto se c'è disponibilità."""
        self.client.login(username='trekker_luca', password='password123')

        # Invia richiesta POST per prenotare
        response = self.client.post(self.url_prenota)

        # Verifica Redirect
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))

        # Verifica Database
        self.uscita.refresh_from_db()
        self.assertEqual(self.uscita.posti_occupati, 1)  # I posti occupati sono saliti a 1

        prenotazione = Prenotazione.objects.get(escursionista=self.escursionista, uscita=self.uscita)
        self.assertEqual(prenotazione.stato, 'confermata')

    def test_logica_lista_attesa(self):
        """Verifica che superato il limite di posti, l'utente finisca in coda (attesa)."""
        # Occupiamo tutti i posti fittiziamente (i posti totali erano 2 nel setUp)
        self.uscita.posti_occupati = 2
        self.uscita.save()

        self.client.login(username='trekker_luca', password='password123')
        self.client.post(self.url_prenota)

        # Ricarichiamo l'uscita: i posti occupati non devono essere saliti oltre il totale (2)
        self.uscita.refresh_from_db()
        self.assertEqual(self.uscita.posti_occupati, 2)

        # L'utente deve avere una prenotazione ma in stato 'attesa'
        prenotazione = Prenotazione.objects.get(escursionista=self.escursionista, uscita=self.uscita)
        self.assertEqual(prenotazione.stato, 'attesa')

    def test_guide_non_possono_prenotare(self):
        """Verifica che chi non è nel gruppo Escursionisti venga respinto."""
        self.client.login(username='guida_mario', password='password123')
        self.client.post(self.url_prenota)

        # Non deve essere stata creata alcuna prenotazione
        self.assertFalse(Prenotazione.objects.exists())