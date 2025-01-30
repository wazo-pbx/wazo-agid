# Copyright 2012-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from psycopg2.sql import SQL

from wazo_agid import dialplan_variables as dv
from wazo_agid import objects
from wazo_agid.handlers.handler import Handler
from wazo_agid.objects import sanitize_aliased_column, sanitize_column

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor, DictRow

    from wazo_agid.agid import FastAGI

logger = logging.getLogger(__name__)


class GroupFeatures(Handler):
    def __init__(self, agi: FastAGI, cursor: DictCursor, args: list[str]) -> None:
        super().__init__(agi, cursor, args)
        self._id: int = None  # type: ignore[assignment]
        self._referer: str = None  # type: ignore[assignment]
        self._exten: str = None  # type: ignore[assignment]
        self._context: str = None  # type: ignore[assignment]
        self._name: str = None  # type: ignore[assignment]
        self._label: str = None  # type: ignore[assignment]
        self._dtmf_record_toggle: bool = False
        self._timeout = None
        self._transfer_user = None
        self._transfer_call = None
        self._write_caller = None
        self._write_calling = None
        self._ignore_forward = None
        self._preprocess_subroutine = None
        self._musicclass = None
        self._pickup_member = None
        self._max_calls: int = None  # type: ignore[assignment]
        self._tenant_uuid = None

    def execute(self) -> None:
        self._set_members()
        self._display_queue()
        self._set_options()
        self._set_vars()
        self._set_preprocess_subroutine()
        self._set_timeout()
        self._set_dial_action()
        self._set_schedule()
        if self._needs_rewrite_cid():
            self._set_rewrite_cid()
        self._set_call_record_options()

    def _display_queue(self) -> None:
        self._agi.verbose(
            f'Calling group "{self._label}" from tenant "{self._tenant_uuid}"',
        )

    def _needs_rewrite_cid(self) -> bool:
        return self._referer == f"group:{self._id}"

    def _set_members(self) -> None:
        dst_id = self._agi.get_variable(dv.DESTINATION_ID)
        self._id = int(dst_id)
        self._referer = self._agi.get_variable(dv.FWD_REFERER)

        groupfeatures_columns = (
            'id',
            'name',
            'label',
            'dtmf_record_toggle',
            'timeout',
            'transfer_user',
            'transfer_call',
            'write_caller',
            'write_calling',
            'ignore_forward',
            'preprocess_subroutine',
            'mark_answered_elsewhere',
            'tenant_uuid',
        )
        queue_columns = ('musicclass', 'timeout', 'strategy', 'retry', 'maxlen')
        extensions_columns = ('exten', 'context')
        columns = [sanitize_column(f"groupfeatures.{c}") for c in groupfeatures_columns]
        columns += [
            sanitize_aliased_column(f"queue.{c}", f"queue_{c}") for c in queue_columns
        ]
        columns += [sanitize_column(f"extensions.{c}") for c in extensions_columns]

        query = SQL(
            "SELECT {columns} FROM groupfeatures "
            "INNER JOIN queue "
            "ON groupfeatures.name = queue.name "
            "LEFT JOIN extensions "
            "ON groupfeatures.id::text = extensions.typeval "
            "AND extensions.type = 'group' "
            "WHERE groupfeatures.id = %s "
            "AND queue.category = 'group' "
            "AND queue.commented = 0"
        )
        self._cursor.execute(query.format(columns=SQL(", ").join(columns)), (self._id,))
        res: DictRow = self._cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find group (id: {self._id})")

        self._exten = res['exten']
        self._context = res['context']
        self._name = res['name']
        self._label = res['label']
        self._timeout = res['timeout']
        self._dtmf_record_toggle = res['dtmf_record_toggle']
        self._transfer_user = res['transfer_user']
        self._transfer_call = res['transfer_call']
        self._write_caller = res['write_caller']
        self._write_calling = res['write_calling']
        self._ignore_forward = res['ignore_forward']
        self._preprocess_subroutine = res['preprocess_subroutine']
        self._musicclass = res['queue_musicclass']
        self._mark_answered_elsewhere = res['mark_answered_elsewhere']
        self._tenant_uuid = res['tenant_uuid']
        self._user_timeout = res['queue_timeout']
        self._group_strategy = res['queue_strategy']
        self._group_retry_delay = res['queue_retry']
        self._max_calls = res['queue_maxlen']

    def _set_vars(self) -> None:
        self._agi.set_variable(dv.REAL_NUMBER, self._exten)
        self._agi.set_variable(dv.REAL_CONTEXT, self._context)
        self._agi.set_variable('__WAZO_GROUPNAME', self._name)
        self._agi.set_variable('WAZO_GROUP_LABEL', self._label)
        self._agi.set_variable('WAZO_GROUP_STRATEGY', self._group_strategy)
        self._agi.set_variable('WAZO_GROUP_MAX_CALLS', self._max_calls)
        if self._musicclass:
            self._agi.set_variable('CHANNEL(musicclass)', self._musicclass)

    def _set_options(self) -> None:
        options = ""
        needanswer = "1"

        if self._transfer_user:
            options += "t"

        if self._transfer_call:
            options += "T"

        if self._write_caller:
            options += "x"

        if self._write_calling:
            options += "X"

        if self._ignore_forward:
            options += 'i'

        if not self._musicclass:
            options += "r"
            needanswer = "0"
        elif self._group_strategy == 'linear':
            # linear groups need Dial options
            options += "m"

        if self._mark_answered_elsewhere:
            if self._group_strategy == 'linear':
                # equivalent Dial option used for linear groups
                options += "c"
            else:
                options += "C"

        self._agi.set_variable('WAZO_GROUPOPTIONS', options)
        self._agi.set_variable(dv.GROUPNEEDANSWER, needanswer)

    def _set_preprocess_subroutine(self) -> None:
        if self._preprocess_subroutine:
            self._agi.set_variable(
                dv.GROUPPREPROCESS_SUBROUTINE, self._preprocess_subroutine
            )

    def _set_timeout(self) -> None:
        if self._timeout:
            self._agi.set_variable(dv.GROUP_TIMEOUT, self._timeout)
        else:
            self._agi.set_variable(dv.GROUP_TIMEOUT, "")

        if self._user_timeout:
            self._agi.set_variable('WAZO_GROUP_USER_TIMEOUT', self._user_timeout)
        else:
            self._agi.set_variable('WAZO_GROUP_USER_TIMEOUT', "")

        if self._group_retry_delay:
            self._agi.set_variable('WAZO_GROUP_RETRY_DELAY', self._group_retry_delay)
        else:
            self._agi.set_variable('WAZO_GROUP_RETRY_DELAY', "0")

    def _set_dial_action(self) -> None:
        for event in ('noanswer', 'congestion', 'busy', 'chanunavail'):
            objects.DialAction(
                self._agi, self._cursor, event, "group", self._id
            ).set_variables()

    def _set_rewrite_cid(self) -> None:
        objects.CallerID(self._agi, self._cursor, 'group', self._id).rewrite(
            force_rewrite=False
        )

    def _set_schedule(self) -> None:
        path = self._agi.get_variable(dv.PATH)
        if not path:
            self._agi.set_variable(dv.PATH, 'group')
            self._agi.set_variable(dv.PATH_ID, self._id)

    def _set_call_record_options(self) -> None:
        self._agi.set_variable('WAZO_CALL_RECORD_SIDE', 'caller')
        self._agi.set_variable('__WAZO_LOCAL_CHAN_MATCH_UUID', str(uuid4()))
        toggle_enabled = '1' if self._dtmf_record_toggle else '0'
        self._agi.set_variable(
            f'__{dv.GROUP_DTMF_RECORD_TOGGLE_ENABLED}',
            toggle_enabled,
        )
