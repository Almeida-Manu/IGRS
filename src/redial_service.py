import sys  
import KSR as kamailio

ACME_DOMAIN = 'acme.operador'

def mod_init():
    kamailio.info('Redial Service Python Script Loaded Successfully\n')
    return sys.modules[__name__]

def child_init(rank):
    return 1

def sip_route(msg):
    method = kamailio.pv.get('$rm')
    from_uri = kamailio.pv.get('$fu')
    from_domain = kamailio.pv.get('$fd')

    kamailio.info(f'Processing {method} from {from_uri}\n')

    # 1. Handle REGISTER
    if method == 'REGISTER':
        if from_domain == ACME_DOMAIN:
            kamailio.registrar.save('location', 0)
            kamailio.sl.send_reply(200, 'OK')
        else:
            kamailio.sl.send_reply(403, 'Forbidden')
        return 1

    # 2. Handle In-Dialog Requests (ACK, BYE)
    # If the request has a Route header (loose routing), simply relay it.
    if kamailio.rr.loose_route() == 1:
        kamailio.tm.t_relay()
        return 1

    # 3. Handle INVITE (Initial Calls)
    if method == 'INVITE':
        # Check domain security
        if from_domain != ACME_DOMAIN:
            kamailio.warn(f'Request from unauthorized domain: {from_domain}\n')
            kamailio.sl.send_reply(403, 'Forbidden')
            return 1

        # Add Record-Route so Kamailio sees the BYE later
        kamailio.rr.record_route()

        # Lookup location
        if kamailio.registrar.lookup('location') == 1:
            kamailio.tm.t_on_failure('app_failure_route')
            kamailio.tm.t_relay()
        else:
            kamailio.sl.send_reply(404, 'User Not Found')
        return 1

    # 4. Handle any transaction stateful ACKs that didn't match loose_route
    if method == 'ACK':
        kamailio.tm.t_relay()
        return 1

    # Default: drop others
    return 1

def app_failure_route(msg):
    status = kamailio.pv.get('$T_reply_code')
    to_uri = kamailio.pv.get('$ru')

    kamailio.info(f'Failure route triggered. Status: {status} for {to_uri}\n')

    if status in ['486', '408', '603']:
        # Your redial logic here
        pass

    return 1
