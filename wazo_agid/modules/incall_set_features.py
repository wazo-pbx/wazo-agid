# Copyright 2006-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from psycopg2.extras import DictCursor

from wazo_agid import agid, dialplan_variables, objects


def incall_set_features(agi: agid.FastAGI, cursor: DictCursor, args: list[str]) -> None:
    user_id = agi.get_variable(dialplan_variables.USERID)
    if user_id:
        try:
            user = objects.User(agi, cursor, int(user_id))
            agi.set_variable('WAZO_SIMULTCALLS', user.simultcalls)
        except (ValueError, LookupError) as e:
            agi.dp_break(str(e))


agid.register(incall_set_features)
