# Copyright 2013-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import ANY, Mock, call, patch

from hamcrest import assert_that, equal_to

from wazo_agid import dialplan_variables as dv
from wazo_agid.modules import check_diversion


class TestCheckDiversion(unittest.TestCase):
    def setUp(self):
        self.agi = Mock()
        self.cursor = Mock()
        self.queue = Mock(name='foo')

    def test_is_agent_ratio_overrun_no_waiting_calls(self):
        self.queue.waitratio = 1.0
        waiting_calls = 0

        result = check_diversion._is_agent_ratio_overrun(
            self.agi, self.queue, waiting_calls
        )
        self.assertFalse(result)

    def test_is_agent_ratio_overrun_0_members(self):
        self.queue.waitratio = 1.0
        self.agi.get_variable.return_value = '0'
        waiting_calls = 2

        result = check_diversion._is_agent_ratio_overrun(
            self.agi, self.queue, waiting_calls
        )
        self.assertTrue(result)
        self.agi.get_variable.assert_called_once_with(
            f'QUEUE_MEMBER({self.queue.name},logged)'
        )

    def test_is_agent_ratio_overrun_over(self):
        self.queue.waitratio = 0.70
        self.agi.get_variable.return_value = '4'
        waiting_calls = 2

        result = check_diversion._is_agent_ratio_overrun(
            self.agi, self.queue, waiting_calls
        )
        self.assertTrue(result)

    def test_is_agent_ratio_overrun_under(self):
        self.queue.waitratio = 0.80
        self.agi.get_variable.return_value = '4'
        waiting_calls = 2

        result = check_diversion._is_agent_ratio_overrun(
            self.agi, self.queue, waiting_calls
        )
        self.assertFalse(result)

    @patch('wazo_agid.modules.check_diversion.objects')
    def test_check_diversion_divert_event_is_cleared(self, mock_objects):
        self.queue.waittime = None
        self.queue.waitratio = None
        mock_objects.Queue.return_value = self.queue
        self.agi.get_variable.return_value = 42

        check_diversion.check_diversion(self.agi, self.cursor, [])

        expected = [call(dv.DIVERT_EVENT, ''), call('WAZO_FWD_TYPE', ANY)]
        assert_that(self.agi.set_variable.call_args_list, equal_to(expected))
