import sys  
import logging
import KSR as kamailio

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger('RedialService')

ACME_DOMAIN = 'acme.operador'

# ==================================
# 1. Module Initialization
# ==================================
def mod_init():
    """
    Kamailio calls this function once when loading the script.
    """
    kamailio.info('Redial Service Python Script Loaded Successfully\n')
    return sys.modules[__name__]

def child_init(rank):
    """
    Kamailio calls this for every worker process (UDP workers, timers, etc).
    """
    return 1

# ==================================
# Database Functions
# ==================================
def db_create_redial_list(aor):
    return True

def db_delete_redial_list(aor):
    return True

def db_update_redial_list(aor, new_list):
    return True

def db_get_redial_list(aor):
    return []

# ==================================
# HTTP Handler (sanity check)
# ==================================
def http_route(msg):
    """
    Handle HTTP requests (sanity check)
    """
    LOG.info("Received HTTP request")
    kamailio.xhttp.xhttp_reply(200, "OK", "text/plain", "Redial Service is ALIVE via KEMI Python!\n")
    return 1

# ==================================
# Core SIP Routing Function
# ==================================
def sip_route(msg):
    method = kamailio.pv.get('$rm')
    from_uri = kamailio.pv.get('$fu')
    from_domain = kamailio.pv.get('$fd')

    LOG.info(f'Processing {method} from {from_uri}')

    if from_domain != ACME_DOMAIN:
        LOG.warning(f'Request from unauthorized domain: {from_domain}')
        kamailio.sl.send_reply(403, 'Forbidden - Not an ACME Operator User')
        return 1

    # Handle REGISTER
    if method == 'REGISTER':
        kamailio.registrar.save('location')
        kamailio.sl.send_reply(200, 'OK')
        return 1

    # Handle MESSAGE
    elif method == 'MESSAGE':
        return 1 

    # Handle INVITE
    elif method == 'INVITE':
        if kamailio.registrar.lookup('location') == 1:
            kamailio.tm.t_on_failure('app_failure_route')
            kamailio.tm.t_relay()
            return 1
        else:
            kamailio.sl.send_reply(404, 'Not Found')
            return 1

    return 0


# ==================================
# Failure Route
# ==================================
def app_failure_route(msg):
    status = kamailio.pv.get('$T_fr')
    from_uri = kamailio.pv.get('$fu')
    to_uri = kamailio.pv.get('$ru')

    LOG.info(f'Failure route triggered. Status: {status} for destination: {to_uri}')

    if status in ['486', '408', '603']:
        redial_list = db_get_redial_list(from_uri)
        if to_uri in redial_list:
            LOG.info(f'Destination {to_uri} is in redial list. Triggering re-dial logic.')
            return 1

    kamailio.tm.t_relay()
    return 1
