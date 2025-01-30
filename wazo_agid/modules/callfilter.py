# Copyright 2013-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from xivo_dao import callfilter_dao

from wazo_agid import agid
from wazo_agid import dialplan_variables as dv

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor

    from wazo_agid.agid import FastAGI


def callfilter(agi: FastAGI, cursor: DictCursor, args: list[str]) -> None:
    callfiltermember_id = args[0]

    if not callfiltermember_id.isdigit():
        agi.dp_break(
            f'This id "{callfiltermember_id}" is not a valid callfiltermember_id id.'
        )

    caller_user_id = agi.get_variable(dv.USERID)
    callfiltermember = callfilter_dao.get_by_callfiltermember_id(callfiltermember_id)
    if not callfiltermember:
        agi.dp_break('This callfilter does not exist.')

    bslist = callfilter_dao.get(callfiltermember.callfilterid)
    if not bslist:
        agi.dp_break('This callfilter has no member.')

    allow_ids = []
    for bs in bslist:
        callfilter, callfiltermembers = bs
        allow_ids.append(callfiltermembers.typeval)

    if not caller_user_id or caller_user_id not in allow_ids:
        agi.dp_break('This user is not allowed to use this callfilter.')

    new_state = 0 if callfiltermember.active == 1 else 1
    callfilter_dao.update_callfiltermember_state(callfiltermember_id, new_state)
    agi.set_variable(dv.BSFILTERENABLED, new_state)


agid.register(callfilter)
