# Copyright 2018-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from wazo_agid import agid
from wazo_agid import dialplan_variables as dv

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor

    from wazo_agid.agid import FastAGI


logger = logging.getLogger(__name__)


def linear_group_check_timeout(
    agi: FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    group_id = agi.get_variable('WAZO_DSTID')

    if not (_group_timeout := agi.get_variable(dv.GROUP_TIMEOUT)):
        logger.info('%s not set for group %s', dv.GROUP_TIMEOUT, group_id)
        group_timeout = 0
    else:
        group_timeout = int(_group_timeout)

    current_time = time.time()

    if not (_start_time := agi.get_variable('WAZO_GROUP_START_TIME')):
        start_time = current_time
        agi.set_variable('WAZO_GROUP_START_TIME', str(start_time))
    else:
        start_time = float(_start_time)

    if (current_time - start_time) >= group_timeout:
        agi.set_variable('WAZO_GROUP_TIMEOUT_EXPIRED', '1')
        return

    if _user_timeout := agi.get_variable('WAZO_GROUP_USER_TIMEOUT'):
        user_timeout = int(_user_timeout)
    else:
        user_timeout = group_timeout

    remaining_time = group_timeout - (current_time - start_time)
    next_dial_timeout = int(min(user_timeout, remaining_time))

    agi.set_variable('WAZO_DIAL_TIMEOUT', str(next_dial_timeout))


agid.register(linear_group_check_timeout)
