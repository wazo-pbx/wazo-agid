# Copyright 2008-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging

from psycopg2.extras import DictCursor

from wazo_agid import agid, objects
from wazo_agid.fastagi import FastAGI

logger = logging.getLogger(__name__)


def agent_get_options(agi: FastAGI, cursor: DictCursor, args):
    agi.set_variable('XIVO_AGENTEXISTS', 0)

    try:
        tenant_uuid = args[0]
        number = str(args[1])

        if number.startswith('*'):
            agent = objects.Agent(agi, cursor, xid=number[1:])
        else:
            agent = objects.Agent(agi, cursor, number=number)

        if agent.tenant_uuid != tenant_uuid:
            return
    except (LookupError, IndexError) as e:
        agi.verbose(str(e))
        return

    agi.set_variable('XIVO_AGENTEXISTS', 1)
    agi.set_variable('XIVO_AGENTPASSWD', agent.passwd or '')
    agi.set_variable('XIVO_AGENTID', agent.id)
    agi.set_variable('XIVO_AGENTNUM', agent.number)

    if agent.language:
        agi.set_variable('CHANNEL(language)', agent.language)


agid.register(agent_get_options)
