# Copyright 2013-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from wazo_agid import dialplan_variables as dv
from wazo_agid import objects
from wazo_agid.handlers.handler import Handler

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor, DictRow

    from wazo_agid.agid import FastAGI


class AgentFeatures(Handler):
    def __init__(self, agi: FastAGI, cursor: DictCursor, args: list[str]) -> None:
        super().__init__(agi, cursor, args)
        self.agent_id: str = None  # type: ignore[assignment]
        self.agent: objects.Agent = None  # type: ignore[assignment]

    def execute(self) -> None:
        self._extract_agent_id()
        self._set_agent_interface()
        self._set_agent()
        self._set_preprocess_subroutine()
        self._set_queue_call_options()

    def _extract_agent_id(self) -> None:
        try:
            self.agent_id = self._args[0]
        except IndexError:
            self._agi.dp_break('Missing feature agent_id argument')

    def _set_agent_interface(self) -> None:
        try:
            self._agi.set_variable(dv.AGENT_INTERFACE, self._get_agent_device())
        except LookupError as e:
            self._agi.dp_break(e)

    def _get_agent_device(self):
        self._cursor.execute(
            'SELECT state_interface FROM agent_login_status WHERE agent_id  = %s',
            (self.agent_id,),
        )
        res: DictRow = self._cursor.fetchone()
        if not res:
            raise LookupError(f'Unable to find agent (id: {self.agent_id})')
        device = res[0]
        return device

    def _set_agent(self) -> None:
        try:
            self.agent = objects.Agent.from_id_any_tenant(self._cursor, self.agent_id)
        except (LookupError, IndexError) as e:
            self._agi.dp_break(e)

    def _set_preprocess_subroutine(self) -> None:
        if self.agent.preprocess_subroutine:
            preprocess_subroutine = self.agent.preprocess_subroutine
        else:
            preprocess_subroutine = ''
        self._agi.set_variable(dv.AGENTPREPROCESS_SUBROUTINE, preprocess_subroutine)

    def _set_queue_call_options(self) -> None:
        queue_options = self._agi.get_variable('WAZO_QUEUEOPTIONS')
        queue_call_options = self._extract_queue_call_options(queue_options)
        self._agi.set_variable(dv.QUEUECALLOPTIONS, queue_call_options)

    def _extract_queue_call_options(self, queue_options: str) -> str:
        queue_options = re.sub(r'\(.*?\)', '', queue_options)
        authorized_options = ['h', 'i', 't', 'w', 'x', 'k']
        queue_call_options = ''
        for option in queue_options:
            if option in authorized_options:
                queue_call_options += option
        return queue_call_options
