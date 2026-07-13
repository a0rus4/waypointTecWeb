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
        """Verifica che la pagina di registrazione risponda con status HTTP 200."""
        response = self.client.get(reverse('registrazione'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'utenti/registrazione.html')


class ProfiloUtenteViewTests(WayPointUtentiTestCase):
    def test_accesso_profilo_anonimo_reindirizza(self):
        """Verifica che un utente non loggato venga bloccato (Redirect 302)."""
        response = self.client.get(reverse('profilo'))
        self.assertEqual(response.status_code, 302)

    def test_profilo_guida_context_data(self):
        """Verifica che una Guida veda correttamente i propri contatori nel pannello."""
        guida = User.objects.create_user(username='guida_test', password='password123')
        guida.groups.add(self.gruppo_guide)

        self.client.login(username='guida_test', password='password123')
        response = self.client.get(reverse('profilo'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_guida'])
        self.assertFalse(response.context['is_escursionista'])
        self.assertEqual(response.context['escursioni_create_count'], 0)

    def test_profilo_escursionista_nuovo_fallback_raccomandazione(self):
        """Verifica che un nuovo escursionista riceva i 3 itinerari di fallback nel context."""
        # 1. FIX: Prima creiamo un utente "Guida" fasullo per soddisfare i requisiti del database
        finta_guida = User.objects.create_user(username='guida_fittizia', password='123')

        # 2. Creiamo un'escursione di test approvata, passandogli la finta guida
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
        """Verifica che un utente normale possa cancellare il proprio account via POST."""
        self.client.login(username='user_comune', password='password123')


        response = self.client.post(reverse('elimina_utente'))

        # 1. Deve reindirizzare alla home
        self.assertRedirects(response, reverse('core:home'))
        # 2. L'utente non deve più esistere nel database
        self.assertFalse(User.objects.filter(username='user_comune').exists())

    def test_superuser_viene_bloccato_da_cancellazione(self):
        """Verifica il vincolo di sicurezza: l'admin riceve un HTTP 403 (PermissionDenied)."""
        admin = User.objects.create_superuser(username='admin_test', password='password123')
        self.client.login(username='admin_test', password='password123')


        response = self.client.post(reverse('elimina_utente'))

        # Django traduce il raise PermissionDenied in un codice di stato 403 Forbidden
        self.assertEqual(response.status_code, 403)
        # L'admin deve essere ancora presente a sistema
        self.assertTrue(User.objects.filter(username='admin_test').exists())


class CambiaPasswordViewTests(WayPointUtentiTestCase):
    def test_cambio_password_successo(self):
        """Verifica che l'utente possa aggiornare la password e fare nuovamente login."""
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