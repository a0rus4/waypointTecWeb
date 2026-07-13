# =============================================================================
# COSTANTI CONDIVISE DI DOMINIO
# =============================================================================
# i nomi dei gruppi Django ("Guide", "Escursionisti")
# vengono spesso utilizzati.
# se in futuro si decidesse di rinominare
# un gruppo, bisognerebbe modificare la stringa in tutti i punti in cui compare,
#
# =============================================================================

GRUPPO_GUIDE = 'Guide'
GRUPPO_ESCURSIONISTI = 'Escursionisti'

# Termine minimo (in ore) entro cui un escursionista può cancellare una
# prenotazione CONFERMATA prima della data di ritrovo. Oltre questa soglia
# la cancellazione last-minute non è più permessa dall'interfaccia utente,
# implementando il requisito di traccia "cancellazione entro termini stabiliti".
# È un valore di dominio, non un dettaglio di configurazione ambientale, ma lo
# teniamo qui (e richiamato anche da settings.py) per essere riutilizzabile sia
# nelle view sia, potenzialmente, in test e comandi di gestione.
ORE_LIMITE_CANCELLAZIONE = 24
