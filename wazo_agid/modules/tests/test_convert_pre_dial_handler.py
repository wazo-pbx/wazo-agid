# Copyright 2021-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from unittest.mock import Mock, call

from hamcrest import assert_that, contains_inanyorder

from wazo_agid.fastagi import FastAGI

from ..convert_pre_dial_handler import convert_pre_dial_handler


class TestConvertPreDialHandler(unittest.TestCase):
    def setUp(self):
        self.agi = Mock(FastAGI)

    def test_no_call_options(self):
        self.agi.get_variable.return_value = ''

        convert_pre_dial_handler(self.agi, Mock(), Mock())

        self.agi.set_variable.assert_not_called()

    def test_no_b_option(self):
        variables = {'XIVO_CALLOPTIONS': 'XB(foobar^s^1)'}
        self.agi.get_variable.side_effect = variables.get

        convert_pre_dial_handler(self.agi, Mock(), Mock())

        self.agi.set_variable.assert_not_called()

    def test_with_b_option_no_handlers(self):
        variables = {
            'XIVO_CALLOPTIONS': 'Xb(foobaz^s^1)B(foobar^s^1)',
        }
        self.agi.get_variable.side_effect = variables.get

        convert_pre_dial_handler(self.agi, Mock(), Mock())

        assert_that(
            self.agi.set_variable.call_args_list,
            contains_inanyorder(
                call('XIVO_CALLOPTIONS', 'XB(foobar^s^1)'),
                call('PUSH(_WAZO_PRE_DIAL_HANDLERS,|)', 'foobaz,s,1'),
            ),
        )
