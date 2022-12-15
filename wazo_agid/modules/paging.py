# Copyright 2012-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os

from wazo_agid import agid, objects

logger = logging.getLogger(__name__)


def paging(agi, cursor, args):

    userid = agi.get_variable('XIVO_USERID')

    try:
        paging_entry = objects.Paging(agi, cursor, args[0], userid)
    except (ValueError, LookupError) as e:
        agi.answer()
        agi.stream_file('vm-incorrect')
        agi.dp_break(f'Sorry you are not authorize to page this group : {str(e)}')

    paging_line = '&'.join(paging_entry.lines)
    agi.set_variable('XIVO_PAGING_LINES', paging_line)
    agi.set_variable('XIVO_PAGING_TIMEOUT', paging_entry.timeout)
    agi.set_variable('XIVO_PAGING_OPTS', build_options(paging_entry))


def build_options(paging):
    # s = call phones only if not busy
    # b = Gosub for each destination channels
    paging_opts = 'sb(paging^add-sip-headers^1)'

    if paging.duplex:
        paging_opts = paging_opts + 'd'

    if paging.quiet:
        paging_opts = paging_opts + 'q'

    if paging.record:
        paging_opts = paging_opts + 'r'

    if paging.ignore:
        paging_opts = paging_opts + 'i'

    if paging.announcement_play and paging.announcement_file:
        sound_file_directory = '/var/lib/wazo/sounds/tenants'
        announcement_file_name = os.path.join(
            sound_file_directory,
            paging.tenant_uuid,
            'playback',
            paging.announcement_file,
        )

        paging_opts = paging_opts + f'A({announcement_file_name})'

    if paging.announcement_caller:
        paging_opts = paging_opts + 'n'

    return paging_opts


agid.register(paging)
