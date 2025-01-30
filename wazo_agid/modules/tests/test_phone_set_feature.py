# Copyright 2016-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from wazo_agid import dialplan_variables as dv
from wazo_agid.modules.phone_set_feature import (
    _phone_set_busy,
    _phone_set_dnd,
    _phone_set_incallfilter,
    _phone_set_rna,
    _phone_set_unc,
)


class TestPhoneSetFeature(unittest.TestCase):
    def setUp(self):
        self._user_id = 2
        self._client = Mock().return_value
        self._agi = Mock()
        self._agi.config = {'confd': {'client': self._client}}
        self._agi.get_variable.return_value = self._user_id

    def test_phone_set_dnd(self):
        self._client.users(self._user_id).get_service.return_value = {'enabled': True}

        _phone_set_dnd(self._agi, None, None)

        self._client.users(self._user_id).get_service.assert_called_once_with('dnd')
        self._client.users(self._user_id).update_service.assert_called_once_with(
            'dnd', {'enabled': False}
        )
        expected_calls = [
            call(dv.DNDENABLED, False),
            call(dv.USERID_OWNER, self._user_id),
        ]
        self._agi.set_variable.assert_has_calls(expected_calls)

    def test_phone_set_incallfilter(self):
        self._client.users(self._user_id).get_service.return_value = {'enabled': False}

        _phone_set_incallfilter(self._agi, None, None)

        self._client.users(self._user_id).get_service.assert_called_once_with(
            'incallfilter'
        )
        self._client.users(self._user_id).update_service.assert_called_once_with(
            'incallfilter', {'enabled': True}
        )
        expected_calls = [
            call(dv.INCALLFILTERENABLED, True),
            call(dv.USERID_OWNER, self._user_id),
        ]
        self._agi.set_variable.assert_has_calls(expected_calls)

    def test_phone_set_busy(self):
        args = [None, '1', '123']

        _phone_set_busy(self._agi, None, args)

        self._client.users(self._user_id).update_forward.assert_called_once_with(
            'busy', {'enabled': True, 'destination': '123'}
        )
        expected_calls = [
            call(dv.USERID_OWNER, self._user_id),
            call(dv.BUSYENABLED, 1),
        ]
        self._agi.set_variable.assert_has_calls(expected_calls)

    def test_phone_set_busy_do_not_set_variable_when_raise_exception(self):
        args = [None, '1', '123']
        self._client.users(self._user_id).update_forward.side_effect = Exception()

        _phone_set_busy(self._agi, None, args)

        self._agi.set_variable.assert_not_called()

    def test_phone_set_rna(self):
        args = [None, '0', '']

        _phone_set_rna(self._agi, None, args)

        self._client.users(self._user_id).update_forward.assert_called_once_with(
            'noanswer', {'enabled': False}
        )
        expected_calls = [
            call(dv.USERID_OWNER, self._user_id),
            call(dv.RNAENABLED, 0),
        ]
        self._agi.set_variable.assert_has_calls(expected_calls)

    def test_phone_set_rna_do_not_set_variable_when_raise_exception(self):
        args = [None, '1', '123']
        self._client.users(self._user_id).update_forward.side_effect = Exception()

        _phone_set_rna(self._agi, None, args)

        self._agi.set_variable.assert_not_called()

    def test_phone_set_unc(self):
        args = [None, '1', '123']

        _phone_set_unc(self._agi, None, args)

        self._client.users(self._user_id).update_forward.assert_called_once_with(
            'unconditional', {'enabled': True, 'destination': '123'}
        )
        expected_calls = [
            call(dv.USERID_OWNER, self._user_id),
            call(dv.UNCENABLED, 1),
        ]
        self._agi.set_variable.assert_has_calls(expected_calls)

    def test_phone_set_unc_do_not_set_variable_when_raise_exception(self):
        args = [None, '1', '123']
        self._client.users(self._user_id).update_forward.side_effect = Exception()

        _phone_set_unc(self._agi, None, args)

        self._agi.set_variable.assert_not_called()
