# Copyright 2021-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, call, patch

from wazo_agid import dialplan_variables as dv

from ..call_recording import record_caller


class TestRecordCaller(TestCase):
    def setUp(self):
        self.agi = Mock()
        self.agi.get_variable = Mock()
        self.cursor = Mock()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    def test_record_caller_does_not_start_recording_when_already_recording(
        self, start_mix_monitor
    ):
        self.agi.get_variable.return_value = '1'

        record_caller(self.agi, self.cursor, [])

        start_mix_monitor.assert_not_called()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    def test_record_caller_does_not_start_recording_when_no_user_id_or_uuid(
        self, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERID': '',
            'WAZO_USERUUID': '',
        }
        self.agi.get_variable.side_effect = agi_variables.get

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call('WAZO_USERID'),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_not_called()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_does_not_start_recording_fallback_to_user_id_when_no_uuid(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERID': '1',
            'WAZO_USERUUID': '',
        }
        self.agi.get_variable.side_effect = agi_variables.get

        record_caller(self.agi, self.cursor, [])

        calls = [call('WAZO_CALL_RECORD_ACTIVE'), call('WAZO_USERUUID')]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_called_once()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_does_not_record_when_not_an_outcall(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=False,
            call_record_outgoing_external_enabled=False,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_not_called()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_does_not_record_when_an_outcall_but_disabled(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '1',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=False,
            call_record_outgoing_external_enabled=False,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_not_called()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_records_when_an_outcall_and_enabled(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '1',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=False,
            call_record_outgoing_external_enabled=True,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_called_once()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_does_not_record_when_an_outcall_but_internal_enabled(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '1',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=False,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_not_called()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_records_when_not_an_outcall_and_internal_enabled(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=False,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_called_once()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_records_when_an_outcall_and_all_enabled(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '1',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=True,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_called_once()

    @patch('wazo_agid.modules.call_recording._start_mix_monitor')
    @patch('wazo_agid.objects.User')
    def test_record_caller_records_when_not_an_outcall_and_all_enabled(
        self, user, start_mix_monitor
    ):
        agi_variables = {
            'WAZO_CALL_RECORD_ACTIVE': '',
            'WAZO_USERUUID': 'the-users-uuid',
            dv.OUTCALL_ID: '',
        }
        self.agi.get_variable.side_effect = agi_variables.get
        user.return_value = Mock(
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=True,
        )

        record_caller(self.agi, self.cursor, [])

        calls = [
            call('WAZO_CALL_RECORD_ACTIVE'),
            call('WAZO_USERUUID'),
            call(dv.OUTCALL_ID),
        ]
        self.agi.get_variable.assert_has_calls(calls)

        start_mix_monitor.assert_called_once()
