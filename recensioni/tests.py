from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from datetime import timedelta

# Importiamo i modelli dalle altre app (assicurati che i nomi corrispondano!)
from escursione.models import Escursione, Uscita, Prenotazione
from recensioni.models import Recensione


class RecensioniBaseTestCase(TestCase):
    """
    Classe base per la preparazione dei dati fittizi per testare le recensioni.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Creazione Gruppi
        cls.gruppo_guide = Group.objects.create(name='Guide')
        cls.gruppo_escursionisti = Group.objects.create(name='Escursionisti')

        # 2. Utenti (Guida e due Escursionisti)
        cls.guida = User.objects.create_user(username='guida_test', password='password123')
        cls.guida.groups.add(cls.gruppo_guide)

        cls.escursionista_passato = User.objects.create_user(username='trekker_passato', password='password123')
        cls.escursionista_passato.groups.add(cls.gruppo_escursionisti)

        cls.escursionista_futuro = User.objects.create_user(username='trekker_futuro', password='password123')
        cls.escursionista_futuro.groups.add(cls.gruppo_escursionisti)

        # 3. Escursione Base
        cls.escursione = Escursione.objects.create(
            titolo="Sentiero delle Cascate",
            difficolta="T",
            dislivello=300,
            approvata=True,
            guida=cls.guida
        )

        # 4. Due uscite: una già avvenuta nel passato, una che avverrà in futuro
        cls.uscita_conclusa = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() - timedelta(days=2),  # Due giorni fa
            posti_totali=10
        )
        cls.uscita_futura = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() + timedelta(days=5),  # Tra cinque giorni
            posti_totali=10
        )

        # 5. Iscriviamo gli escursionisti alle rispettive uscite
        Prenotazione.objects.create(
            escursionista=cls.escursionista_passato,
            uscita=cls.uscita_conclusa,
            stato='confermata'
        )
        Prenotazione.objects.create(
            escursionista=cls.escursionista_futuro,
            uscita=cls.uscita_futura,
            stato='confermata'
        )

        # 6. Creiamo una recensione base su cui la guida potrà rispondere
        cls.recensione_base = Recensione.objects.create(
            escursione=cls.escursione,
            autore=cls.escursionista_passato,
            voto=4,
            testo="Bellissimo panorama!"
        )


class CreaRecensioneViewTests(RecensioniBaseTestCase):
    def test_accesso_solo_a_escursionisti(self):
        """Verifica che una Guida non possa lasciare recensioni."""
        self.client.login(username='guida_test', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        response = self.client.post(url, {'voto': 5, 'testo': 'Mi auto-voto!'})

        # Ci aspettiamo un redirect (302) alla pagina di dettaglio a causa del blocco
        self.assertEqual(response.status_code, 302)
        # Assicuriamoci che la recensione fasulla non sia stata creata
        self.assertEqual(Recensione.objects.count(), 1)  # C'è solo quella creata nel setUp

    def test_blocco_recensione_per_evento_non_concluso(self):
        """Verifica che chi si prenota a un evento futuro non possa recensirlo in anticipo."""
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        response = self.client.post(url, {'voto': 3, 'testo': 'Non so, non ci sono ancora andato.'})

        # Deve essere bloccato dalla view
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Recensione.objects.count(), 1)

    def test_creazione_recensione_successo(self):
        """Verifica l'inserimento corretto per chi ha completato l'escursione."""
        # Creiamo un nuovo escursionista al volo e facciamogli fare l'uscita passata
        nuovo_trekker = User.objects.create_user(username='nuovo_trekker', password='password123')
        nuovo_trekker.groups.add(self.gruppo_escursionisti)
        Prenotazione.objects.create(
            escursionista=nuovo_trekker, uscita=self.uscita_conclusa, stato='confermata'
        )

        self.client.login(username='nuovo_trekker', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        response = self.client.post(url, {'voto': 5, 'testo': 'Esperienza meravigliosa!'})

        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))
        # Ora le recensioni totali nel DB devono essere 2!
        self.assertEqual(Recensione.objects.count(), 2)
        self.assertTrue(Recensione.objects.filter(autore=nuovo_trekker, voto=5).exists())


class RispondiRecensioneViewTests(RecensioniBaseTestCase):
    def test_solo_guida_organizzatrice_puo_rispondere(self):
        """Verifica il blocco di sicurezza: un escursionista o una guida estranea non può rispondere."""
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('rispondi_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.post(url, {'risposta_guida': 'Risposta hackerata!'})
        self.assertEqual(response.status_code, 302)

        # Ricarichiamo dal DB: la risposta deve essere vuota
        self.recensione_base.refresh_from_db()
        self.assertEqual(self.recensione_base.risposta_guida, '')

    def test_guida_puo_rispondere_successo(self):
        """Verifica che la guida corretta possa pubblicare una replica ufficiale."""
        self.client.login(username='guida_test', password='password123')
        url = reverse('rispondi_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.post(url, {'risposta_guida': 'Grazie mille per aver partecipato!'})
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))

        self.recensione_base.refresh_from_db()
        self.assertEqual(self.recensione_base.risposta_guida, 'Grazie mille per aver partecipato!')


class SegnalaRecensioneViewTests(RecensioniBaseTestCase):
    def test_segnalazione_escursionista_funziona(self):
        """Verifica che il flag 'segnalata' diventi True se un escursionista effettua la segnalazione."""
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('segnala_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.post(url)  # Oppure GET, dipendentemente da come l'hai impostata nell'HTML
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))

        self.recensione_base.refresh_from_db()
        self.assertTrue(self.recensione_base.segnalata)

    def test_segnalazione_guida_fallisce(self):
        """Verifica che una Guida non possa usare questo strumento (riservato agli escursionisti)."""
        self.client.login(username='guida_test', password='password123')
        url = reverse('segnala_recensione', kwargs={'recensione_id': self.recensione_base.id})

        self.client.get(url)
        self.recensione_base.refresh_from_db()

        # Non deve essere stata segnalata (impostazione di default)
        self.assertFalse(self.recensione_base.segnalata)