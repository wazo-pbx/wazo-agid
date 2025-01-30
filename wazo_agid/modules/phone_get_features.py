# Copyright 2006-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from psycopg2.extras import DictCursor

from wazo_agid import agid
from wazo_agid import dialplan_variables as dv
from wazo_agid import objects

logger = logging.getLogger(__name__)


def phone_get_features(agi: agid.FastAGI, cursor: DictCursor, args: list[str]) -> None:
    userid = agi.get_variable('WAZO_USERID')

    try:
        user = objects.User(agi, cursor, int(userid))
    except (ValueError, LookupError) as e:
        agi.dp_break(str(e))

    _set_current_forwards(agi, user.id)

    for service in objects.ExtenFeatures.FEATURES['services']:
        if service == 'callrecord':
            enabled = user.call_record_enabled
            agi.set_variable(dv.CALLRECORD, int(enabled))
        elif service == 'enablevm':
            enabled = user.enablevoicemail
            agi.set_variable(dv.ENABLEVOICEMAIL, int(enabled))
        elif service == 'incallfilter':
            enabled = user.incallfilter
            agi.set_variable(dv.INCALLFILTER, int(enabled))
        elif service == 'enablednd':
            enabled = user.enablednd
            agi.set_variable("WAZO_ENABLEDND", int(enabled))


def _set_current_forwards(agi, user_id):
    forwards = _get_forwards(agi, user_id)
    busy_forward = forwards['busy']
    agi.set_variable(dv.ENABLEBUSY, _extract_and_format_enabled(busy_forward))
    agi.set_variable(dv.DESTBUSY, _extract_and_format_destination(busy_forward))
    noanswer_forward = forwards['noanswer']
    agi.set_variable(dv.ENABLERNA, _extract_and_format_enabled(noanswer_forward))
    agi.set_variable(dv.DESTRNA, _extract_and_format_destination(noanswer_forward))
    unconditional_forward = forwards['unconditional']
    agi.set_variable(
        'WAZO_ENABLEUNC', _extract_and_format_enabled(unconditional_forward)
    )
    agi.set_variable(dv.DESTUNC, _extract_and_format_destination(unconditional_forward))


def _extract_and_format_enabled(forward):
    return int(forward['enabled'])


def _extract_and_format_destination(forward):
    return forward['destination'] if forward['destination'] is not None else ''


def _get_forwards(agi, user_id):
    try:
        confd_client = agi.config['confd']['client']
        return confd_client.users(user_id).list_forwards()
    except Exception as e:
        logger.error('Error during getting forwards: %s', e)
        return {
            'busy': {'enabled': False, 'destination': None},
            'noanswer': {'enabled': False, 'destination': None},
            'unconditional': {'enabled': False, 'destination': None},
        }


agid.register(phone_get_features)
