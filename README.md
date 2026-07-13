WayPoint

Applicazione web Django per la gestione di escursioni ed uscite di trekking:
catalogo pubblico con ricerca avanzata, prenotazioni con lista d'attesa,
recensioni post-escursione e moderazione, pannello di amministrazione per
guide e amministratori.

Progetto realizzato per un esame universitario.

Funzionalità principali


Catalogo pubblico con ricerca combinabile per testo, difficoltà,
dislivello massimo, data e disponibilità posti, con paginazione
(core/views.py).
Gestione escursioni e uscite: le Guide creano itinerari (Escursione)
e ne pianificano le date (Uscita); le nuove escursioni restano in
attesa di approvazione da parte di un Amministratore prima di comparire
nel catalogo pubblico.
Prenotazioni con controllo posti in tempo reale, lista d'attesa
automatica quando un'uscita è al completo, e cancellazione soggetta a un
limite di 24 ore prima della partenza (core/constants.py).
Notifiche via email (in bcc, per non esporre gli indirizzi degli
altri partecipanti) quando un'uscita viene cancellata o quando si libera
un posto per chi è in lista d'attesa.
Recensioni con voto e commento sulle escursioni concluse, risposta
della guida, segnalazione da parte degli utenti e provvedimenti
(avvertimento / ban) applicabili dagli amministratori da pannello admin.
Consigliati per te: suggerimenti di nuove escursioni basati sullo
storico di partecipazione dell'utente (filtro per difficoltà simile a
escursioni già svolte).
Ruoli: Escursionista, Guida e Amministratore, con permessi distinti
gestiti tramite i gruppi di Django (django.contrib.auth.models.Group).


Stack tecnico


Python 3.12, Django
SQLite (database di sviluppo)
Pillow (gestione immagini)
Bootstrap (frontend) e Leaflet.js (mappa punto di ritrovo)
Gestione dipendenze con pipenv


Struttura del progetto

waypoint_project/   Impostazioni globali Django, URL principali
core/                Homepage pubblica e motore di ricerca
escursione/          Modelli, viste, form e admin di Escursione/Uscita/Prenotazione
recensioni/          Modelli, viste, form e admin delle recensioni
utenti/              Registrazione, profilo utente, provvedimenti di moderazione
static/               Asset statici sorgente (CSS/immagini di base)
media/               Immagini caricate (copertine, gallerie) — incluse anche
                     le immagini "seed" usate da popola_db

Setup del progetto

Requisiti: Python 3.12 e pipenv installati.

bash# 1. Installare le dipendenze (crea automaticamente il virtualenv)
pipenv install

# 2. Attivare il virtualenv
pipenv shell

# 3. Creare il database e applicare le migrazioni
python manage.py migrate

# 4. Creare un utente amministratore
python manage.py createsuperuser

# 5. (Opzionale ma consigliato) Popolare il database con dati dimostrativi:
python manage.py popola_db

# 6. Avviare il server di sviluppo
python manage.py runserver

L'app sarà raggiungibile su http://127.0.0.1:8000/, il pannello di
amministrazione su http://127.0.0.1:8000/admin/.

Test

python manage.py test

Esegue la suite di test automatici presente in ogni app (tests.py).