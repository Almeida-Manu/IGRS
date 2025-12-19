import sys
import KSR as kamailio

ACME_DOMAIN = 'acme.operador'


def mod_init():
    kamailio.info('Redial Service Python Script Loaded Successfully\n')
    return sys.modules[__name__]


def child_init(rank):
    return 1

def app_reply_route(msg):
    status = kamailio.pv.get('$rs')
    method = kamailio.pv.get('$rm')
    kamailio.info(f'REPLY ROUTE: Processing {status} {method} response.\n')
    return 1

def sip_route(msg):
    # Ensure replies go back to the public src IP
    kamailio.force_rport()

    method = kamailio.pv.get('$rm')

    # Handle In-Dialog requests (BYE, ACK, Re-INVITE)
    if kamailio.rr.loose_route() == 1:
        kamailio.tm.t_relay()
        return 1

    # Handle CALL state (ACKs that didn't match loose_route, e.g. 404 ACKs)
    if method == 'ACK':
        kamailio.tm.t_relay()
        return 1

    # Cancel processing if this is a retransmission
    if kamailio.tm.t_check_trans() == 1:
        return 1

    from_uri = kamailio.pv.get('$fu')
    from_domain = kamailio.pv.get('$fd')
    from_user = kamailio.pv.get('$fU')

    kamailio.info(f'Processing {method} from {from_uri}\n')

    # ======================================================
    # Handle REGISTER
    # ======================================================
    if method == 'REGISTER':
        # Only allow register with valid domain
        if from_domain != ACME_DOMAIN:
            kamailio.warn(
                f'REGISTER: Attempt from invalid domain {from_domain}\n'
            )
            kamailio.sl.send_reply(403, 'Forbidden')
            return 1

        # DEREGISTRATION LOGIC
        # Clients deregister by setting Expires: 0 header OR ;expires=0 in Contact
        expires_hdr = kamailio.pv.get('$hdr(Expires)')
        contact_hdr = kamailio.pv.get('$hdr(Contact)')

        is_deregister = False

        if expires_hdr and expires_hdr.strip() == '0':
            is_deregister = True
        elif contact_hdr and 'expires=0' in contact_hdr.lower():
            is_deregister = True

        if is_deregister:
            kamailio.pv.sets(
                f'$sht(loc=>{from_user})', '$null'
            )  # remove from htable
            kamailio.info(f'REGISTER: Deregistered {from_user}\n')
            kamailio.sl.send_reply(200, 'OK')
            return 1

        # REGISTRATION LOGIC
        src_ip = kamailio.pv.get('$si')
        src_port = kamailio.pv.get('$sp')
        proto = kamailio.pv.get('$pr')  # udp/tcp
        contact_uri = f'sip:{from_user}@{src_ip}:{src_port};transport={proto}'
        kamailio.pv.sets(f'$sht(loc=>{from_user})', contact_uri)
        kamailio.info(
            f'REGISTER: Authorized & Saved {from_user} -> {contact_uri}\n'
        )
        kamailio.sl.send_reply(200, 'OK')
        return 1

    # ======================================================
    # Handle INVITE
    # ======================================================
    if method == 'INVITE':
        target_user = kamailio.pv.get('$rU')
        target_uri = kamailio.pv.get(f'$sht(loc=>{target_user})')
        if target_uri:
            kamailio.info(f'INVITE: Found user {target_user} at {target_uri}\n')
            kamailio.pv.sets('$ru', target_uri)
            # Record Route so valid BYEs can pass through later
            kamailio.rr.record_route()
            kamailio.tm.t_on_reply('app_reply_route')
            # Arm failure route to catch 408/500 errors
            kamailio.tm.t_on_failure('app_failure_route')
            kamailio.tm.t_relay()
            return 1
        else:
            kamailio.warn(f'INVITE: User {target_user} not found in htable\n')
            kamailio.sl.send_reply(404, 'User Not Found')
            return 1

    # Handle other methods (e.g. OPTIONS, SUBSCRIBE)
    kamailio.sl.send_reply(405, 'Method Not Allowed')

    return 1


def app_failure_route(msg):
    status = kamailio.pv.get('$rs')
    kamailio.info(f'Failure route triggered. Status: {status}\n')
    return 1
