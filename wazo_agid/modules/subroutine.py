# Copyright 2023-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from psycopg2.extras import DictCursor

from wazo_agid import agid
from wazo_agid import dialplan_variables as dv

logger = logging.getLogger(__name__)

VARIABLE_MAP = {
    'WAZO_CALLOPTIONS': 'XIVO_CALLOPTIONS',
    dv.CID_REWRITTEN: 'XIVO_CID_REWRITTEN',  # 25.02
    'WAZO_CONTEXT': 'XIVO_CONTEXT',
    'WAZO_DSTID': 'XIVO_DSTID',
    'WAZO_DSTNUM': 'XIVO_DSTNUM',
    'WAZO_INTERFACE': 'XIVO_INTERFACE',
    'WAZO_GROUPNAME': 'XIVO_GROUPNAME',
    'WAZO_GROUPOPTIONS': 'XIVO_GROUPOPTIONS',
    dv.GROUP_TIMEOUT: 'XIVO_GROUPTIMEOUT',  # 25.02
    dv.HANGUP_RING_TIME: 'XIVO_HANGUPRINGTIME',  # 25.02
    'WAZO_QUEUENAME': 'XIVO_QUEUENAME',
    'WAZO_PICKEDUP': 'XIVO_PICKEDUP',
    'WAZO_RINGSECONDS': 'XIVO_RINGSECONDS',
    dv.REAL_CONTEXT: 'XIVO_REAL_CONTEXT',  # 25.02
    dv.REAL_NUMBER: 'XIVO_REAL_NUMBER',  # 25.02
    'WAZO_CALLORIGIN': 'XIVO_CALLORIGIN',
    'WAZO_MOBILEPHONENUMBER': 'XIVO_MOBILEPHONENUMBER',
    'WAZO_QUEUEOPTIONS': 'XIVO_QUEUEOPTIONS',
    'WAZO_SRCNUM': 'XIVO_SRCNUM',
    'WAZO_DST_EXTEN_ID': 'XIVO_DST_EXTEN_ID',
    dv.FWD_REFERER: 'XIVO_FWD_REFERER',
    'WAZO_FROMGROUP': 'XIVO_FROMGROUP',
    'WAZO_BASE_CONTEXT': 'XIVO_BASE_CONTEXT',
    'WAZO_ENABLEDND': 'XIVO_ENABLEDND',
    'WAZO_ENABLEUNC': 'XIVO_ENABLEUNC',
    'WAZO_CALLEE_SIMULTCALLS': 'XIVO_SIMULTCALLS',
    dv.MAILBOX: 'XIVO_MAILBOX',  # 25.02
    dv.MAILBOX_CONTEXT: 'XIVO_MAILBOX_CONTEXT',  # 25.02
    dv.MAILBOX_LANGUAGE: 'XIVO_MAILBOX_LANGUAGE',  # 25.02
    'WAZO_MAILBOX_OPTIONS': 'XIVO_MAILBOX_OPTIONS',  # 25.02
    dv.USEREMAIL: 'XIVO_USEREMAIL',  # 25.02
}
ORIG_VALUE_TPL = 'WAZO_COMPAT_{new_name}_ORIG'


def pre_subroutine_compat(
    agi: agid.FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    logger.debug('Entering pre-subroutine compatibility')
    for new_name, old_name in VARIABLE_MAP.items():
        current_value = agi.get_variable(new_name)
        agi.set_variable(old_name, current_value)
        agi.set_variable(ORIG_VALUE_TPL.format(new_name=new_name), current_value)


def post_subroutine_compat(
    agi: agid.FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    logger.debug('Entering post-subroutine compatibility')
    for new_name, old_name in VARIABLE_MAP.items():
        orig_value = agi.get_variable(ORIG_VALUE_TPL.format(new_name=new_name))
        new_value = agi.get_variable(new_name)
        compat_value = agi.get_variable(old_name)

        # Cleanup the mess to make sure it does not get used
        agi.set_variable(old_name, '')
        agi.set_variable(ORIG_VALUE_TPL.format(new_name=new_name), '')

        # Nothing changed, keep going
        if new_value == orig_value == compat_value:
            continue

        # New name has been used everything is fine
        if new_value != orig_value:
            continue

        # The old variable name has been used
        if compat_value != orig_value:
            msg = (
                f'The deprecated variable {old_name} has been modified by a subroutine.'
                f' Use {new_name} instead'
            )
            logger.info(msg)
            agi.verbose(msg)
            agi.set_variable(new_name, compat_value)


agid.register(pre_subroutine_compat)
agid.register(post_subroutine_compat)
