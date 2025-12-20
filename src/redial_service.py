import sys
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


def update_max_list_size(current_size):
    try:
        max_str = kamailio.htable.sht_get(HT_KPI, 'max_list_size')
        max_val = int(max_str) if max_str else 0
        if current_size > max_val:
            kamailio.htable.sht_sets(HT_KPI, 'max_list_size', str(current_size))
    except Exception:
        pass


# ----  ----


# ---- Default Initialisation ----
def mod_init():
    kamailio.info('Redial 2.0 Service Loaded')
    try:
        if kamailio.htable.sht_get(HT_KPI, 'total_activations') is None:
            kamailio.htable.sht_sets(HT_KPI, 'total_activations', '0')
            kamailio.htable.sht_sets(HT_KPI, 'active_users_now', '0')
            kamailio.htable.sht_sets(HT_KPI, 'max_list_size', '0')
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
    # to_domain = kamailio.pv.get('$rd')

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
    elif method == 'CANCEL':
        return handle_cancel()
    elif method == 'BYE':
        return handle_bye()

    kamailio.sl.send_reply(405, 'Method Not Allowed')
    return 1


def handle_ack():
    return kamailio.tm.t_relay()


def handle_cancel():
    return kamailio.tm.t_relay()


def handle_bye():
    return kamailio.tm.t_relay()


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
        return -1

    cmd_parts = body.strip().split()
    command = cmd_parts[0].upper()

    user_data_str = kamailio.htable.sht_get(HT_AOR, f_user)
    if not user_data_str:
        kamailio.sl.send_reply(403, 'User not registered')
        return -1
    user_data = json.loads(user_data_str)

    if command == 'ACTIVATE':
        targets = cmd_parts[1:]

        if user_data.get('state') != 'Active':
            update_kpi('active_users_now', 1)
            update_kpi('total_activations', 1)
            update_max_list_size(len(targets))

        user_data['state'] = 'Active'
        user_data['targets'] = targets
        user_data['status'] = 'Available'
        kamailio.htable.sht_sets(HT_AOR, f_user, json.dumps(user_data))
        kamailio.info(f'SERVICE: {f_user} Activated Redial\n')
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
        kamailio.sl.send_reply(400, 'Unknown Command - [ACTIVATE / DEACTIVATE]')

    return 1


def handle_invite():
    caller = kamailio.pv.get('$fU')
    callee = kamailio.pv.get('$rU')

    kamailio.info(f'INVITE: Attempt {caller} -> {callee}\n')

    # Block if callee already OnCall
    callee_data_str = kamailio.htable.sht_get(HT_AOR, callee)
    if callee_data_str:
        t_data = json.loads(callee_data_str)
        if t_data.get('status') == 'OnCall':
            kamailio.info(f'INVITE: {callee} is OnCall\n')
            kamailio.sl.send_reply(486, 'Busy Here')
            return 1

    # Check if Caller has Callee in their Redial List
    caller_data_str = kamailio.htable.sht_get(HT_AOR, caller)
    if caller_data_str:
        caller_data = json.loads(caller_data_str)
        if caller_data.get('state') == 'Active' and callee in caller_data.get('targets', []):
            # Redial arming
            kamailio.pv.seti('$avp(redial_count)', 0)
            kamailio.tm.t_on_failure('app_failure_route')

    # Create dialog
    kamailio.setflag(4)

    # Store dialog variables
    kamailio.pv.sets('$dlg_var(caller)', caller)
    kamailio.pv.sets('$dlg_var(callee)', callee)

    kamailio.registrar.lookup('location')
    kamailio.tm.t_relay()
    return 1


def cleanup_on_bye(msg):
    caller = kamailio.pv.get('$dlg_var(caller)')
    callee = kamailio.pv.get('$dlg_var(callee)')

    kamailio.info(f'DIALOG: Ended {caller} <-> {callee}\n')

    if caller:
        update_user_status(caller, 'Available')
    if callee:
        update_user_status(callee, 'Available')
    return 1


# TODO: this is not triggering
def dlg_end(msg):
    caller = kamailio.pv.get('$dlg_var(caller)')
    callee = kamailio.pv.get('$dlg_var(callee)')

    kamailio.info(f'DIALOG: Ended {caller} <-> {callee}\n')

    update_user_status(caller, 'Available')
    update_user_status(callee, 'Available')

    return 1


def app_reply_route(msg):
    reply_status = str(kamailio.pv.get('$rs'))
    method = kamailio.pv.get('$cs')

    kamailio.info(f'app_reply_route triggered status[{reply_status}] method[{method}]\n')
    # Detect Call Answer (200 OK to INVITE)
    if reply_status == '200':
        caller = kamailio.pv.get('$dlg_var(caller)')
        callee = kamailio.pv.get('$dlg_var(callee)')

        kamailio.info(f'DIALOG: Established {caller} <-> {callee}\n')

        update_user_status(caller, 'OnCall')
        update_user_status(callee, 'OnCall')

    return 1


def app_failure_route(msg):
    failure_status = str(kamailio.pv.get('$rs'))

    should_redial = False

    # Redial on Network Errors (408, 480, 500, 503)
    # Also redial on call reject/busy (486)
    if failure_status in ['408', '480', '486', '503', '500']:
        should_redial = True
        kamailio.info(f'FAILURE: Network/Timeout error ({failure_status})\n')
    elif failure_status == '486':
        kamailio.info('FAILURE: Destination Busy (486)\n')
        should_redial = True

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
