# =============================================================================
# TEST DELL'APP "escursione" — VISTE PUBBLICHE, GESTIONE LATO GUIDA, PRENOTAZIONI
# =============================================================================

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

    TEORIA — setUpTestData: eseguito UNA SOLA VOLTA per l'intera classe
    (non prima di ogni singolo test), dentro una transazione di database
    che viene fa un rollback automaticamente dopo ogni test. Questo
    significa che ogni test parte da uno stato identico e pulito, senza
    dover ricreare da zero gruppi/utenti/escursione in ogni singolo metodo:
    più veloce e meno codice ripetuto.
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

        cls.escursionista = User.objects.create_user(
            username='trekker_luca', password='password123', email='luca@example.com'
        )
        cls.escursionista.groups.add(cls.gruppo_escursionisti)

        # Un secondo escursionista, usato dai test sulla lista d'attesa e
        # sulla notifica email (serve un "terzo" utente distinto sia dal
        # proprietario dell'escursione sia dal primo escursionista).
        cls.escursionista_2 = User.objects.create_user(
            username='trekker_giulia', password='password123', email='giulia@example.com'
        )
        cls.escursionista_2.groups.add(cls.gruppo_escursionisti)

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
        """
        COSA TESTA: che la pagina di dettaglio di un'escursione sia
        raggiungibile da un utente ANONIMO (nessun login effettuato in
        questo test), come richiesto dalla traccia ("gli utenti anonimi
        possono visualizzare le escursioni disponibili"). Verifica anche che
        il contenuto reale (il titolo) sia effettivamente presente nell'HTML
        restituito, non solo che lo status sia 200
        """
        url = reverse('dettaglio_escursione', kwargs={'pk': self.escursione.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'escursione/escursione_detail.html')
        self.assertContains(response, "Sentiero degli Dei")


class GestioneLatiGuidaTests(EscursioneBaseTestCase):
    def test_guida_puo_creare_uscita_per_propria_escursione(self):
        """
        COSA TESTA: che la Guida PROPRIETARIA dell'escursione riesca ad
        accedere alla pagina per aggiungere una nuova data (Uscita). È il
        controllo "positivo" (percorso consentito), da leggere in coppia con
        il test successivo (percorso negato) per avere la prova che il
        controllo di ownership discrimina correttamente tra i due casi,
        e non blocca semplicemente chiunque per errore.
        """
        self.client.login(username='guida_mario', password='password123')
        url = reverse('aggiungi_data_uscita', kwargs={'escursione_id': self.escursione.id})

        # Test di caricamento della pagina form
        response_get = self.client.get(url)
        self.assertEqual(response_get.status_code, 200)

    def test_guida_NON_puo_aggiungere_date_a_escursioni_altrui(self):
        """
        COSA TESTA: il controllo di OWNERSHIP in UscitaCreateView.form_valid(). Una
        Guida autenticata E autorizzata a creare uscite in generale
        (appartiene al gruppo Guide) NON deve poter modificare l'itinerario
        di UN'ALTRA guida solo perché ne conosce l'id nell'URL. guida_luigi
        qui è autenticato e nel gruppo giusto, ma NON è il proprietario di
        "Sentiero degli Dei" (che appartiene a guida_mario): la richiesta
        deve essere respinta con 403, non semplicemente ignorata o
        rediretta altrove.
        """
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
        """
        COSA TESTA: lo stesso principio di ownership del test precedente,
        ma sull'azione più distruttiva del progetto (elimina_escursione,
        che cancella a cascata anche tutte le Uscite e Prenotazioni
        collegate). La verifica più importante qui non è solo lo status
        della risposta, ma che l'ESCURSIONE ESISTA ANCORA nel database dopo
        """
        self.client.login(username='guida_luigi', password='password123')  # Guida sbagliata
        url = reverse('elimina_escursione', kwargs={'escursione_id': self.escursione.id})

        self.client.post(url)

        # L'escursione deve ancora esistere nel database!
        self.assertTrue(Escursione.objects.filter(id=self.escursione.id).exists())

    def test_solo_proprietario_puo_eliminare_uscita(self):
        """
        COSA TESTA: controllo di ownership simmetrico al test
        precedente, ma su elimina_uscita invece di elimina_escursione.
        Stesso schema: guida_luigi (autenticato, ma non
        proprietario) tenta di cancellare una data di un itinerario altrui,
        e l'Uscita deve sopravvivere al tentativo.
        """
        self.client.login(username='guida_luigi', password='password123')
        url = reverse('elimina_uscita', kwargs={'uscita_id': self.uscita.id})

        self.client.post(url)

        self.assertTrue(Uscita.objects.filter(id=self.uscita.id).exists())


class PrenotazioneBusinessLogicTests(EscursioneBaseTestCase):
    def setUp(self):
        """
        TEORIA — setUp vs setUpTestData: setUp (senza "Test") gira PRIMA DI
        OGNI SINGOLO test_* di questa classe (non una volta sola per
        l'intera classe). Qui si usa per calcolare l'URL di prenotazione,
        un'operazione così leggera da non giustificare l'ottimizzazione di
        setUpTestData, e che in teoria potrebbe dipendere da dati diversi
        in futuri test aggiunti a questa classe.
        """
        self.url_prenota = reverse('prenota_uscita', kwargs={'uscita_id': self.uscita.id})

    def test_prenotazione_confermata_successo(self):
        """
        COSA TESTA: il percorso "felice" della prenotazione (posti
        disponibili). Verifica TRE cose distinte: il redirect
        dopo il POST, l'aggiornamento reale del contatore posti_occupati sul
        database (non solo in memoria: self.uscita.refresh_from_db() ricarica
        i valori scrivendo sopra quelli in memoria, altrimenti staremmo
        controllando una copia locale mai più sincronizzata con l'uscita
        vera), e che la Prenotazione creata abbia lo stato corretto
        ('confermata', non 'attesa').
        """
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
        """
        COSA TESTA: la transizione di stato quando l'uscita è già al
        completo (posti_occupati == posti_totali, impostato manualmente qui
        per simulare il sold-out senza dover creare N prenotazioni finte).
        Due asserzioni chiave insieme: il contatore NON deve salire oltre il
        totale (non deve esserci overbooking), E la nuova Prenotazione deve
        comunque essere stata creata, ma con stato 'attesa' invece di essere
        semplicemente rifiutata ".
        """
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
        """
        COSA TESTA: il controllo di ruolo in prenota_uscita — solo chi
        appartiene al gruppo Escursionisti può prenotare. guida_mario è
        autenticato (supera @login_required) ma non è nel gruppo giusto:
        la richiesta non deve produrre NESSUNA Prenotazione nel database,
        indipendentemente da quale status HTTP venga restituito (qui si
        verifica direttamente l'assenza dell'effetto, il modo più robusto
        di testare "questa azione non deve avere avuto luogo").
        """
        self.client.login(username='guida_mario', password='password123')
        self.client.post(self.url_prenota)

        # Non deve essere stata creata alcuna prenotazione
        self.assertFalse(Prenotazione.objects.exists())

    def test_cancellazione_bloccata_entro_24_ore(self):
        """
        COSA TESTA: il termine minimo di preavviso per la
        cancellazione (ORE_LIMITE_CANCELLAZIONE, core/constants.py),
        applicato in cancella_prenotazione.
        Impostiamo data_ritrovo tra sole 5 ore (meno delle 24 richieste) e
        verifichiamo che la Prenotazione sopravviva al tentativo di
        cancellazione: la vista deve rifiutare l'operazione, non eseguirla.
        """
        self.uscita.data_ritrovo = timezone.now() + timedelta(hours=5)
        self.uscita.posti_occupati = 1
        self.uscita.save()

        prenotazione = Prenotazione.objects.create(
            escursionista=self.escursionista, uscita=self.uscita, stato='confermata'
        )

        self.client.login(username='trekker_luca', password='password123')
        url = reverse('cancella_prenotazione', kwargs={'prenotazione_id': prenotazione.id})
        self.client.post(url)

        # La prenotazione deve esistere: la cancellazione va rifiutata
        self.assertTrue(Prenotazione.objects.filter(id=prenotazione.id).exists())
        # E il posto deve restare occupato (nessuna liberazione avvenuta)
        self.uscita.refresh_from_db()
        self.assertEqual(self.uscita.posti_occupati, 1)

    def test_cancellazione_permessa_oltre_24_ore(self):
        """
        COSA TESTA: controllo simmetrico al test precedente. Con la
        stessa identica prenotazione ma un'uscita programmata tra 3 giorni
        la cancellazione deve invece
        riuscire: la Prenotazione deve sparire dal database e il posto
        deve tornare libero.
        """
        self.uscita.data_ritrovo = timezone.now() + timedelta(days=3)
        self.uscita.posti_occupati = 1
        self.uscita.save()

        prenotazione = Prenotazione.objects.create(
            escursionista=self.escursionista, uscita=self.uscita, stato='confermata'
        )

        self.client.login(username='trekker_luca', password='password123')
        url = reverse('cancella_prenotazione', kwargs={'prenotazione_id': prenotazione.id})
        self.client.post(url)

        self.assertFalse(Prenotazione.objects.filter(id=prenotazione.id).exists())
        self.uscita.refresh_from_db()
        self.assertEqual(self.uscita.posti_occupati, 0)


