# =============================================================================
# TEST DELL'APP "escursione" — OWNERSHIP LATO GUIDA E LOGICA DI PRENOTAZIONE
# =============================================================================
# Quest'app contiene la logica di dominio più ricca del progetto: chi può
# modificare cosa (ownership), la gestione dei posti, la lista d'attesa e i
# termini di cancellazione. I 4 test rimasti (su 10 originali) coprono un
# comportamento significativo ciascuno, evitando i doppioni: un controllo di
# sicurezza (403 su risorsa altrui) e le tre regole di business del ciclo di
# prenotazione (posto confermato, lista d'attesa, cancellazione fuori termine).
# =============================================================================

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from datetime import timedelta
from .models import Escursione, Uscita, Prenotazione


class EscursioneBaseTestCase(TestCase):
    """
    Prepara lo scenario condiviso: i due gruppi-ruolo, due guide (una
    proprietaria e una "estranea", per i test di ownership), un escursionista, e
    un'escursione con una singola uscita futura da 2 posti.

    setUpTestData gira una sola volta per classe (vedi commento in core/tests.py).
    """

    @classmethod
    def setUpTestData(cls):
        cls.gruppo_guide = Group.objects.create(name='Guide')
        cls.gruppo_escursionisti = Group.objects.create(name='Escursionisti')

        # guida_1 è la PROPRIETARIA dell'escursione; guida_2 è un'altra guida
        # (autenticata e nel gruppo giusto) usata per provare che NON possa
        # toccare gli itinerari altrui.
        cls.guida_1 = User.objects.create_user(username='guida_mario', password='password123')
        cls.guida_1.groups.add(cls.gruppo_guide)
        cls.guida_2 = User.objects.create_user(username='guida_luigi', password='password123')
        cls.guida_2.groups.add(cls.gruppo_guide)

        cls.escursionista = User.objects.create_user(username='trekker_luca', password='password123')
        cls.escursionista.groups.add(cls.gruppo_escursionisti)

        cls.escursione = Escursione.objects.create(
            titolo="Sentiero degli Dei", descrizione="Un percorso bellissimo.",
            difficolta="E", dislivello=500, approvata=True, guida=cls.guida_1,
        )
        cls.uscita = Uscita.objects.create(
            escursione=cls.escursione,
            data_ritrovo=timezone.now() + timedelta(days=5),
            posti_totali=2, posti_occupati=0,
        )


class OwnershipGuidaTests(EscursioneBaseTestCase):
    def test_guida_non_puo_aggiungere_date_a_escursioni_altrui(self):
        """
        SICUREZZA / OWNERSHIP. Una guida autenticata e nel gruppo giusto
        (guida_luigi) NON deve poter aggiungere una data all'itinerario di
        un'ALTRA guida, anche conoscendone l'id nell'URL. Il controllo in
        UscitaCreateView deve respingere la richiesta con 403 Forbidden (non
        ignorarla in silenzio né rimandare altrove): testare lo status esatto
        rende chiaro che è un rifiuto di autorizzazione consapevole.
        """
        # Effettua il login simulato con l'account della guida "estranea".
        self.client.login(username='guida_luigi', password='password123')
        # Costruisce l'URL della view passando l'ID dell'escursione (appartenente a guida_1) nei kwargs.
        url = reverse('aggiungi_data_uscita', kwargs={'escursione_id': self.escursione.id})

        # Invia una richiesta POST (che modificherebbe il DB) con dati validi per una nuova uscita.
        response = self.client.post(url, {
            'data_ritrovo': timezone.now() + timedelta(days=10),
            'posti_totali': 15,
        })

        # il server deve rifiutare l'operazione restituendo esattamente il codice HTTP 403 (Accesso Negato).
        self.assertEqual(response.status_code, 403)


class PrenotazioneBusinessLogicTests(EscursioneBaseTestCase):
    def setUp(self):
        # setUp gira prima di OGNI test di questa classe (vs setUpTestData, una
        # volta sola): qui calcola solo l'URL di prenotazione, operazione troppo
        # leggera per giustificare la cache di setUpTestData.
        self.url_prenota = reverse('prenota_uscita', kwargs={'uscita_id': self.uscita.id})

    # Inizio test: verifica il percorso nominale di una prenotazione andata a buon fine.
    def test_prenotazione_con_posti_liberi_va_a_buon_fine(self):
        """
        Verifica TRE effetti insieme: il
        redirect dopo il POST; l'incremento REALE di posti_occupati sul database
        (refresh_from_db ricarica i valori dal DB, altrimenti controlleremmo una
        copia in memoria mai aggiornata); e che la Prenotazione nasca con stato
        'confermata' (posto garantito), non 'attesa'.
        """
        # Autentica l'utente cliente.
        self.client.login(username='trekker_luca', password='password123')

        # Invia la richiesta POST all'URL generato nel setUp() per scatenare la logica di prenotazione.
        response = self.client.post(self.url_prenota)

        # Verifica 1/3: Controlla che, a successo avvenuto, l'utente venga reindirizzato (HTTP 302) alla pagina di dettaglio.
        self.assertRedirects(response, reverse('dettaglio_escursione', kwargs={'pk': self.escursione.id}))
        # Forza l'aggiornamento dell'oggetto `self.uscita` in memoria rileggendolo dal database reale.
        self.uscita.refresh_from_db()
        # Verifica 2/3: Controlla che il contatore dei posti occupati sia fisicamente aumentato a 1.
        self.assertEqual(self.uscita.posti_occupati, 1)
        # Recupera il record di Prenotazione appena creato nel database per ispezionarlo.
        prenotazione = Prenotazione.objects.get(escursionista=self.escursionista, uscita=self.uscita)
        # Verifica 3/3: Assicura che, essendoci posti liberi, lo stato del record sia 'confermata'.
        self.assertEqual(prenotazione.stato, 'confermata')



    def test_prenotazione_su_uscita_piena_finisce_in_lista_attesa(self):
        """
        LISTA D'ATTESA / NO OVERBOOKING. Portiamo l'uscita al completo
        (posti_occupati = posti_totali = 2) e proviamo a prenotare. Due
        asserzioni chiave: il contatore NON deve superare il totale (niente
        overbooking) E la Prenotazione deve comunque essere creata, ma con stato
        'attesa' invece di essere rifiutata: così l'utente entra in coda e potrà
        subentrare in caso di disdette.
        """
        # Manipola lo stato dell'istanza in memoria riempiendo l'uscita.
        self.uscita.posti_occupati = 2
        # Salva la manipolazione nel database per preparare lo scenario del test.
        self.uscita.save()

        # Autentica il cliente.
        self.client.login(username='trekker_luca', password='password123')
        # Invia la richiesta POST per prenotare nonostante i posti siano esauriti.
        self.client.post(self.url_prenota)

        # Ricarica i dati dell'uscita dal database.
        self.uscita.refresh_from_db()
        # Verifica 1/2: Assicura che il sistema non sia andato in overbooking (i posti occupati restano 2).
        self.assertEqual(self.uscita.posti_occupati, 2)  # nessun overbooking
        # Recupera la prenotazione generata.
        prenotazione = Prenotazione.objects.get(escursionista=self.escursionista, uscita=self.uscita)
        # Verifica 2/2: Assicura che la logica abbia salvato la prenotazione, ma declassata allo stato 'attesa'.
        self.assertEqual(prenotazione.stato, 'attesa')


    def test_cancellazione_bloccata_sotto_il_termine_minimo(self):
        """
        Probabilmente il test più complesso.
        REGOLA DI BUSINESS TEMPORALE (ORE_LIMITE_CANCELLAZIONE, core/constants).
        Un utente non può disdire "all'ultimo": impostiamo l'uscita tra sole 5
        ore (sotto le 24 di preavviso) e verifichiamo che la cancellazione venga
        RIFIUTATA. La prova non è lo status, ma gli effetti: la Prenotazione
        deve sopravvivere e il posto restare occupato (nessuna liberazione).
        """
        # Modifica la data di ritrovo spostandola nel futuro ravvicinato (solo 5 ore da adesso).
        # Serve a innescare la condizione di blocco. Stiamo simulando il contesto in cui l'utente tenta di cancellare la prenotazione la mattina stessa dell'uscita.
        self.uscita.data_ritrovo = timezone.now() + timedelta(hours=5)
        # Occupa fisicamente un posto in memoria.
        self.uscita.posti_occupati = 1
        # Registra la nuova configurazione dell'uscita nel database.
        # Esegue una query UPDATE per consolidare le modifiche appena fatte (data e posti) nel database temporaneo di test.
        self.uscita.save()

        # Crea manualmente (bypassando le views) una prenotazione già confermata per questo utente.
        prenotazione = Prenotazione.objects.create(
            escursionista=self.escursionista, uscita=self.uscita, stato='confermata',
        )

        # Autentica l'utente.
        # La view di cancellazione è protetta. Senza questo passaggio, il test riceverebbe un errore 403 (Accesso Negato) prima ancora di eseguire la logica temporale.
        self.client.login(username='trekker_luca', password='password123')
        # Genera dinamicamente l'URL della view che gestisce la cancellazione.
        url = reverse('cancella_prenotazione', kwargs={'prenotazione_id': prenotazione.id})
        # Esegue la chiamata POST, che dovrebbe attivare il tentativo di cancellazione.
        self.client.post(url)

        # Verifica 1/2: Il record di prenotazione esiste ancora nel DB (la cancellazione è fallita e non l'ha cancellato).
        self.assertTrue(Prenotazione.objects.filter(id=prenotazione.id).exists())
        # Ricarica i dati dell'uscita per verificare le variazioni del contatore.
        self.uscita.refresh_from_db()
        # Verifica 2/2: Il posto risulta ancora occupato, dimostrando che il rollback o il blocco dell'azione hanno protetto l'integrità dei dati.
        self.assertEqual(self.uscita.posti_occupati, 1)