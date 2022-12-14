# Copyright 2010-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_agid import agid, objects

logger = logging.getLogger(__name__)


def check_schedule(agi, cursor, args):
    path = agi.get_variable('XIVO_PATH')
    path_id = agi.get_variable('XIVO_PATH_ID')

    if not path:
        return

    schedule = objects.ScheduleDataMapper.get_from_path(cursor, path, path_id)
    schedule_state = schedule.compute_state_for_now()

    agi.set_variable('XIVO_SCHEDULE_STATUS', schedule_state.state)
    if schedule_state.state == 'closed':
        schedule_state.action.set_variables_in_agi(agi)

    # erase path for next schedule check
    agi.set_variable('XIVO_PATH', '')


agid.register(check_schedule)
