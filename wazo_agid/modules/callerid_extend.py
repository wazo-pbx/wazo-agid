# Copyright 2012-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from wazo_agid import agid

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor

    from wazo_agid.agid import FastAGI


def callerid_extend(agi: FastAGI, cursor: DictCursor, args: list[str]) -> None:
    if 'agi_callington' in agi.env:
        agi.set_variable('WAZO_SRCTON', agi.env['agi_callington'])


agid.register(callerid_extend)
