import sys
import json
import KSR as kamailio


# ---- Configs ----
ACME_DOMAIN = 'acme.operador'
MAX_REDIALS = 3
MAX_REDIAL_LIST = 5
# Htable
HT_AOR = 'aor'
HT_KPI = 'kpi'
# ----  ----


# ---- Helpers ----
def update_user_status(user, new_status):
    # Update aor htable entry for user for col status
    data_str = kamailio.htable.sht_get(HT_AOR, user)
    if not data_str:
        return
    try:
        data = json.loads(data_str)
        data['status'] = new_status
        kamailio.htable.sht_sets(HT_AOR, user, json.dumps(data))
        kamailio.info(f'STATUS: User {user} -> {new_status}\n')
    except Exception as e:
        kamailio.warn(f'JSON error updating status: {e}\n')


def update_kpi(kpi_name, delta):
    # Update kpi htable entry for col $kpi_data incrementing value by delta
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
    kamailio.info('Redial 2.0 Service Loaded\n')
    # Initialise kpi htable
    try:
        if kamailio.htable.sht_get(HT_KPI, 'total_activations') is None:
            kamailio.htable.sht_sets(HT_KPI, 'total_activations', '0')
            kamailio.htable.sht_sets(HT_KPI, 'active_users_now', '0')
            kamailio.htable.sht_sets(
                HT_KPI, 'max_list_size', f'{MAX_REDIAL_LIST}'
            )
    except Exception as e:
        kamailio.warn(f'ERROR initialising KPIs: {e}')
    return sys.modules[__name__]


def child_init(rank):
    return 1


# ----  ----


# ---- Routing ----
# Main route for SIP connections
def sip_route(msg):
    # Block external domain traffic
    from_domain = kamailio.pv.get('$fd')
    to_domain = kamailio.pv.get('$rd')
    if from_domain != ACME_DOMAIN:
        kamailio.warn(f'ROUTE: Blocked access from {from_domain}\n')
        kamailio.sl.send_reply(403, 'Forbidden - Domain Not Allowed')
        return 1
    if to_domain != ACME_DOMAIN:
        kamailio.warn(f'ROUTE: Blocked access to {to_domain}\n')
        kamailio.sl.send_reply(403, 'Forbidden - Domain Not Allowed')
        return 1

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

    # Handle DEREGISTER default implementations
    is_deregister = (expires == '0') or (
        contact and 'expires=0' in contact.lower()
    )

    # Perform user DEREGISTER
    if is_deregister:
        kamailio.info(f'DEREGISTER: {user}\n')
        update_kpi('active_users_now', -1)
        # Remove user entry as per requirement
        kamailio.htable.sht_rm(HT_AOR, user)
    # Perform user REGISTER
    else:
        if kamailio.htable.sht_get(HT_AOR, user) is None:
            kamailio.info(f'REGISTER: {user}\n')
            initial_user_data = json.dumps(
                {'status': 'Available', 'targets': []}
            )
            kamailio.htable.sht_sets(HT_AOR, user, initial_user_data)
            update_kpi('active_users_now', 1)
            update_kpi('total_activations', 1)

    kamailio.registrar.save('location', 0)
    return 1


def handle_message():
    r_user = kamailio.pv.get('$rU')
    f_user = kamailio.pv.get('$fU')
    body = kamailio.pv.get('$rb')

    # Message to redial@acme.operador
    if r_user != 'redial':
        kamailio.sl.send_reply(403, 'Forbidden destination for MESSAGE')
        return -1

    if not body:
        kamailio.sl.send_reply(400, 'Empty Body')
        return -1

    cmd_parts = body.strip().split()
    if not cmd_parts:
        kamailio.sl.send_reply(400, 'Empty Command')
        return -1
    command = cmd_parts[0].upper()

    # Check if user is registered
    user_data_str = kamailio.htable.sht_get(HT_AOR, f_user)
    if not user_data_str:
        kamailio.sl.send_reply(403, 'User not registered')
        return -1
    user_data = json.loads(user_data_str)

    # Handle ACTIVATE
    if command == 'ACTIVATE':
        targets = cmd_parts[1:]
        if len(targets) + len(user_data['targets']) > MAX_REDIAL_LIST:
            kamailio.sl.send_reply(
                400,
                f'Maximum size for redial list exceeded with this call ({MAX_REDIAL_LIST})',
            )
            return -1

        # Update KPIs if activating redial service
        if len(user_data['targets']) == 0:
            update_kpi('active_users_now', 1)
            update_kpi('total_activations', len(targets))

        # Check if all targets exist in the AOR table
        # Lookup targets in table, if they don't exist it returns None
        for target in targets:
            if not kamailio.htable.sht_get(HT_AOR, target):
                kamailio.sl.send_reply(
                    400, f'Target user "{target}" not found / not registered'
                )
                return -1

        # Perform htable col targets update
        user_data['targets'] = targets
        kamailio.htable.sht_sets(HT_AOR, f_user, json.dumps(user_data))
        kamailio.info(f'SERVICE: {f_user} Activated Redial for {targets}\n')
        kamailio.sl.send_reply(200, 'Service Update Activated')

    # Perform DEACTIVATE
    elif command == 'DEACTIVATE':
        if user_data.get('state') == 'Active':
            update_kpi('active_users_now', -1)

        # Remove targets entry col as per requirements
        user_data['targets'] = []
        kamailio.htable.sht_sets(HT_AOR, f_user, json.dumps(user_data))
        kamailio.info(f'SERVICE: {f_user} Deactivated Redial\n')
        kamailio.sl.send_reply(200, 'Service Deactivated')

    else:
        kamailio.sl.send_reply(
            400,
            'Unknown Command - valid: [ACTIVATE / DEACTIVATE <user_1> <user_2> ...], maximum list size ({MAX_REDIAL_LIST})',
        )

    return 1


def handle_invite():
    caller = kamailio.pv.get('$fU')
    callee = kamailio.pv.get('$rU')

    kamailio.info(f'INVITE: Attempt {caller} -> {callee}\n')


    callee_data_str = kamailio.htable.sht_get(HT_AOR, callee)
    
    # Block if callee is not found in AoR table
    if not callee_data_str:
        kamailio.info(f'INVITE: {callee} was not found\n')
        kamailio.sl.send_reply(404, 'User not found')
        return 1

    # Block if callee is not Available
    if callee_data_str:
        t_data = json.loads(callee_data_str)
        callee_status = t_data.get('status')
        if callee_status != 'Available':
            kamailio.info(f'INVITE: {callee} is {callee_status}\n')
            kamailio.sl.send_reply(486, 'Busy Here')
            return 1

    # Block if caller is not Available (error by spam preventation)
    caller_data_str = kamailio.htable.sht_get(HT_AOR, caller)
    if caller_data_str:
        t_data = json.loads(caller_data_str)
        caller_status = t_data.get('status')
        if caller_status != 'Available':
            kamailio.info(f'INVITE: {caller} is {caller_status}\n')
            kamailio.sl.send_reply(403, 'Forbidden Multiple Calls Detected')
            return 1

    # Check if Caller has Callee in their Redial List
    caller_data_str = kamailio.htable.sht_get(HT_AOR, caller)
    if caller_data_str:
        caller_data = json.loads(caller_data_str)
        kamailio.info(
            f'ARM: {callee} for {caller} target list ({" ".join(target for target in caller_data.get("targets"))})\n'
        )
        if callee in caller_data.get('targets', []):
            # Redial arming
            kamailio.pv.seti('$avp(redial_count)', 0)
            kamailio.tm.t_on_failure('app_redial_route')
        else:
            kamailio.tm.t_on_failure('app_failure_route')

    # TODO: is this code wrong, and why dial_end is not triggering?
    # kamailio.pv.sets('$dlg_var(caller)', caller)
    # kamailio.pv.sets('$dlg_var(callee)', callee)
    # kamailio.setflag(4)
    # kamailio.dialog.dlg_manage()

    # Block incoming calls for involved users during the INVITE process
    update_user_status(caller, 'RoutingCall')
    update_user_status(callee, 'RoutingCall')

    kamailio.registrar.lookup('location')
    kamailio.tm.t_relay()
    return 1


def cleanup_on_bye(msg):
    caller = kamailio.pv.get('$fU')
    callee = kamailio.pv.get('$tU')
    # caller = kamailio.pv.get('$dlg_var(caller)')
    # callee = kamailio.pv.get('$dlg_var(callee)')

    kamailio.info(f'DIALOG: Ended {caller} <-> {callee}\n')

    update_user_status(caller, 'Available')
    update_user_status(callee, 'Available')

    return 1


# TODO: this is not triggering, why?
# def dlg_end(msg):
# caller = kamailio.pv.get('$dlg_var(caller)')
# callee = kamailio.pv.get('$dlg_var(callee)')
# kamailio.info(f'DIALOG: Ended {caller} <-> {callee}\n')
# update_user_status(caller, 'Available')
# update_user_status(callee, 'Available')
# return 1


def app_reply_route(msg):
    reply_status = str(kamailio.pv.get('$rs'))

    # Detect Call Answer (200 OK to INVITE)
    if reply_status == '200':
        caller = kamailio.pv.get('$fU')
        callee = kamailio.pv.get('$tU')
        kamailio.info(f'DIALOG: Established {caller} <-> {callee}\n')
        # Block users from receiving calls during a live call
        update_user_status(caller, 'OnCall')
        update_user_status(callee, 'OnCall')

    return 1


def app_redial_route(msg):
    # Catch error codes matching for redial service
    failure_status = '500'
    if kamailio.tm.t_check_status('486'):
        failure_status = '486'
    elif kamailio.tm.t_check_status('408'):
        failure_status = '408'
    elif kamailio.tm.t_check_status('480'):
        failure_status = '480'
    elif kamailio.tm.t_check_status('500'):
        failure_status = '500'
    elif kamailio.tm.t_check_status('503'):
        failure_status = '503'
    elif kamailio.tm.t_check_status('603'):
        failure_status = '603'
    else:
        code = kamailio.pv.get('$T_reply_code')
        if code:
            failure_status = str(code)

    should_redial = False
    if failure_status in ['408', '480', '500', '503']:
        should_redial = True
        kamailio.info(f'FAILURE: Network/Timeout error ({failure_status})\n')
    elif failure_status == '486':
        should_redial = True
        kamailio.info('FAILURE: Destination Busy (486)\n')
    elif failure_status == '603':
        should_redial = True
        kamailio.info('FAILURE: Destination Blocked (603)\n')

    # Perform redial
    if should_redial:
        count_obj = kamailio.pv.get('$avp(redial_count)')
        count = int(count_obj) if count_obj else 0

        if count < MAX_REDIALS:
            count += 1

            kamailio.pv.seti('$avp(redial_count)', count)
            kamailio.info(
                f'SERVICE: Redialing attempt {count}/{MAX_REDIALS}...\n'
            )

            # Rearm redial failure route
            kamailio.tm.t_on_failure('app_redial_route')
            kamailio.registrar.lookup('location')
            kamailio.tm.t_relay()

            return 1
        else:
            kamailio.info('SERVICE: Max redials reached. Giving up.\n')

    # Freeup users for calls
    # caller = kamailio.pv.get('$dlg_var(caller)')
    # callee = kamailio.pv.get('$dlg_var(callee)')
    caller = kamailio.pv.get('$fU')
    callee = kamailio.pv.get('$tU')
    update_user_status(caller, 'Available')
    update_user_status(callee, 'Available')

    return 1


def app_failure_route(msg):
    # Catch error codes matching for redial service
    failure_status = '500'
    if kamailio.tm.t_check_status('486'):
        failure_status = '486'
    elif kamailio.tm.t_check_status('408'):
        failure_status = '408'
    elif kamailio.tm.t_check_status('480'):
        failure_status = '480'
    elif kamailio.tm.t_check_status('500'):
        failure_status = '500'
    elif kamailio.tm.t_check_status('503'):
        failure_status = '503'
    elif kamailio.tm.t_check_status('603'):
        failure_status = '603'
    else:
        code = kamailio.pv.get('$T_reply_code')
        if code:
            failure_status = str(code)

    if failure_status in ['408', '480', '500', '503']:
        kamailio.info(f'FAILURE: Network/Timeout error ({failure_status})\n')
    elif failure_status == '486':
        kamailio.info('FAILURE: Destination Busy (486)\n')
    elif failure_status == '603':
        kamailio.info('FAILURE: Destination Blocked (603)\n')

    caller = kamailio.pv.get('$fU')
    callee = kamailio.pv.get('$tU')
    update_user_status(caller, 'Available')
    update_user_status(callee, 'Available')

    return 1


# ----  ----


# ----  ----
