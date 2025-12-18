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
    from_user = kamailio.pv.get('$fU')

    kamailio.info(f'Processing {method} from {from_uri}\n')

    # Handle REGISTER
    if method == 'REGISTER':
        if from_domain == ACME_DOMAIN:
            # TODO: fix DEREGISTER
            # Check for Expires header to detect Unregister/Deregister
            expires = kamailio.pv.get("$hdr(Expires)")
            
            # If Expires is 0, the user wants to log out
            if expires == '0':
                # Setting a htable entry to $null removes it
                kamailio.pv.sets(f"$sht(loc=>{from_user})", "$null")
                kamailio.info(f"REGISTER: Deregistered (Removed) {from_user}\n")
                kamailio.sl.send_reply(200, 'OK')
                return 1

            # Otherwise, it's a login/refresh
            src_ip = kamailio.pv.get('$si')
            src_port = kamailio.pv.get('$sp')
            contact_uri = f'sip:{from_user}@{src_ip}:{src_port}'
            
            kamailio.pv.sets(f'$sht(loc=>{from_user})', contact_uri)
            
            kamailio.info(f'REGISTER: Authorized & Saved {from_user} -> {contact_uri}\n')
            kamailio.sl.send_reply(200, 'OK')
        else:
            kamailio.warn(f'REGISTER: Attempt from invalid domain {from_domain}\n')
            kamailio.sl.send_reply(403, 'Forbidden')
        return 1

    # Handle INVITE
    if method == 'INVITE':
        if from_domain != ACME_DOMAIN:
            kamailio.warn(f'INVITE: Request from unauthorized domain: {from_domain}\n')
            kamailio.sl.send_reply(403, 'Forbidden')
            return 1

        target_user = kamailio.pv.get('$rU')
        target_uri = kamailio.pv.get(f'$sht(loc=>{target_user})')
        
        if target_uri:
            kamailio.info(f'INVITE: Found user {target_user} at {target_uri}\n')
            kamailio.pv.sets('$ru', target_uri)
            kamailio.rr.record_route()
            kamailio.tm.t_on_failure('app_failure_route')
            kamailio.tm.t_relay()
            return 1
        else:
            kamailio.warn(f'INVITE: User {target_user} not found in htable\n')
            kamailio.sl.send_reply(404, 'User Not Found')
            return 1

    # Handle In-Dialog (ACK, BYE)
    if kamailio.rr.loose_route() == 1:
        kamailio.tm.t_relay()
        return 1

    if method == 'ACK':
        kamailio.tm.t_relay()
        return 1

    return 1

def app_failure_route(msg):
    status = kamailio.pv.get('$rs')
    kamailio.info(f'Failure route triggered. Status: {status}\n')
    return 1
