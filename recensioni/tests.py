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

        # Inizializza l'entità radice (Escursione) vincolandola alla guida testata.
        cls.escursione = Escursione.objects.create(
            titolo="Sentiero delle Cascate", difficolta="T",
            dislivello=300, approvata=True, guida=cls.guida,
        )

        # Genera un'istanza di Uscita il cui timestamp (data_ritrovo) è intenzionalmente collocato nel passato.
        cls.uscita_conclusa = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() - timedelta(days=2),  # già avvenuta
            posti_totali=10,
        )
        # Genera un'istanza di Uscita parallela collocata nel futuro.
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

# Suite di validazione della business logic per la creazione di nuove recensioni
class CreaRecensioneViewTests(RecensioniBaseTestCase):

    def test_partecipante_a_uscita_conclusa_puo_recensire(self):
        """
        percorso nominale. Un escursionista con prenotazione confermata su
        un'uscita GIÀ CONCLUSA lascia una recensione valida. Creiamo un nuovo
        trekker apposta e lo iscriviamo all'uscita passata, poi verifichiamo sia
        il redirect sia che la riga sia stata SCRITTA nel database con autore e
        voto corretti (le recensioni passano da 1 a 2).
        """
        # Istanziamento on-the-fly di un nuovo utente specifico per evitare collisioni di stato con recensione_base.
        nuovo_trekker = User.objects.create_user(username='nuovo_trekker', password='password123')
        nuovo_trekker.groups.add(self.gruppo_escursionisti)

        # Consolida il prerequisito relazionale: la presenza di una prenotazione confermata per l'utente.
        Prenotazione.objects.create(
            escursionista=nuovo_trekker, uscita=self.uscita_conclusa, stato='confermata',
        )

        # Avvia la sessione autenticata nel TestClient di Django.
        self.client.login(username='nuovo_trekker', password='password123')
        # Risolve la destinazione passando l'ID dell'escursione come argomento nell'URL.
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        # Esegue la chiamata POST iniettando il payload  della recensione.
        response = self.client.post(url, {'voto': 5, 'testo': 'Esperienza meravigliosa!'})

        # Verifica che il controller abbia completato il flusso restituendo un HTTP 302 verso la view di dettaglio.
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))
        # Esegue una query aggregata COUNT() per verificare che il recordset complessivo sia incrementato a 2.
        self.assertEqual(Recensione.objects.count(), 2)
        # Esegue una query condizionale per accertare l'effettiva persistenza dei dati esatti sul disco (voto=5).
        self.assertTrue(Recensione.objects.filter(autore=nuovo_trekker, voto=5).exists())
    def test_non_si_puo_recensire_un_evento_non_ancora_concluso(self):
        """
        REGOLA TEMPORALE. Non basta essere iscritti: l'esperienza deve essere
        già stata vissuta (uscita__data_ritrovo < adesso). trekker_futuro è
        iscritto SOLO a un'uscita futura, quindi il suo tentativo di recensire
        in anticipo va bloccato: ci aspettiamo un redirect gentile (302) e
        NESSUNA nuova recensione nel database (resta solo quella del setUp).
        """
        # Sessione per l'utente non autorizzato temporalmente.
        self.client.login(username='trekker_futuro', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        # Tenta una POST prematura.
        response = self.client.post(url, {'voto': 3, 'testo': 'Non ci sono ancora andato.'})

        # Verifica che /view abbia abortito l'operazione dirottando l'utente (HTTP 302).
        self.assertEqual(response.status_code, 302)
        # Assicura atomicamente che nessun record anomalo sia stato committato (il count deve restare fermo a 1).
        self.assertEqual(Recensione.objects.count(), 1)

    def test_non_si_puo_recensire_due_volte_la_stessa_escursione(self):
        """
        VINCOLO DI UNICITÀ. unique_together (escursione, autore) sul modello,
        gestito in crea_recensione con try/except IntegrityError.
        escursionista_passato ha già la recensione del setUp: un secondo
        tentativo deve fallire in modo CONTROLLATO (redirect 302, non un crash
        500) e non creare duplicati.
        """
        # Sessione per l'utente che ha già generato un record valido in setUpTestData.
        self.client.login(username='trekker_passato', password='password123')
        url = reverse('crea_recensione', kwargs={'escursione_id': self.escursione.id})

        # Sottomette un nuovo payload che infrange il vincolo unique_together a livello di DB/Model.
        response = self.client.post(url, {'voto': 2, 'testo': 'Seconda recensione, dovrebbe fallire.'})

        # L'eccezione di integrità relazionale deve essere catturata e gestita con un redirect pulito, senza causare panic.
        self.assertEqual(response.status_code, 302)
        # Verifica tramite aggregazione che i constraint del DB abbiano impedito fisicamente l'inserimento del duplicato.
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
        # Sessione malevola/non autorizzata per tentare la scrittura in un campo riservato (Privilege Escalation).
        self.client.login(username='trekker_futuro', password='password123')
        # Risolve la route dedicata alla risposta, iniettando l'ID della recensione esistente.
        url = reverse('rispondi_recensione', kwargs={'recensione_id': self.recensione_base.id})

        # Sottomette un payload di tipo UPDATE sul campo specifico della replica.
        response = self.client.post(url, {'risposta_guida': 'Risposta non autorizzata!'})

        # Si aspetta che la routine di sicurezza espella l'utente intercettando il mismatch di ownership.
        self.assertEqual(response.status_code, 302)
        # Invalida la cache locale dell'istanza e sincronizza lo stato in memoria estraendolo a forza dal disco.
        self.recensione_base.refresh_from_db()
        # Asserisce che il rollback o la mancata chiamata a save() abbiano mantenuto intonsa la colonna bersaglio.
        self.assertEqual(self.recensione_base.risposta_guida, '')
