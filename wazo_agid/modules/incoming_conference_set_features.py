# Copyright 2016-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from psycopg2.extras import DictCursor
from xivo_dao.resources.conference import dao as conference_dao

from wazo_agid import agid


def incoming_conference_set_features(
    agi: agid.FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    conference_id = int(agi.get_variable('WAZO_DSTID'))

    try:
        conference = conference_dao.get(conference_id)
    except ValueError as e:
        agi.dp_break(str(e))

    menu = 'wazo-default-user-menu'
    user_profile = f'wazo-user-profile-{conference.id}'
    if conference.pin:
        for _ in range(4):
            agi.answer()
            pin = agi.get_data('conf-getpin', 10000, 80)
            if pin == conference.pin:
                break
            elif pin == conference.admin_pin:
                menu = 'wazo-default-admin-menu'
                user_profile = f'wazo-admin-profile-{conference.id}'
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
        'WAZO_CONFBRIDGE_BRIDGE_PROFILE', f'wazo-bridge-profile-{conference.id}'
    )
    agi.set_variable('WAZO_CONFBRIDGE_USER_PROFILE', user_profile)
    agi.set_variable('WAZO_CONFBRIDGE_MENU', menu)
    agi.set_variable(
        'WAZO_CONFBRIDGE_PREPROCESS_SUBROUTINE', conference.preprocess_subroutine or ''
    )
    agi.appexec('CELGenUserEvent', f'WAZO_CONFERENCE, NAME: {conference.name or ""}')


agid.register(incoming_conference_set_features)
