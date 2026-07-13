# =============================================================================
# MANAGEMENT COMMAND: popola_db
# =============================================================================
# TEORIA — comandi di gestione personalizzati (django-admin / manage.py):
# Django permette di estendere manage.py con comandi custom sottoclassando
# django.core.management.base.BaseCommand e implementando handle(). Ogni file
# .py dentro <app>/management/commands/ diventa automaticamente disponibile
# come `python manage.py <nome_file>` (qui: `python manage.py popola_db`).
# È il meccanismo idiomatico per script "una tantum" o ripetibili legati al
# dominio dell'applicazione (seed di dati, migrazioni di dati, task
# amministrativi), alternativo a script Python sciolti perché ha accesso
# automatico all'intero ambiente Django già configurato (modelli, ORM,
# settings) tramite `python manage.py`.
#
# Il comando genera un dataset dimostrativo completo e IDEMPOTENTE: usa
# sistematicamente get_or_create() invece di create(), quindi può essere
# rieseguito più volte senza generare duplicati (se il record esiste già,
# get_or_create() lo recupera senza ricrearlo).
# =============================================================================
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone
from datetime import timedelta

from escursione.models import ZonaGeografica, Equipaggiamento, Escursione, Uscita, Prenotazione, FotoGalleria
from recensioni.models import Recensione
from core.constants import GRUPPO_GUIDE, GRUPPO_ESCURSIONISTI


class Command(BaseCommand):
    help = 'Popola il database con dati, escursioni, gallerie e utenti fittizi per il collaudo'

    def handle(self, *args, **kwargs):
        # ---------------------------------------------------------------
        # 1. ZONE GEOGRAFICHE ED EQUIPAGGIAMENTO (tabelle di lookup)
        # ---------------------------------------------------------------
        zone = [
            'Abruzzo', 'Basilicata', 'Calabria', 'Campania', 'Emilia-Romagna',
            'Friuli-Venezia Giulia', 'Lazio', 'Liguria', 'Lombardia', 'Marche',
            'Molise', 'Piemonte', 'Puglia', 'Sardegna', 'Sicilia', 'Toscana',
            'Trentino-Alto Adige', 'Umbria', 'Valle d\'Aosta', 'Veneto'
        ]

        equipaggiamenti = [
            'Scarponi da trekking', 'Zaino 30L', 'Borraccia termica 1L',
            'Giacca a vento in Gore-Tex', 'Lampada frontale', 'Casco omologato',
            'Imbrago', 'Set da ferrata', 'Guanti da ferrata',
            'Bastoncini telescopici', 'Ramponi e Piccozza'
        ]

        for nome_zona in zone:
            ZonaGeografica.objects.get_or_create(nome=nome_zona)

        for nome_eq in equipaggiamenti:
            Equipaggiamento.objects.get_or_create(nome=nome_eq)

        self.stdout.write(self.style.SUCCESS('Zone ed equipaggiamenti caricati.'))

        # ---------------------------------------------------------------
        # 2. GRUPPI DI SISTEMA (ruoli applicativi)
        # ---------------------------------------------------------------
        # Si usano le costanti centralizzate di core/constants.py invece di
        # stringhe letterali, così che un'eventuale rinomina dei gruppi resti
        # governata da un unico punto in tutto il progetto.
        guida_group, _ = Group.objects.get_or_create(name=GRUPPO_GUIDE)
        esc_group, _ = Group.objects.get_or_create(name=GRUPPO_ESCURSIONISTI)

        # ---------------------------------------------------------------
        # 3. UTENTI DI TEST (1 Guida, 8 Escursionisti)
        # ---------------------------------------------------------------
        guida_test, created = User.objects.get_or_create(username='mario_guida', email='guida@waypoint.it')
        if created:
            guida_test.set_password('password123')
            guida_test.save()
            guida_test.groups.add(guida_group)

        escursionisti_test = []
        for i in range(1, 9):
            utente, created = User.objects.get_or_create(
                username=f'escursionista_{i}',
                email=f'escursionista{i}@waypoint.it'
            )
            if created:
                utente.set_password('password123')
                utente.save()
                utente.groups.add(esc_group)
            escursionisti_test.append(utente)

        self.stdout.write(self.style.SUCCESS('Utenti di test creati (1 Guida, 8 Escursionisti).'))

        # ---------------------------------------------------------------
        # 4. ESCURSIONI DIMOSTRATIVE ORIGINALI (1 e 2)
        # ---------------------------------------------------------------
        # Calibrate apposta per mostrare sia il caso "posti disponibili" sia
        # il caso "sold out", utile per collaudare a vista lista d'attesa e
        # notifiche senza dover popolare i dati manualmente dall'interfaccia.
        zona_vda = ZonaGeografica.objects.get(nome='Valle d\'Aosta')
        zona_abruzzo = ZonaGeografica.objects.get(nome='Abruzzo')
        eq_base1 = Equipaggiamento.objects.get(nome='Scarponi da trekking')
        eq_base2 = Equipaggiamento.objects.get(nome='Zaino 30L')

        escursione_vuota, _ = Escursione.objects.get_or_create(
            titolo="Traversata del Gran Paradiso",
            defaults={
                'guida': guida_test,
                'zona_geografica': zona_vda,
                'punto_di_ritrovo': "Rifugio Vittorio Emanuele II",
                'latitudine': 45.5186,
                'longitudine': 7.2311,
                'descrizione': "Un maestoso percorso d'alta quota all'interno del Parco Nazionale del Gran Paradiso. Attualmente ci sono posti disponibili.",
                'dislivello': 850,
                'difficolta': 'E',
                'foto_copertina': 'escursione/copertine/default_trekking.jpg',
                'approvata': True
            }
        )
        escursione_vuota.equipaggiamento.add(eq_base1, eq_base2)

        escursione_piena, _ = Escursione.objects.get_or_create(
            titolo="Anello del Corno Grande",
            defaults={
                'guida': guida_test,
                'zona_geografica': zona_abruzzo,
                'punto_di_ritrovo': "Campo Imperatore - Osservatorio",
                'latitudine': 42.4430,
                'longitudine': 13.5586,
                'descrizione': "La vetta più alta degli Appennini. Questo evento è completamente esaurito per testare il sistema di accodamento e le notifiche email.",
                'dislivello': 1100,
                'difficolta': 'EE',
                'foto_copertina': 'escursione/copertine/default_trekking2.jpg',
                'approvata': True
            }
        )
        escursione_piena.equipaggiamento.add(eq_base1, eq_base2)

        # ---------------------------------------------------------------
        # 5. USCITE E PRENOTAZIONI ORIGINALI
        # ---------------------------------------------------------------
        data_base = timezone.now() + timedelta(days=14)

        uscita_vuota, _ = Uscita.objects.get_or_create(
            escursione=escursione_vuota,
            data_ritrovo=data_base,
            defaults={'posti_totali': 5, 'posti_occupati': 0}
        )

        uscita_piena, _ = Uscita.objects.get_or_create(
            escursione=escursione_piena,
            data_ritrovo=data_base + timedelta(days=7),
            defaults={'posti_totali': 5, 'posti_occupati': 5}
        )

        for utente in escursionisti_test[:5]:
            Prenotazione.objects.get_or_create(escursionista=utente, uscita=uscita_piena,
                                               defaults={'stato': 'confermata'})

        # ---------------------------------------------------------------
        # 6. GALLERIA FOTOGRAFICA ORIGINALE
        # ---------------------------------------------------------------
        for i in range(3):
            FotoGalleria.objects.get_or_create(escursione=escursione_vuota,
                                               immagine=f'escursione/galleria/trekking_{i}.jpg')
            FotoGalleria.objects.get_or_create(escursione=escursione_piena,
                                               immagine=f'escursione/galleria/trekking2_{i}.jpg')

        # =================================================================
        # 7. CINQUE ITINERARI AVANZATI AGGIUNTIVI (Escursioni da 3 a 7)
        # =================================================================
        self.stdout.write("Generazione dei 5 nuovi Itinerari avanzati...")
        oggi = timezone.now()

        dati_escursioni = [
            {
                'num': 3, 'titolo': "Giro delle Tre Cime di Lavaredo", 'zona': 'Veneto', 'difficolta': 'E',
                'dislivello': 400,
                'descrizione': "Uno degli itinerari più iconici e spettacolari delle Dolomiti, Patrimonio dell'Umanità UNESCO. Il percorso circolare offre viste mozzafiato sui tre massicci rocciosi da ogni angolazione."
            },
            {
                'num': 4, 'titolo': "Ascesa ai Crateri dell'Etna", 'zona': 'Sicilia', 'difficolta': 'EE',
                'dislivello': 1100,
                'descrizione': "Trekking impegnativo e surreale sulle pendici del vulcano attivo più alto d'Europa. Si cammina tra colate laviche recenti, fumarole e deserti di cenere vulcanica."
            },
            {
                'num': 5, 'titolo': "Sentiero degli Dei", 'zona': 'Campania', 'difficolta': 'T', 'dislivello': 200,
                'descrizione': "Panoramica passeggiata a picco sul mare della Costiera Amalfitana. Sospeso tra cielo e mare, il sentiero attraversa terrazzamenti, boschi di macchia mediterranea e antichi borghi."
            },
            {
                'num': 6, 'titolo': "Traversata del Supramonte", 'zona': 'Sardegna', 'difficolta': 'EE',
                'dislivello': 950,
                'descrizione': "Avventura selvaggia nel cuore della Sardegna. Gole profonde, foreste secolari e antichi ovili dei pastori fanno da cornice a questo itinerario tecnico e isolato."
            },
            {
                'num': 7, 'titolo': "Tappa sulla Via degli Dei", 'zona': 'Emilia-Romagna', 'difficolta': 'E',
                'dislivello': 600,
                'descrizione': "Un segmento del famoso cammino che collega Bologna a Firenze attraversando l'Appennino Tosco-Emiliano. Si cammina tra boschi di faggi e antichi selciati di epoca romana."
            }
        ]

        escursioni_avanzate = []
        for dati in dati_escursioni:
            num = dati['num']
            zona_geo = ZonaGeografica.objects.get(nome=dati['zona'])

            esc, _ = Escursione.objects.get_or_create(
                titolo=dati['titolo'],
                defaults={
                    'guida': guida_test,
                    'zona_geografica': zona_geo,
                    'punto_di_ritrovo': "Punto Base",
                    'latitudine': 40.0 + num,  # Coordinate fittizie, solo per evitare errori sulla mappa
                    'longitudine': 10.0 + num,
                    'descrizione': dati['descrizione'],
                    'difficolta': dati['difficolta'],
                    'dislivello': dati['dislivello'],
                    'approvata': True,
                    'foto_copertina': f"escursione/copertine/default_trekking{num}.jpg"
                }
            )
            esc.equipaggiamento.add(eq_base1)
            escursioni_avanzate.append(esc)

            FotoGalleria.objects.get_or_create(
                escursione=esc,
                immagine=f"escursione/galleria/trekking{num}_0.jpg"
            )

        # =================================================================
        # 8. USCITE E PRENOTAZIONI COMPLESSE (coprono tutti i casi d'uso)
        # =================================================================

        # Escursione 3 (Tre Cime): 1 Passata (piena, per testare lo sblocco
        # delle recensioni post-evento), 1 Futura (quasi piena).
        u3_passata, _ = Uscita.objects.get_or_create(escursione=escursioni_avanzate[0],
                                                     data_ritrovo=oggi - timedelta(days=10),
                                                     defaults={'posti_totali': 5, 'posti_occupati': 5})
        u3_futura, _ = Uscita.objects.get_or_create(escursione=escursioni_avanzate[0],
                                                    data_ritrovo=oggi + timedelta(days=15),
                                                    defaults={'posti_totali': 5, 'posti_occupati': 4})

        for u in escursionisti_test[:5]:
            Prenotazione.objects.get_or_create(escursionista=u, uscita=u3_passata, defaults={'stato': 'confermata'})
        for u in escursionisti_test[:4]:
            Prenotazione.objects.get_or_create(escursionista=u, uscita=u3_futura, defaults={'stato': 'confermata'})

        # Escursione 4 (Etna): lasciata intenzionalmente senza date, per
        # testare che la Home Page gestisca correttamente un'escursione priva
        # di "prossima_data" (annotate con Min restituisce None).

        # Escursione 5 (Sentiero degli Dei): 3 date future vuote (per testare
        # più date sulla stessa escursione)...
        Uscita.objects.get_or_create(escursione=escursioni_avanzate[2], data_ritrovo=oggi + timedelta(days=5),
                                     defaults={'posti_totali': 15})
        Uscita.objects.get_or_create(escursione=escursioni_avanzate[2], data_ritrovo=oggi + timedelta(days=12),
                                     defaults={'posti_totali': 15})
        Uscita.objects.get_or_create(escursione=escursioni_avanzate[2], data_ritrovo=oggi + timedelta(days=19),
                                     defaults={'posti_totali': 15})

        # ...più UNA data passata con 3 iscritti confermati: senza questa,
        # "Sentiero degli Dei" (l'unica escursione di difficoltà Turistico in
        # tutto il catalogo demo) resterebbe un vicolo cieco per il sistema di
        # raccomandazione (nessuna storia da cui dedurre "utenti simili") e
        # non avrebbe mai recensioni, essendo l'unica sua uscita realmente
        # trascorsa con partecipanti.
        u5_passata, _ = Uscita.objects.get_or_create(
            escursione=escursioni_avanzate[2],
            data_ritrovo=oggi - timedelta(days=20),
            defaults={'posti_totali': 15, 'posti_occupati': 3}
        )
        for u in escursionisti_test[5:8]:
            Prenotazione.objects.get_or_create(escursionista=u, uscita=u5_passata, defaults={'stato': 'confermata'})

        # Escursione 6 (Supramonte): piena, con 3 utenti in lista d'attesa
        # (per testare direttamente il flusso di accodamento).
        u6_futura, _ = Uscita.objects.get_or_create(escursione=escursioni_avanzate[3],
                                                    data_ritrovo=oggi + timedelta(days=8),
                                                    defaults={'posti_totali': 3, 'posti_occupati': 3})
        for u in escursionisti_test[0:3]:
            Prenotazione.objects.get_or_create(escursionista=u, uscita=u6_futura, defaults={'stato': 'confermata'})
        for u in escursionisti_test[5:8]:
            Prenotazione.objects.get_or_create(escursionista=u, uscita=u6_futura, defaults={'stato': 'attesa'})

        # Escursione 7 (Via degli Dei): 1 data futura con posti ampiamente
        # disponibili, per il caso "prenotazione semplice".
        u7_futura, _ = Uscita.objects.get_or_create(escursione=escursioni_avanzate[4],
                                                    data_ritrovo=oggi + timedelta(days=25),
                                                    defaults={'posti_totali': 20, 'posti_occupati': 1})
        Prenotazione.objects.get_or_create(escursionista=escursionisti_test[7], uscita=u7_futura,
                                           defaults={'stato': 'confermata'})

        # =================================================================
        # 9. RECENSIONI DIMOSTRATIVE (rating, reputazione, moderazione)
        # =================================================================
        # Senza dati qui, le due property Escursione.punteggio_medio e
        # Escursione.punteggio_guida restituirebbero sempre 0.0 (nessuna
        # recensione da cui calcolare una media), e non ci sarebbe modo di
        # collaudare a vista né la risposta della guida né il flusso di
        # segnalazione/moderazione dell'amministratore. Creiamo quindi
        # recensioni solo per le uscite REALMENTE passate con partecipanti
        # (Tre Cime e, ora, Sentiero degli Dei): recensire un'escursione
        # futura o senza partecipazione confermata violerebbe la stessa
        # regola imposta da recensioni/views.py -> crea_recensione.
        self.stdout.write("Generazione recensioni dimostrative...")

        # --- Recensioni per "Giro delle Tre Cime di Lavaredo" (u3_passata) ---
        recensioni_tre_cime = [
            {
                'utente': escursionisti_test[0], 'voto': 5,
                'testo': "Panorama pazzesco, guida molto preparata e attenta alla sicurezza. Consigliatissimo!",
                # Su questa recensione simuliamo anche la risposta ufficiale della guida.
                'risposta_guida': "Grazie mille per il feedback, è stato un piacere accompagnarvi! Alla prossima uscita.",
            },
            {
                'utente': escursionisti_test[1], 'voto': 4,
                'testo': "Percorso impegnativo ma gestito bene dalla guida. Qualche sosta in più non avrebbe guastato.",
            },
            {
                'utente': escursionisti_test[2], 'voto': 5,
                'testo': "Esperienza fantastica, tornerò sicuramente per altre escursioni con questa guida.",
            },
            {
                'utente': escursionisti_test[3], 'voto': 2,
                'testo': "Ritrovo poco chiaro e partenza in ritardo di mezz'ora. Il percorso in sé era bellissimo.",
                # Segnaliamo questa recensione come "già segnalata": è pronta per
                # collaudare da /admin/ le azioni "Applica avvertimento"/"Applica ban".
                'segnalata': True,
            },
            {
                'utente': escursionisti_test[4], 'voto': 4,
                'testo': "Bella giornata, gruppo numeroso ma ben gestito.",
            },
        ]
        for dati in recensioni_tre_cime:
            Recensione.objects.get_or_create(
                escursione=escursioni_avanzate[0],
                autore=dati['utente'],
                defaults={
                    'voto': dati['voto'],
                    'testo': dati['testo'],
                    'risposta_guida': dati.get('risposta_guida', ''),
                    'segnalata': dati.get('segnalata', False),
                }
            )

        # --- Recensioni per "Sentiero degli Dei" (u5_passata) ---
        recensioni_sentiero_dei = [
            {'utente': escursionisti_test[5], 'voto': 5, 'testo': "Vista sulla Costiera Amalfitana da togliere il fiato, adatto anche a chi non è allenatissimo."},
            {'utente': escursionisti_test[6], 'voto': 4, 'testo': "Sentiero ben segnalato, borghi bellissimi lungo il percorso."},
            {'utente': escursionisti_test[7], 'voto': 3, 'testo': "Bello ma molto affollato in questo periodo dell'anno."},
        ]
        for dati in recensioni_sentiero_dei:
            Recensione.objects.get_or_create(
                escursione=escursioni_avanzate[2],
                autore=dati['utente'],
                defaults={'voto': dati['voto'], 'testo': dati['testo']}
            )

        self.stdout.write(
            self.style.SUCCESS('Tutto pronto! Escursioni, gallerie, prenotazioni e recensioni generate con successo.'))
