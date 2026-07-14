# =============================================================================
# TEST DELL'APP "recensioni" — CREAZIONE, RISPOSTA, SEGNALAZIONE
# =============================================================================

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
        """
        COSA TESTA: il controllo di ruolo in crea_recensione — solo chi
        appartiene al gruppo Escursionisti può lasciare una recensione. Una
        Guida (anche se organizzatrice di un'ALTRA escursione) non deve
        poter recensire nulla. Verifichiamo sia il redirect (302, non un
        errore secco) sia, soprattutto, che il conteggio delle recensioni
        nel database non sia salito: l'unica recensione presente resta
        quella creata in setUpTestData.
        """
        self.client.login(username='guida_test', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        response = self.client.post(url, {'voto': 5, 'testo': 'Mi auto-voto!'})

        # Ci aspettiamo un redirect (302) alla pagina di dettaglio a causa del blocco
        self.assertEqual(response.status_code, 302)
        # Assicuriamoci che la recensione fasulla non sia stata creata
        self.assertEqual(Recensione.objects.count(), 1)  # C'è solo quella creata nel setUp

    def test_blocco_recensione_per_evento_non_concluso(self):
        """
        COSA TESTA: il controllo "ha_partecipato" in crea_recensione, nella
        sua parte temporale (uscita__data_ritrovo__lt=timezone.now()).
        trekker_futuro è iscritto (prenotazione CONFERMATA) a un'uscita che
        deve ancora avvenire: non basta essere iscritti, l'escursione deve
        essersi già CONCLUSA. Recensire in anticipo un'esperienza non ancora
        vissuta non deve essere permesso.
        """
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        response = self.client.post(url, {'voto': 3, 'testo': 'Non so, non ci sono ancora andato.'})

        # Deve essere bloccato dalla view
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Recensione.objects.count(), 1)

    def test_creazione_recensione_successo(self):
        """
        COSA TESTA: il percorso "felice" completo — un escursionista che ha
        partecipato (prenotazione confermata su un'uscita passata)
        riesce a lasciare una recensione. Verifica sia il redirect sia,
        soprattutto, che la riga sia stata scritta nel database con
        l'autore e il voto corretti.
        """
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
        # Ora le recensioni totali nel DB devono essere 2
        self.assertEqual(Recensione.objects.count(), 2)
        self.assertTrue(Recensione.objects.filter(autore=nuovo_trekker, voto=5).exists())

    def test_doppia_recensione_stesso_utente_rifiutata(self):
        """
        COSA TESTA: il vincolo unique_together (escursione, autore)
        del modello Recensione, e la sua gestione applicativa in
        crea_recensione tramite try/except IntegrityError. escursionista_
        passato ha GIÀ una recensione su questa escursione (creata in
        setUpTestData): un secondo tentativo di recensire la STESSA
        escursione deve fallire in modo "controllato" (redirect con
        un messaggio, status 302),
        """
        self.client.login(username='trekker_passato', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        response = self.client.post(url, {'voto': 2, 'testo': 'Seconda recensione, dovrebbe fallire.'})

        self.assertEqual(response.status_code, 302)  # redirect gentile, non un crash 500
        # Deve restare solo la prima recensione: nessun duplicato creato
        self.assertEqual(Recensione.objects.filter(autore=self.escursionista_passato).count(), 1)


class RispondiRecensioneViewTests(RecensioniBaseTestCase):
    def test_solo_guida_organizzatrice_puo_rispondere(self):
        """
        COSA TESTA: il controllo di ownership in rispondi_recensione
        (request.user != recensione.escursione.guida). trekker_futuro non è
        né l'autore della recensione né la guida che ha organizzato
        l'escursione: non deve poter scrivere una risposta ufficiale a nome
        della guida. Verifichiamo sia il redirect sia, con
        refresh_from_db(), che il campo risposta_guida sia rimasto VUOTO
        (non solo che la richiesta non abbia avuto "successo" secondo lo
        status code).
        """
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('rispondi_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.post(url, {'risposta_guida': 'Risposta hackerata!'})
        self.assertEqual(response.status_code, 302)

        # Ricarichiamo dal DB: la risposta deve essere vuota
        self.recensione_base.refresh_from_db()
        self.assertEqual(self.recensione_base.risposta_guida, '')

    def test_guida_puo_rispondere_successo(self):
        """
        COSA TESTA: il percorso "felice" — la guida CORRETTA (proprietaria
        dell'escursione recensita) riesce a pubblicare una replica
        ufficiale, e il testo viene davvero salvato sul database.
        """
        self.client.login(username='guida_test', password='password123')
        url = reverse('rispondi_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.post(url, {'risposta_guida': 'Grazie mille per aver partecipato!'})
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))

        self.recensione_base.refresh_from_db()
        self.assertEqual(self.recensione_base.risposta_guida, 'Grazie mille per aver partecipato!')


class SegnalaRecensioneViewTests(RecensioniBaseTestCase):
    def test_segnalazione_escursionista_funziona(self):
        """
        COSA TESTA: il percorso "felice" della segnalazione — un
        Escursionista autenticato marca una recensione come sospetta
        (segnalata=True), e la vista reindirizza al dettaglio
        dell'escursione.
        """
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('segnala_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.post(url)
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))

        self.recensione_base.refresh_from_db()
        self.assertTrue(self.recensione_base.segnalata)

    def test_segnalazione_guida_fallisce(self):
        """
        COSA TESTA: il controllo di ruolo in segnala_recensione — una Guida
        non è nel gruppo Escursionisti e non deve poter usare questo
        strumento.

        """
        self.client.login(username='guida_test', password='password123')
        url = reverse('segnala_recensione', kwargs={'recensione_id': self.recensione_base.id})

        self.client.post(url)
        self.recensione_base.refresh_from_db()

        # Non deve essere stata segnalata (impostazione di default)
        self.assertFalse(self.recensione_base.segnalata)

    def test_segnalazione_via_get_bloccata(self):
        """
        COSA TESTA: verifica esplicita e diretta, @require_POST deve rifiutare
        una richiesta GET con status 405 Method Not Allowed, PRIMA di
        eseguire qualunque logica interna (inclusa quella di ruolo).
        """
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('segnala_recensione', kwargs={'recensione_id': self.recensione_base.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)
        # E, di conseguenza, nessun effetto collaterale sul database
        self.recensione_base.refresh_from_db()
        self.assertFalse(self.recensione_base.segnalata)
