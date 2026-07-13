# =============================================================================
# APP "core" — MOTORE DI RICERCA E HOMEPAGE PUBBLICA
# =============================================================================
# Questa è l'unica vista dell'app core: la homepage pubblica di WayPoint.
# Non richiede autenticazione (è raggiungibile da un utente anonimo, come
# previsto dalla traccia: "Gli utenti anonimi possono visualizzare le
# escursioni disponibili filtrandole per vari criteri").
#
# TEORIA — QuerySet "lazy" di Django:
# Ogni chiamata a .filter()/.annotate()/.order_by() su un QuerySet NON esegue
# immediatamente una query SQL: costruisce incrementalmente un oggetto che
# rappresenta l'interrogazione. La query viene tradotta in SQL e inviata al
# database solo quando il QuerySet viene effettivamente "valutato" (iterato in
# un ciclo for, convertito in lista, passato al Paginator, ecc.). Questo è ciò
# che permette, nella funzione home() qui sotto, di comporre filtri opzionali
# uno via l'altro (if ricerca: ..., if difficolta_scelta: ...) senza pagare il
# costo di più interrogazioni separate: alla fine viene eseguita una singola
# query SQL, con tutte le condizioni combinate in un'unica clausola WHERE.
# =============================================================================

from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q, Min, F
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from escursione.models import Escursione


def home(request):
    """
    Homepage pubblica: mostra il catalogo delle escursioni APPROVATE dagli
    amministratori, con un motore di ricerca a filtri multipli e combinabili
    (testo libero, difficoltà, dislivello massimo, data minima, disponibilità
    posti) e impaginazione dei risultati.

    Requisito di traccia coperto: "Il sistema deve consentire la ricerca
    avanzata delle escursioni in base a determinate caratteristiche. I
    risultati di ricerca devono mostrare immediatamente la disponibilità di
    posti e il livello di difficoltà."
    """

    # -------------------------------------------------------------------
    # 1. QUERYSET DI BASE + AGGREGAZIONE (annotate)
    # -------------------------------------------------------------------
    # filter(approvata=True) è la prima condizione applicata, e non è mai
    # facoltativa: garantisce che un'escursione ancora in attesa di
    # approvazione da parte di un amministratore non compaia MAI nel catalogo
    # pubblico, indipendentemente da quali altri filtri l'utente selezioni.
    # Questo implementa il flusso di moderazione della traccia ("Gli
    # Amministratori possono approvare la creazione delle escursioni").
    #
    # TEORIA — annotate() e funzioni di aggregazione (Min):
    # annotate() aggiunge, per OGNI riga del risultato, un valore calcolato
    # con una funzione di aggregazione SQL (qui Min, ma potrebbero essere
    # Avg, Count, Max, Sum...). Qui calcoliamo "prossima_data": la più vicina
    # tra le date future (data_ritrovo > adesso) delle Uscite collegate a
    # questa Escursione. Il parametro filter=Q(...) dentro Min() applica un
    # filtro SOLO al calcolo dell'aggregazione (le date passate non entrano
    # nel calcolo del minimo), senza escludere l'intera riga Escursione dal
    # risultato: un'escursione con sole uscite passate compare comunque, ma
    # con prossima_data=None.
    lista_escursioni = Escursione.objects.filter(approvata=True).annotate(
        prossima_data=Min(
            'uscite_programmate__data_ritrovo',
            filter=Q(uscite_programmate__data_ritrovo__gt=timezone.now())
        )
    )

    # -------------------------------------------------------------------
    # 2. LETTURA E SANIFICAZIONE DEI PARAMETRI GET
    # -------------------------------------------------------------------
    # I filtri arrivano come querystring (?q=...&difficolta=...&...): sono
    # tutti facoltativi, quindi request.GET.get(chiave, '') restituisce una
    # stringa vuota se il parametro non è presente. Il .replace('None', '')
    # ripulisce un artefatto tipico dei template Django: se un campo del form
    # di ricerca non è valorizzato, alcuni browser/template inviano la stringa
    # letterale "None" anziché ometterlo; qui la neutralizziamo esplicitamente
    # prima di usarla in un confronto.
    ricerca = request.GET.get('q', '').replace('None', '').strip()
    difficolta_scelta = request.GET.get('difficolta', '').replace('None', '').strip()
    dislivello_max = request.GET.get('dislivello', '').replace('None', '').strip()
    data_da = request.GET.get('data_da', '').replace('None', '').strip()
    solo_disponibili = request.GET.get('solo_disponibili', '').replace('None', '').strip()

    # -------------------------------------------------------------------
    # 3. FILTRI IN CASCATA (ognuno è condizionale e opzionale)
    # -------------------------------------------------------------------

    # --- Filtro testuale: titolo OPPURE descrizione ---
    # TEORIA — oggetti Q: filter(a=1, b=2) equivale a un AND implicito tra le
    # condizioni; per esprimere un OR (necessario qui: "titolo contiene X"
    # OPPURE "descrizione contiene X") serve combinare due oggetti Q con
    # l'operatore | (OR bit a bit, ridefinito da Django per i Q object).
    # __icontains esegue un LIKE case-insensitive.
    if ricerca:
        lista_escursioni = lista_escursioni.filter(
            Q(titolo__icontains=ricerca) | Q(descrizione__icontains=ricerca)
        )

    # --- Filtro difficoltà: whitelist anti-injection ---
    # Anziché fidarsi ciecamente del valore ricevuto dall'utente, lo si
    # confronta con l'insieme dei valori ammessi definiti nel modello stesso
    # (Escursione._meta.get_field('difficolta').choices): se un utente
    # malintenzionato manipolasse l'URL con un valore arbitrario (?difficolta=
    # <script>...), il filtro verrebbe semplicemente ignorato invece di
    # generare una query con un valore non previsto.
    difficolta_valide = {val for val, _ in Escursione._meta.get_field('difficolta').choices}
    if difficolta_scelta in difficolta_valide:
        lista_escursioni = lista_escursioni.filter(difficolta=difficolta_scelta)

    # --- Filtro dislivello massimo ---
    # .isdigit() verifica che la stringa sia composta solo da cifre prima di
    # convertirla con int(): evita un ValueError (e quindi un errore 500) se
    # l'utente inserisce testo non numerico nel campo.
    if dislivello_max.isdigit():
        lista_escursioni = lista_escursioni.filter(dislivello__lte=int(dislivello_max))

    # --- Filtro data minima di partenza ---
    # __date estrae solo la parte "data" (senza l'ora) dal campo DateTimeField
    # data_ritrovo, per confrontarla con la data (senza ora) scelta dall'utente.
    if data_da:
        lista_escursioni = lista_escursioni.filter(
            uscite_programmate__data_ritrovo__date__gte=data_da
        )

    # --- Filtro "solo posti disponibili" ---
    # TEORIA — F expressions: F('campo') permette di riferirsi al valore di
    # un'altra colonna DELLA STESSA RIGA direttamente nella query SQL, senza
    # doverlo prima caricare in Python. Qui confrontiamo due colonne della
    # stessa Uscita (posti_occupati < posti_totali) interamente lato database:
    # è più efficiente e soprattutto più corretto di caricare tutte le righe e
    # filtrarle in Python, perché il confronto avviene in modo atomico rispetto
    # allo stato del database al momento della query.
    # Nota: il confronto è fatto sulla stringa esatta 'true' (non su un valore
    # "truthy" generico) per evitare che un valore imprevisto (es. 'false',
    # '0') attivi comunque il filtro per errore.
    if solo_disponibili == 'true':
        lista_escursioni = lista_escursioni.filter(
            uscite_programmate__data_ritrovo__gt=timezone.now(),
            uscite_programmate__posti_occupati__lt=F('uscite_programmate__posti_totali')
        )

    # -------------------------------------------------------------------
    # 4. DISTINCT E ORDINAMENTO
    # -------------------------------------------------------------------
    # .distinct() è indispensabile ogni volta che il queryset attraversa una
    # relazione 1-a-N (qui: uscite_programmate) tramite un filter(): se
    # un'escursione ha più uscite che soddisfano una condizione, l'SQL
    # generato produce un JOIN che duplica la riga Escursione una volta per
    # ogni Uscita corrispondente. Questo può accadere con QUALSIASI filtro
    # basato su uscite_programmate (filtro data, filtro disponibilità), non
    # solo con "solo_disponibili": per questo il blocco è ora POSIZIONATO FUORI
    # da ogni "if" dei filtri, così da applicare distinct()/order_by() sempre,
    # indipendentemente da quali filtri risultino attivi in questa richiesta.
    # order_by(F('prossima_data').asc(nulls_last=True), '-id'): ordina prima
    # per data più imminente; nulls_last=True relega in fondo le escursioni
    # che non hanno (ancora) una data futura programmata, anziché farle
    # comparire per prime (comportamento di default di SQLite per i NULL in
    # ordine crescente). A parità di data, '-id' mostra prima gli inserimenti
    # più recenti.
    lista_escursioni = lista_escursioni.distinct().order_by(
        F('prossima_data').asc(nulls_last=True),
        '-id'
    )

    # -------------------------------------------------------------------
    # 5. IMPAGINAZIONE (Paginator)
    # -------------------------------------------------------------------
    # TEORIA — Paginator: suddivide un QuerySet (o qualunque sequenza) in
    # "pagine" di dimensione fissa (qui 6 elementi), valutando pigramente solo
    # gli elementi della pagina richiesta (non l'intero QuerySet), grazie a
    # LIMIT/OFFSET generati automaticamente in SQL.
    #
    # La gestione esplicita delle eccezioni rende la paginazione robusta anche
    # a input malformati digitati manualmente nell'URL da un utente:
    #   - PageNotAnInteger: ?page=testo -> si torna alla pagina 1 (nessun 500).
    #   - EmptyPage: ?page=9999 (oltre il numero di pagine esistenti) -> si
    #     mostra l'ultima pagina disponibile anziché una pagina vuota o un errore.
    # Questa robustezza è verificata esplicitamente da un test automatico
    # (core/tests.py: test_gestione_paginazione_errore_testo).
    paginator = Paginator(lista_escursioni, 6)
    page_number = request.GET.get('page', 1)

    try:
        escursioni_paginate = paginator.page(page_number)
    except PageNotAnInteger:
        escursioni_paginate = paginator.page(1)
    except EmptyPage:
        escursioni_paginate = paginator.page(paginator.num_pages)

    # -------------------------------------------------------------------
    # 6. CONTEXT PER IL TEMPLATE
    # -------------------------------------------------------------------
    # Oltre alla lista impaginata, si passa al template anche il valore
    # "attuale" di ogni filtro: serve a ripopolare i campi del form di ricerca
    # con la scelta fatta dall'utente (altrimenti, cambiando pagina, il form
    # si "dimenticherebbe" i filtri applicati).
    context = {
        'escursioni': escursioni_paginate,
        'ricerca_attuale': ricerca,
        'difficolta_attuale': difficolta_scelta,
        'dislivello_attuale': dislivello_max,
        'data_da_attuale': data_da,
        'solo_disponibili_attuale': solo_disponibili,
    }

    return render(request, 'core/home.html', context)
