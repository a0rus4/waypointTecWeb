# =============================================================================
# TEST DELL'APP "recensioni" — CREAZIONE FEEDBACK E RISPOSTA DELLA GUIDA
# =============================================================================
# Le recensioni alimentano il rating dei sentieri e la reputazione delle guide,
# quindi le regole su CHI può recensire, QUANDO e QUANTE volte sono il cuore
# dell'app. I 4 test rimasti (su 9) coprono: il percorso valido, la regola
# temporale (recensire solo dopo aver partecipato a un'uscita conclusa), il
# vincolo di unicità, e l'ownership sulla risposta ufficiale della guida.
# =============================================================================

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from datetime import timedelta

from escursione.models import Escursione, Uscita, Prenotazione
from recensioni.models import Recensione


class RecensioniBaseTestCase(TestCase):
    """
    Prepara: i gruppi-ruolo; una guida; due escursionisti (uno iscritto a
    un'uscita GIÀ CONCLUSA, uno a un'uscita FUTURA); e una recensione già
    esistente su cui testare risposta e vincolo di unicità.
    """

    @classmethod
    def setUpTestData(cls):
        cls.gruppo_guide = Group.objects.create(name='Guide')
        cls.gruppo_escursionisti = Group.objects.create(name='Escursionisti')

        cls.guida = User.objects.create_user(username='guida_test', password='password123')
        cls.guida.groups.add(cls.gruppo_guide)

        # Uno ha partecipato (uscita passata) -> potrà recensire;
        # l'altro è iscritto a un'uscita futura -> NON deve poter recensire.
        cls.escursionista_passato = User.objects.create_user(username='trekker_passato', password='password123')
        cls.escursionista_passato.groups.add(cls.gruppo_escursionisti)
        cls.escursionista_futuro = User.objects.create_user(username='trekker_futuro', password='password123')
        cls.escursionista_futuro.groups.add(cls.gruppo_escursionisti)

        cls.escursione = Escursione.objects.create(
            titolo="Sentiero delle Cascate", difficolta="T",
            dislivello=300, approvata=True, guida=cls.guida,
        )
        cls.uscita_conclusa = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() - timedelta(days=2),  # già avvenuta
            posti_totali=10,
        )
        cls.uscita_futura = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() + timedelta(days=5),  # deve ancora avvenire
            posti_totali=10,
        )
        Prenotazione.objects.create(
            escursionista=cls.escursionista_passato, uscita=cls.uscita_conclusa, stato='confermata',
        )
        Prenotazione.objects.create(
            escursionista=cls.escursionista_futuro, uscita=cls.uscita_futura, stato='confermata',
        )

        # Recensione preesistente dell'escursionista "passato": serve ai test di
        # risposta della guida e di doppia-recensione.
        cls.recensione_base = Recensione.objects.create(
            escursione=cls.escursione, autore=cls.escursionista_passato,
            voto=4, testo="Bellissimo panorama!",
        )


class CreaRecensioneViewTests(RecensioniBaseTestCase):
    def test_partecipante_a_uscita_conclusa_puo_recensire(self):
        """
        PERCORSO FELICE. Un escursionista con prenotazione confermata su
        un'uscita GIÀ CONCLUSA lascia una recensione valida. Creiamo un nuovo
        trekker apposta e lo iscriviamo all'uscita passata, poi verifichiamo sia
        il redirect sia che la riga sia stata SCRITTA nel database con autore e
        voto corretti (le recensioni passano da 1 a 2).
        """
        nuovo_trekker = User.objects.create_user(username='nuovo_trekker', password='password123')
        nuovo_trekker.groups.add(self.gruppo_escursionisti)
        Prenotazione.objects.create(
            escursionista=nuovo_trekker, uscita=self.uscita_conclusa, stato='confermata',
        )

        self.client.login(username='nuovo_trekker', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})
        response = self.client.post(url, {'voto': 5, 'testo': 'Esperienza meravigliosa!'})

        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))
        self.assertEqual(Recensione.objects.count(), 2)
        self.assertTrue(Recensione.objects.filter(autore=nuovo_trekker, voto=5).exists())

    def test_non_si_puo_recensire_un_evento_non_ancora_concluso(self):
        """
        REGOLA TEMPORALE. Non basta essere iscritti: l'esperienza deve essere
        già stata vissuta (uscita__data_ritrovo < adesso). trekker_futuro è
        iscritto SOLO a un'uscita futura, quindi il suo tentativo di recensire
        in anticipo va bloccato: ci aspettiamo un redirect gentile (302) e
        NESSUNA nuova recensione nel database (resta solo quella del setUp).
        """
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})
        response = self.client.post(url, {'voto': 3, 'testo': 'Non ci sono ancora andato.'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Recensione.objects.count(), 1)

    def test_non_si_puo_recensire_due_volte_la_stessa_escursione(self):
        """
        VINCOLO DI UNICITÀ. unique_together (escursione, autore) sul modello,
        gestito in crea_recensione con try/except IntegrityError.
        escursionista_passato ha già la recensione del setUp: un secondo
        tentativo deve fallire in modo CONTROLLATO (redirect 302, non un crash
        500) e non creare duplicati.
        """
        self.client.login(username='trekker_passato', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})
        response = self.client.post(url, {'voto': 2, 'testo': 'Seconda recensione, dovrebbe fallire.'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Recensione.objects.filter(autore=self.escursionista_passato).count(), 1)


class RispondiRecensioneViewTests(RecensioniBaseTestCase):
    def test_solo_la_guida_organizzatrice_puo_rispondere(self):
        """
        SICUREZZA / OWNERSHIP sulla risposta ufficiale. Il controllo
        (request.user != recensione.escursione.guida) impedisce a chiunque non
        sia la guida che ha organizzato l'escursione di scrivere una replica a
        suo nome. trekker_futuro (né autore né guida) ci prova: verifichiamo il
        redirect e, con refresh_from_db(), che il campo risposta_guida sia
        rimasto VUOTO — cioè che l'azione non abbia avuto alcun effetto.
        """
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('rispondi_recensione', kwargs={'recensione_id': self.recensione_base.id})
        response = self.client.post(url, {'risposta_guida': 'Risposta non autorizzata!'})

        self.assertEqual(response.status_code, 302)
        self.recensione_base.refresh_from_db()
        self.assertEqual(self.recensione_base.risposta_guida, '')
