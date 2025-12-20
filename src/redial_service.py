import sys
import time
import json
import KSR as kamailio


# ---- Configs ----
ACME_DOMAIN = 'acme.operador'
MAX_REDIALS = 3
# Htable
HT_AOR = 'aor'
HT_KPI = 'kpi'
# ----  ----


# ---- Helpers ----
def update_user_status(user, new_status):
    """Updates just the status field of the user's JSON blob"""
    data_str = kamailio.htable.sht_get(HT_AOR, user)
    if not data_str:
        return  # User not registered, ignore

    try:
        data = json.loads(data_str)
        data['status'] = new_status
        kamailio.htable.sht_sets(HT_AOR, user, json.dumps(data))
        kamailio.info(f'STATUS: User {user} -> {new_status}\n')
    except Exception as e:
        kamailio.warn(f'JSON error updating status: {e}\n')


def update_kpi(kpi_name, delta):
    try:
        val_str = kamailio.htable.sht_get(HT_KPI, kpi_name)
        val = int(val_str) if val_str else 0
        new_val = val + delta
        if new_val < 0:
            new_val = 0
        kamailio.htable.sht_sets(HT_KPI, kpi_name, str(new_val))
    except Exception as e:
        kamailio.warn(f'Htable error updating KPI table: {e}\n')


# ----  ----


# ---- Default Initialisation ----
def mod_init():
    kamailio.info('Redial 2.0 Service Loaded')
    try:
        if kamailio.htable.sht_get(HT_KPI, 'total_activations') is None:
            kamailio.htable.sht_sets(HT_KPI, 'total_activations', '0')
            kamailio.htable.sht_sets(HT_KPI, 'active_users_now', '0')
            kamailio.htable.sht_sets(HT_KPI, 'max_list_size', f'{MAX_REDIALS}')
    except Exception as e:
        kamailio.warn(f'ERROR initialising KPIs: {e}')
    return sys.modules[__name__]


def child_init(rank):
    return 1


# ----  ----


# ---- Routing ----
# Main route for SIP connections
def sip_route(msg):
    from_domain = kamailio.pv.get('$fd')
    to_domain = kamailio.pv.get('$rd')

    # Block external domain traffic
    if from_domain != ACME_DOMAIN:
        kamailio.warn(f'ROUTE: Blocked access from {from_domain}\n')
        kamailio.sl.send_reply(403, 'Forbidden - Domain Not Allowed')
        return 1

    # TODO: check is from_domain user service is ACTIVE

    # Routing logic per method
    method = kamailio.pv.get('$rm')
    if method == 'REGISTER':
        return handle_register()
    elif method == 'MESSAGE':
        return handle_message()
    elif method == 'INVITE':
        return handle_invite()
    elif method == 'ACK':
        return handle_ack()
    elif method == 'BYE':
        return handle_bye()
    elif method == 'CANCEL':
        return handle_cancel()

    kamailio.sl.send_reply(405, 'Method Not Allowed')
    return 1


def handle_ack():
    kamailio.tm.t_relay()
    return 1


def handle_cancel():
    kamailio.info(f'CANCEL: {kamailio.pv.get("$ru")}')
    kamailio.tm.t_relay()
    return 1


def handle_bye():
    # Detect Call End
    caller = kamailio.pv.get('$fU')
    callee = kamailio.pv.get('$tU')

    kamailio.info(f'DIALOG: Call Ended {caller} <-> {callee}\n')
    update_user_status(caller, 'Available')
    update_user_status(callee, 'Available')

    kamailio.tm.t_relay()
    return 1


def handle_register():
    user = kamailio.pv.get('$fU')
    expires = kamailio.pv.get('$hdr(Expires)')
    contact = kamailio.pv.get('$hdr(Contact)')

    is_deregister = (expires == '0') or (contact and 'expires=0' in contact.lower())

    if is_deregister:
        kamailio.info(f'DEREGISTER: {user} - Removing Data\n')
        old_data_str = kamailio.htable.sht_get(HT_AOR, user)
        if old_data_str:
            old_data = json.loads(old_data_str)
            if old_data.get('state') == 'Active':
                update_kpi('active_users_now', -1)

        kamailio.htable.sht_rm(HT_AOR, user)
    else:
        if kamailio.htable.sht_get(HT_AOR, user) is None:
            kamailio.info(f'REGISTER: {user}\n')
            initial_state = json.dumps({'state': 'Active', 'targets': [], 'status': 'Available'})
            kamailio.htable.sht_sets(HT_AOR, user, initial_state)
            update_kpi('total_activations', 1)
            update_kpi('active_users_now', 1)

    kamailio.registrar.save('location', 0)
    return 1


# TODO: add test for ACTIVATE/DEACTIVATE in test container
def handle_message():
    r_user = kamailio.pv.get('$rU')
    f_user = kamailio.pv.get('$fU')
    body = kamailio.pv.get('$rb')

    if r_user != 'redial':
        kamailio.sl.send_reply(403, 'Forbidden destination for MESSAGE')
        return -1

    if not body:
        kamailio.sl.send_reply(400, 'Empty Body')
        return 1

    cmd_parts = body.strip().split()
    command = cmd_parts[0].upper()

    user_data_str = kamailio.htable.sht_get(HT_AOR, f_user)
    if not user_data_str:
        kamailio.sl.send_reply(403, 'User not registered')
        return -1
    user_data = json.loads(user_data_str)

    if command == 'ACTIVATE':
        targets = cmd_parts[1:]
        if not targets:
            kamailio.sl.send_reply(400, 'Missing target list')
            return -1

        if user_data.get('state') != 'Active':
            update_kpi('active_users_now', 1)

        user_data['state'] = 'Active'
        user_data['targets'] = targets
        user_data['status'] = 'Available'
        kamailio.htable.sht_sets(HT_AOR, f_user, json.dumps(user_data))

        update_kpi('total_activations', 1)
        current_max = int(kamailio.htable.sht_get(HT_KPI, 'max_list_size') or 0)
        if len(targets) > current_max:
            kamailio.htable.sht_sets(HT_KPI, 'max_list_size', str(len(targets)))

        kamailio.info(f'SERVICE: {f_user} Activated Redial for {targets}\n')
        kamailio.sl.send_reply(200, 'Service Activated')

    elif command == 'DEACTIVATE':
        if user_data.get('state') == 'Active':
            update_kpi('active_users_now', -1)

        user_data['state'] = 'Inactive'
        user_data['targets'] = []
        user_data['status'] = 'Unavailable'
        kamailio.htable.sht_sets(HT_AOR, f_user, json.dumps(user_data))
        kamailio.info(f'SERVICE: {f_user} Deactivated Redial\n')
        kamailio.sl.send_reply(200, 'Service Deactivated')

    else:
        kamailio.sl.send_reply(400, 'Unknown Command')

    return 1


def handle_invite():
    f_user = kamailio.pv.get('$fU')  # Caller
    target_user = kamailio.pv.get('$rU')  # Callee

    # 1. Check if Target is already OnCall
    target_str = kamailio.htable.sht_get(HT_AOR, target_user)
    if target_str:
        try:
            t_data = json.loads(target_str)
            # if target is OnCall, reject immediately (Busy)
            if t_data.get('status') == 'OnCall':
                kamailio.info(f'INVITE: Blocked. {target_user} is OnCall.\n')
                kamailio.sl.send_reply(486, 'Busy Here (OnCall)')
                return 1
        except:
            pass

    # Check Redial Logic Armed
    # We check the CALLER's data. If they have the Redial Service Active
    # AND they are calling one of their targets, we arm the failure route.
    caller_str = kamailio.htable.sht_get(HT_AOR, f_user)
    if caller_str:
        try:
            c_data = json.loads(caller_str)
            if c_data.get('state') == 'Active' and target_user in c_data.get('targets', []):
                kamailio.info(f'SERVICE: Redial ARMED for {f_user} -> {target_user}\n')
                kamailio.pv.seti('$avp(redial_count)', 0)
                kamailio.tm.t_on_failure('app_failure_route')
        except:
            pass

    # Arm the Reply Route to catch the 200 OK (Call Start)
    kamailio.tm.t_on_reply('app_reply_route')

    kamailio.registrar.lookup('location')
    kamailio.tm.t_relay()
    return 1


def app_reply_route(msg):
    status = int(kamailio.pv.get('$rs'))
    method = kamailio.pv.get('$rm')

    # Detect Call Answer (200 OK to INVITE)
    if method == 'INVITE' and status == 200:
        caller = kamailio.pv.get('$fU')
        callee = kamailio.pv.get('$tU')

        kamailio.info(f'DIALOG: Call Established {caller} <-> {callee}\n')
        update_user_status(caller, 'OnCall')
        update_user_status(callee, 'OnCall')

    return 1


def app_failure_route(msg):
    status = kamailio.pv.get('$rs')

    # Redial on Network Errors (408, 480, 500, 503)
    # Dont redial on call reject (486)

    should_redial = False

    if status in ['408', '480', '503', '500']:
        should_redial = True
        kamailio.info(f'FAILURE: Network/Timeout error ({status}). Retry warranted.\n')
    elif status == '486':
        kamailio.info('FAILURE: Destination Busy (486). Stopping Redial.\n')
        should_redial = False

    if should_redial:
        count_obj = kamailio.pv.get('$avp(redial_count)')
        count = int(count_obj) if count_obj else 0

        if count < MAX_REDIALS:
            count += 1
            kamailio.pv.seti('$avp(redial_count)', count)
            kamailio.info(f'SERVICE: Redialing attempt {count}/{MAX_REDIALS}...\n')
            kamailio.tm.t_relay()
            return 1

    return 1
