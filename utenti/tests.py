# =============================================================================
# TEST DELL'APP "utenti" — REGISTRAZIONE, PROFILO, ELIMINAZIONE, PASSWORD
# =============================================================================

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from escursione.models import Escursione


class WayPointUtentiTestCase(TestCase):
    """
    Classe base per la preparazione dei dati di test (Gruppi).
    Eseguito una sola volta per ottimizzare i tempi del database di test.
    """

    @classmethod
    def setUpTestData(cls):
        cls.gruppo_escursionisti = Group.objects.create(name='Escursionisti')
        cls.gruppo_guide = Group.objects.create(name='Guide')


class RegistrazioneUtenteViewTests(WayPointUtentiTestCase):
    def test_pagina_registrazione_carica_200(self):
        """
        COSA TESTA: che la pagina di registrazione sia raggiungibile (200)
        e usi il template corretto. È uno smoke test volutamente minimo:
        NON verifica che la registrazione funzioni davvero (per quello,
        vedi test_registrazione_crea_utente_nel_gruppo_corretto qui sotto).
        Lo si tiene comunque perché è un controllo rapido e a costo quasi
        zero contro un errore banale ma bloccante (es. un typo nel nome del
        template che romperebbe l'intera pagina).
        """
        response = self.client.get(reverse('registrazione'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'utenti/registrazione.html')

    def test_registrazione_crea_utente_nel_gruppo_corretto(self):
        """
        COSA TESTA: il percorso end-to-end completo della
        registrazione, non solo che la pagina si apra. Invia dati di
        registrazione validi (RegistrazioneForm, utenti/form.py: richiede
        username, password1/password2, email, first_name, last_name, e il
        campo "ruolo" scelto tra 'guida'/'escursionista'), e verifica che:
        1) un nuovo User venga davvero creato nel database;
        2) venga automaticamente iscritto al Group corretto in base al
           ruolo scelto (la logica in RegistrazioneForm.save(), che decide
           GRUPPO_GUIDE o GRUPPO_ESCURSIONISTI leggendo cleaned_data['ruolo']);
        3) la password NON sia salvata in chiaro (deve iniziare con il
           prefisso dell'algoritmo di hashing di Django, non essere
           uguale alla password inviata nel form).
        """
        dati_registrazione = {
            'username': 'nuovo_escursionista_test',
            'password1': 'UnaPasswordSicura123!',
            'password2': 'UnaPasswordSicura123!',
            'email': 'nuovo@example.com',
            'first_name': 'Test',
            'last_name': 'Utente',
            'ruolo': 'escursionista',
        }

        response = self.client.post(reverse('registrazione'), dati_registrazione)

        # Il form valido deve reindirizzare (a 'login', si veda
        # RegistrazioneUtenteView.success_url), non ri-mostrare la pagina
        # con errori.
        self.assertRedirects(response, reverse('login'))

        # 1. L'utente deve esistere davvero nel database
        self.assertTrue(User.objects.filter(username='nuovo_escursionista_test').exists())
        nuovo_utente = User.objects.get(username='nuovo_escursionista_test')

        # 2. Deve essere stato iscritto al gruppo Escursionisti (non Guide)
        self.assertTrue(nuovo_utente.groups.filter(name='Escursionisti').exists())
        self.assertFalse(nuovo_utente.groups.filter(name='Guide').exists())

        # 3. La password non deve mai essere salvata in chiaro
        self.assertNotEqual(nuovo_utente.password, 'UnaPasswordSicura123!')
        self.assertTrue(nuovo_utente.check_password('UnaPasswordSicura123!'))

    def test_registrazione_come_guida_assegna_gruppo_guide(self):
        """
        COSA TESTA: controllo simmetrico al test precedente, con
        ruolo='guida' invece di 'escursionista'. Verifica che la biforcazione
        in RegistrazioneForm.save() (if ruolo_scelto == 'guida': ... else:
        ...) assegni il gruppo corretto in ENTRAMBI i casi, non solo in uno:
        """
        dati_registrazione = {
            'username': 'nuova_guida_test',
            'password1': 'UnaPasswordSicura123!',
            'password2': 'UnaPasswordSicura123!',
            'email': 'guida_nuova@example.com',
            'first_name': 'Test',
            'last_name': 'Guida',
            'ruolo': 'guida',
        }

        self.client.post(reverse('registrazione'), dati_registrazione)

        nuova_guida = User.objects.get(username='nuova_guida_test')
        self.assertTrue(nuova_guida.groups.filter(name='Guide').exists())
        self.assertFalse(nuova_guida.groups.filter(name='Escursionisti').exists())


class ProfiloUtenteViewTests(WayPointUtentiTestCase):
    def test_accesso_profilo_anonimo_reindirizza(self):
        """
        COSA TESTA: LoginRequiredMixin su ProfiloUtenteView. Un utente non
        autenticato deve essere reindirizzato (302) al login, non vedere il
        profilo né ricevere un errore.
        """
        response = self.client.get(reverse('profilo'))
        self.assertEqual(response.status_code, 302)

    def test_profilo_guida_context_data(self):
        """
        COSA TESTA: che il context passato al template distingua
        correttamente una Guida (is_guida=True, is_escursionista=False) e
        calcoli il contatore delle sue escursioni create.
        """
        guida = User.objects.create_user(username='guida_test', password='password123')
        guida.groups.add(self.gruppo_guide)

        self.client.login(username='guida_test', password='password123')
        response = self.client.get(reverse('profilo'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_guida'])
        self.assertFalse(response.context['is_escursionista'])
        self.assertEqual(response.context['escursioni_create_count'], 0)

    def test_profilo_escursionista_nuovo_fallback_raccomandazione(self):
        """
        COSA TESTA: il sistema di raccomandazione, nel suo caso limite più
        delicato — il "cold start" (un escursionista appena registrato, con
        zero storico di partecipazione). Senza una gestione esplicita di
        questo caso, il sistema di raccomandazione (che normalmente si basa
        sullo storico personale) rischierebbe di restituire una lista vuota
        o di sollevare un'eccezione. Verifica che scatti invece la logica di
        fallback (mostrare comunque qualche escursione, qui una).
        """

        finta_guida = User.objects.create_user(username='guida_fittizia', password='123')

        #  Creiamo un'escursione di test approvata, passandogli la finta guida
        Escursione.objects.create(
            titolo="Sentiero Test",
            difficolta="E",
            approvata=True,
            dislivello=500,
            guida=finta_guida)

        escursionista = User.objects.create_user(username='trekker_test', password='password123')
        escursionista.groups.add(self.gruppo_escursionisti)

        self.client.login(username='trekker_test', password='password123')
        response = self.client.get(reverse('profilo'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_escursionista'])
        # Verifica l'innesco della logica di fallback (almeno un'escursione consigliata)
        self.assertEqual(len(response.context['raccomandazioni_esperienza']), 1)


class EliminaUtenteViewTests(WayPointUtentiTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='user_comune', password='password123')

    def test_utente_comune_puo_eliminarsi(self):
        """
        COSA TESTA: il percorso "felice" dell'auto-eliminazione
        dell'account. Verifica sia il redirect alla home sia,
        soprattutto, che l'utente sia DAVVERO sparito dal database (non
        solo disattivato o marcato in qualche altro modo).
        """
        self.client.login(username='user_comune', password='password123')

        response = self.client.post(reverse('elimina_utente'))

        # 1. Deve reindirizzare alla home
        self.assertRedirects(response, reverse('core:home'))
        # 2. L'utente non deve più esistere nel database
        self.assertFalse(User.objects.filter(username='user_comune').exists())

    def test_superuser_viene_bloccato_da_cancellazione(self):
        """
        COSA TESTA: un vincolo di sicurezza specifico — un superuser (admin)
        NON deve poter cancellare il proprio account tramite questa via
        "da utente comune". La view deve
        sollevare PermissionDenied (tradotto da Django in 403), e l'account
        deve sopravvivere al tentativo.
        """
        admin = User.objects.create_superuser(username='admin_test', password='password123')
        self.client.login(username='admin_test', password='password123')

        response = self.client.post(reverse('elimina_utente'))

        # Django traduce il raise PermissionDenied in un codice di stato 403 Forbidden
        self.assertEqual(response.status_code, 403)
        # L'admin deve essere ancora presente a sistema
        self.assertTrue(User.objects.filter(username='admin_test').exists())


class CambiaPasswordViewTests(WayPointUtentiTestCase):
    def test_cambio_password_successo(self):
        """
        COSA TESTA: che il cambio password funzioni, che la NUOVA password sia
        davvero quella utilizzabile per un login successivo. Per questo,
        dopo il cambio, il test fa esplicitamente logout e un nuovo
        tentativo di login con la password aggiornata".
        """
        user = User.objects.create_user(username='pass_test', password='VecchiaPassword123')
        self.client.login(username='pass_test', password='VecchiaPassword123')

        form_data = {
            'old_password': 'VecchiaPassword123',
            'new_password1': 'NuovissimaPassword123!',
            'new_password2': 'NuovissimaPassword123!'
        }

        response = self.client.post(reverse('cambio_password'), form_data)

        # Verifica il reindirizzamento al profilo
        self.assertRedirects(response, reverse('profilo'))

        # Verifichiamo che la sessione riconosca la nuova password effettuando un logout e un nuovo login
        self.client.logout()
        login_valido = self.client.login(username='pass_test', password='NuovissimaPassword123!')
        self.assertTrue(login_valido)
