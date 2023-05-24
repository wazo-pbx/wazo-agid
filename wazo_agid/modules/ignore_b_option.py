# Copyright 2021-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from wazo_agid import agid
from wazo_agid.dialplan_variables import CALL_OPTIONS

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor


B_REGEX = re.compile(r'b\(([\-_0-9A-Za-z]+)\^?.*?\)')


def ignore_b_option(agi: agid.FastAGI, cursor: DictCursor, args: list[str]) -> None:
    """
    handler to detect and warn about usage of b option
    """
    if not (call_options := agi.get_variable(CALL_OPTIONS)):
        return

    if not (match := B_REGEX.search(call_options)):
        return

    to_remove = match.group(0)
    to_stack = match.group(1)

    agi.verbose(
        f'WARNING: deprecated usage of dialplan b option detected with subroutine: {to_stack}'
    )
    agi.verbose(
        'Option will be ignored. Wazo pre-dial handlers should be used instead.'
    )

    pruned_call_options = call_options.replace(to_remove, '')
    agi.set_variable(CALL_OPTIONS, pruned_call_options)


agid.register(ignore_b_option)
