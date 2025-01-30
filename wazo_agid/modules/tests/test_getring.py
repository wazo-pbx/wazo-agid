# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import configparser
import io
import unittest
from unittest.mock import Mock

from hamcrest import assert_that, calling, not_, raises

from wazo_agid import dialplan_variables as dv

from .. import getring

DEFAULT_CONFIG = '''\
[number]
;101@context = <section>
;@context = <section>
;!102@context = 1
'''


class TestGetRing(unittest.TestCase):
    def setUp(self):
        self.agi = Mock()
        self.cursor = Mock()

    def test_that_no_number_config_does_not_raise(self):
        self._set_config(DEFAULT_CONFIG)
        variables = {
            dv.REAL_NUMBER: '1001',
            dv.REAL_CONTEXT: 'default',
            'WAZO_FWD_REFERER': 'foo:bar',
        }
        self.agi.get_variable.side_effect = lambda var: variables.get(var)

        assert_that(
            calling(getring.getring).with_args(self.agi, self.cursor, []),
            not_(raises(Exception)),
        )

    def _set_config(self, content):
        file_ = io.StringIO(content)

        getring.CONFIG_PARSER = configparser.RawConfigParser()
        getring.CONFIG_PARSER.read_file(file_)
