# Copyright 2006-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from uuid import uuid4

from wazo_agid import agid
from wazo_agid import dialplan_variables as dv
from wazo_agid import objects


def incoming_queue_set_features(agi, cursor, args):
    queue_id = agi.get_variable('WAZO_DSTID')
    referer = agi.get_variable('WAZO_FWD_REFERER')

    try:
        queue = objects.Queue(agi, cursor, int(queue_id))
    except (ValueError, LookupError) as e:
        agi.dp_break(str(e))

    options = ""
    needanswer = "1"

    if queue.data_quality:
        options += "d"

    if queue.hitting_callee:
        options += "h"

    if queue.hitting_caller:
        options += "H"

    if queue.retries:
        options += "n"

    if queue.ring:
        options += "r"
        needanswer = "0"

    if queue.transfer_user:
        options += "t"

    if queue.transfer_call:
        options += "T"

    if queue.write_caller:
        options += "x"

    if queue.write_calling:
        options += "X"

    if queue.ignore_forward:
        options += "i"

    if queue.mark_answered_elsewhere:
        options += "C"

    agi.set_variable(dv.REAL_NUMBER, queue.number)
    agi.set_variable(dv.REAL_CONTEXT, queue.context)
    agi.set_variable('__WAZO_QUEUENAME', queue.name)
    agi.set_variable('WAZO_QUEUEOPTIONS', options)
    agi.set_variable(dv.QUEUENEEDANSWER, needanswer)
    agi.set_variable(dv.QUEUEURL, queue.url)
    agi.set_variable(dv.QUEUEANNOUNCEOVERRIDE, queue.announceoverride)
    if queue.musiconhold:
        agi.set_variable('CHANNEL(musicclass)', queue.musiconhold)

    _set_wrapup_time(agi, queue)
    _set_call_record_toggle(agi, queue)

    if queue.preprocess_subroutine:
        preprocess_subroutine = queue.preprocess_subroutine
    else:
        preprocess_subroutine = ""

    if queue.timeout:
        timeout = queue.timeout
    else:
        timeout = ""

    agi.set_variable(dv.QUEUEPREPROCESS_SUBROUTINE, preprocess_subroutine)
    agi.set_variable(dv.QUEUETIMEOUT, timeout)

    queue.set_dial_actions()

    if referer == f"queue:{queue.id}":
        queue.rewrite_cid()

    agi.set_variable(dv.QUEUESTATUS, 'ok')

    # schedule
    # 'incall' schedule has priority over queue's schedule
    path = agi.get_variable(dv.PATH)
    if not path:
        agi.set_variable(dv.PATH, 'queue')
        agi.set_variable(dv.PATH_ID, queue.id)

    # pickup
    pickups = queue.pickupgroups()
    agi.set_variable(dv.PICKUPGROUP, ','.join(pickups))

    set_call_record_side(agi, queue)


def _set_call_record_toggle(agi, queue):
    toggle_enabled = '1' if queue.dtmf_record_toggle else '0'
    agi.set_variable(
        f'__{dv.QUEUE_DTMF_RECORD_TOGGLE_ENABLED}',
        toggle_enabled,
    )


def _set_wrapup_time(agi, queue):
    if queue.wrapuptime:
        agi.set_variable('__QUEUEWRAPUPTIME', queue.wrapuptime)


def holdtime_announce(agi, cursor, args):
    queue_id = agi.get_variable('WAZO_DSTID')
    try:
        queue = objects.Queue(agi, cursor, int(queue_id))
    except (ValueError, LookupError) as e:
        agi.dp_break(str(e))

    if queue.announce_holdtime != 1:
        return

    holdtime = agi.get_variable('QUEUEHOLDTIME')
    holdtime = max(1, (int(holdtime) + 59) // 60)

    gender = 'f' if holdtime == 1 else ''

    agi.answer()
    agi.stream_file('queue-holdtime')
    agi.stream_file('queue-less-than')
    agi.say_number(str(holdtime), gender=gender)
    agi.stream_file('queue-minutes')


def set_call_record_side(agi, queue):
    agi.set_variable('WAZO_CALL_RECORD_SIDE', 'caller')
    agi.set_variable('__WAZO_LOCAL_CHAN_MATCH_UUID', str(uuid4()))


agid.register(incoming_queue_set_features)
agid.register(holdtime_announce)
