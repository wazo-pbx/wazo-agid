# Copyright 2012-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from wazo_agentd_client import error
from wazo_agentd_client.error import AgentdClientError

from wazo_agid import dialplan_variables as dv
from wazo_agid.fastagi import FastAGI


def login_agent(
    agi: FastAGI, agent_id: int, extension: str, context: str, tenant_uuid: str
) -> None:
    agentd_client = agi.config['agentd']['client']
    try:
        agentd_client.agents.login_agent(
            agent_id, extension, context, tenant_uuid=tenant_uuid
        )
    except AgentdClientError as e:
        if e.error == error.ALREADY_LOGGED:
            agi.set_variable(dv.AGENTSTATUS, 'already_logged')
        elif e.error == error.ALREADY_IN_USE:
            agi.set_variable(dv.AGENTSTATUS, 'already_in_use')
        else:
            raise
    else:
        agi.set_variable(dv.AGENTSTATUS, 'logged')


def logoff_agent(agi: FastAGI, agent_id: int, tenant_uuid: str) -> None:
    agentd_client = agi.config['agentd']['client']
    try:
        agentd_client.agents.logoff_agent(agent_id, tenant_uuid=tenant_uuid)
    except AgentdClientError as e:
        if e.error != error.NOT_LOGGED:
            raise


def get_agent_status(agi: FastAGI, agent_id: int, tenant_uuid: str) -> None:
    agentd_client = agi.config['agentd']['client']
    status = agentd_client.agents.get_agent_status(agent_id, tenant_uuid=tenant_uuid)
    login_status = 'logged_in' if status.logged else 'logged_out'
    agi.set_variable(dv.AGENT_LOGIN_STATUS, login_status)
