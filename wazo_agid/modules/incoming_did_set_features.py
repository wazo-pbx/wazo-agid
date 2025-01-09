# Copyright 2006-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from psycopg2.extras import DictCursor

from wazo_agid import agid, dialplan_variables, objects


def incoming_did_set_features(
    agi: agid.FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    incall_id = agi.get_variable('XIVO_INCALL_ID')

    did = objects.DID(agi, cursor, incall_id)

    if did.preprocess_subroutine:
        preprocess_subroutine = did.preprocess_subroutine
    else:
        preprocess_subroutine = ""

    agi.set_variable('XIVO_DIDPREPROCESS_SUBROUTINE', preprocess_subroutine)
    agi.set_variable('XIVO_EXTENPATTERN', did.exten)
    agi.set_variable(dialplan_variables.PATH, 'incall')
    agi.set_variable(dialplan_variables.PATH_ID, did.id)
    agi.set_variable('XIVO_REAL_CONTEXT', did.context)
    agi.set_variable(dialplan_variables.REAL_NUMBER, did.exten)
    agi.set_variable('WAZO_GREETING_SOUND', did.greeting_sound or '')

    did.set_dial_actions()
    did.rewrite_cid()


agid.register(incoming_did_set_features)
