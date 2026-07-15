# =============================================================================
# TEST DELL'APP "utenti" — REGISTRAZIONE, RACCOMANDAZIONI, SICUREZZA ACCOUNT
# =============================================================================
# Quest'app gestisce identità e account. I 4 test rimasti (su 9) coprono
# quattro sottosistemi distinti e non banali: la registrazione end-to-end (con
# assegnazione del gruppo giusto e hashing della password), il sistema di
# raccomandazione nel suo caso limite (utente senza storico), un vincolo di
# sicurezza sulla cancellazione (il superuser non si auto-elimina da qui) e il
# cambio password verificato con un vero login successivo.
# =============================================================================

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from escursione.models import Escursione


class WayPointUtentiTestCase(TestCase):
    """Prepara i due gruppi-ruolo, usati dai test di registrazione e profilo."""

    @classmethod
    def setUpTestData(cls):
        cls.gruppo_escursionisti = Group.objects.create(name='Escursionisti')
        cls.gruppo_guide = Group.objects.create(name='Guide')


class RegistrazioneUtenteViewTests(WayPointUtentiTestCase):
    def test_registrazione_crea_utente_nel_gruppo_giusto_e_con_password_hashata(self):
        """
        REGISTRAZIONE END-TO-END. Invia dati validi al RegistrazioneForm e
        verifica tre cose in un colpo solo:
          1) un nuovo User viene creato davvero nel database;
          2) viene iscritto al Group corretto in base al 'ruolo' scelto (la
             biforcazione in RegistrazioneForm.save(): qui 'escursionista' ->
             gruppo Escursionisti, e NON Guide);
          3) la password NON è salvata in chiaro: check_password() accetta
             l'originale, ma il campo memorizzato è diverso dalla stringa inviata
             (è un hash), come richiede una gestione sicura delle credenziali.
        """
        dati = {
            'username': 'nuovo_escursionista_test',
            'password1': 'UnaPasswordSicura123!',
            'password2': 'UnaPasswordSicura123!',
            'email': 'nuovo@example.com',
            'first_name': 'Test', 'last_name': 'Utente',
            'ruolo': 'escursionista',
        }
        response = self.client.post(reverse('registrazione'), dati)

        # Form valido -> redirect al login (non ri-render con errori)
        self.assertRedirects(response, reverse('login'))

        nuovo = User.objects.get(username='nuovo_escursionista_test')
        self.assertTrue(nuovo.groups.filter(name='Escursionisti').exists())
        self.assertFalse(nuovo.groups.filter(name='Guide').exists())
        self.assertNotEqual(nuovo.password, 'UnaPasswordSicura123!')  # non in chiaro
        self.assertTrue(nuovo.check_password('UnaPasswordSicura123!'))


class ProfiloUtenteViewTests(WayPointUtentiTestCase):
    def test_raccomandazioni_fallback_per_escursionista_senza_storico(self):
        """
        SISTEMA DI RACCOMANDAZIONE — caso limite "cold start". Un escursionista
        appena registrato non ha storico di partecipazione: la logica basata sui
        gusti passati non avrebbe dati e rischierebbe una lista vuota o
        un'eccezione. Il test verifica che scatti invece il FALLBACK, cioè che
        vengano comunque proposte escursioni (qui l'unica approvata a sistema).
        """
        finta_guida = User.objects.create_user(username='guida_fittizia', password='123')
        Escursione.objects.create(
            titolo="Sentiero Test", difficolta="E", approvata=True,
            dislivello=500, guida=finta_guida,
        )

        escursionista = User.objects.create_user(username='trekker_test', password='password123')
        escursionista.groups.add(self.gruppo_escursionisti)

        self.client.login(username='trekker_test', password='password123')
        response = self.client.get(reverse('profilo'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_escursionista'])
        self.assertEqual(len(response.context['raccomandazioni_esperienza']), 1)


class EliminaUtenteViewTests(WayPointUtentiTestCase):
    def test_superuser_non_puo_auto_eliminarsi_da_questa_vista(self):
        """
        SICUREZZA. La cancellazione account "da utente comune" non deve poter
        distruggere un superuser (protezione contro la rimozione accidentale
        dell'amministratore). La view deve sollevare PermissionDenied (403) e
        l'account admin deve sopravvivere al tentativo.
        """
        User.objects.create_superuser(username='admin_test', password='password123')
        self.client.login(username='admin_test', password='password123')

        response = self.client.post(reverse('elimina_utente'))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(username='admin_test').exists())


class CambiaPasswordViewTests(WayPointUtentiTestCase):
    def test_cambio_password_rende_utilizzabile_la_nuova_password(self):
        """
        CAMBIO PASSWORD verificato sul serio. Non ci fermiamo al redirect di
        successo: dopo il cambio facciamo logout e proviamo un NUOVO login con
        la password aggiornata. Solo se quel login riesce abbiamo la prova che
        la nuova password è davvero quella attiva (e che la sessione è stata
        gestita correttamente).
        """
        User.objects.create_user(username='pass_test', password='VecchiaPassword123')
        self.client.login(username='pass_test', password='VecchiaPassword123')

        response = self.client.post(reverse('cambio_password'), {
            'old_password': 'VecchiaPassword123',
            'new_password1': 'NuovissimaPassword123!',
            'new_password2': 'NuovissimaPassword123!',
        })
        self.assertRedirects(response, reverse('profilo'))

        self.client.logout()
        login_valido = self.client.login(username='pass_test', password='NuovissimaPassword123!')
        self.assertTrue(login_valido)
