# Copyright 2016-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_dao.resources.conference import dao as conference_dao

from wazo_agid import agid


def incoming_conference_set_features(agi, cursor, args):
    conference_id = int(agi.get_variable('XIVO_DSTID'))

    try:
        conference = conference_dao.get(conference_id)
    except (ValueError) as e:
        agi.dp_break(str(e))

    menu = 'xivo-default-user-menu'
    user_profile = f'xivo-user-profile-{conference.id}'
    if conference.pin:
        for _ in range(4):
            agi.answer()
            pin = agi.get_data('conf-getpin', 10000, 80)
            if pin == conference.pin:
                break
            elif pin == conference.admin_pin:
                menu = 'xivo-default-admin-menu'
                user_profile = f'xivo-admin-profile-{conference.id}'
                break
            else:
                agi.stream_file('conf-invalidpin')
        else:
            agi.dp_break(
                'Unable to join the conference room, wrong pin'
                f'(conference_id: {conference.id}, name: {conference.name})'
            )

    agi.set_variable('WAZO_CONFBRIDGE_ID', conference.id)
    agi.set_variable('WAZO_CONFBRIDGE_TENANT_UUID', conference.tenant_uuid)
    agi.set_variable(
        'WAZO_CONFBRIDGE_BRIDGE_PROFILE', f'xivo-bridge-profile-{conference.id}'
    )
    agi.set_variable('WAZO_CONFBRIDGE_USER_PROFILE', user_profile)
    agi.set_variable('WAZO_CONFBRIDGE_MENU', menu)
    agi.set_variable(
        'WAZO_CONFBRIDGE_PREPROCESS_SUBROUTINE', conference.preprocess_subroutine or ''
    )
    agi.appexec('CELGenUserEvent', f'WAZO_CONFERENCE, NAME: {conference.name or ""}')


agid.register(incoming_conference_set_features)
