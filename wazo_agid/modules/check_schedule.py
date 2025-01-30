# Copyright 2010-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from wazo_agid import agid
from wazo_agid import dialplan_variables as dv
from wazo_agid import objects

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor

    from wazo_agid.agid import FastAGI

logger = logging.getLogger(__name__)


def check_schedule(agi: FastAGI, cursor: DictCursor, args: list[str]) -> None:
    path = agi.get_variable(dv.PATH)
    path_id = agi.get_variable(dv.PATH_ID)

    if not path:
        return

    schedule = objects.ScheduleDataMapper.get_from_path(cursor, path, path_id)
    schedule_state = schedule.compute_state_for_now()

    agi.set_variable('WAZO_SCHEDULE_STATUS', schedule_state.state)
    if schedule_state.state == 'closed':
        schedule_state.action.set_variables_in_agi(agi)

    # erase path for next schedule check
    agi.set_variable(dv.PATH, '')


agid.register(check_schedule)
