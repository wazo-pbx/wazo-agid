# Copyright 2013-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from collections import defaultdict
from typing import Any
from unittest.mock import Mock, call, patch

from hamcrest import assert_that, contains_exactly
from hamcrest.core import equal_to
from typing_extensions import Self

from wazo_agid import dialplan_variables as dv
from wazo_agid import objects
from wazo_agid.handlers.outgoingfeatures import OutgoingFeatures


class TenantBuilder:
    def __init__(self) -> None:
        self._country: str = ''

    def with_country(self, country: str) -> Self:
        self._country = country
        return self

    def build(self) -> objects.Tenant:
        tenant = Mock(objects.Tenant)
        tenant.country = self._country
        return tenant


class TrunkBuilder:
    def __init__(self) -> None:
        self._outgoing_caller_id_format: str = ''
        self._interface: str = ''
        self._intfsuffix: str = ''

    def with_outgoing_caller_id_format(self, outgoing_caller_id_format: str) -> Self:
        self._outgoing_caller_id_format = outgoing_caller_id_format
        return self

    def with_interface(self, interface: str) -> Self:
        self._interface = interface
        return self

    def build(self) -> objects.Trunk:
        trunk = Mock(objects.Trunk)
        trunk.outgoing_caller_id_format = self._outgoing_caller_id_format
        trunk.interface = self._interface
        trunk.intfsuffix = self._intfsuffix
        return trunk


class OutCallBuilder:
    def __init__(self) -> None:
        self._internal: int = 0
        self._caller_id: str = ''
        self._trunks: list = []

    def with_caller_id(self, caller_id: str) -> Self:
        self._caller_id = caller_id
        return self

    def with_trunk(self, trunk: objects.Trunk) -> Self:
        self._trunks.append(trunk)
        return self

    def internal(self) -> Self:
        self._internal = 1
        return self

    def external(self) -> Self:
        self._internal = 0
        return self

    def build(self) -> objects.Outcall:
        outcall = Mock(objects.Outcall)
        outcall.callerid = self._caller_id
        outcall.internal = self._internal
        outcall.trunks = []
        for trunk in self._trunks:
            outcall.trunks.append(trunk)
        return outcall


class UserBuilder:
    def __init__(self) -> None:
        self._caller_id: str = '"John"'
        self._out_caller_id: str = 'default'
        self._userfield: str = ''
        self._musiconhold: str = ''

    def with_caller_id(self, caller_id: str) -> Self:
        self._caller_id = caller_id
        return self

    def with_default_outgoing_caller_id(self) -> Self:
        self._out_caller_id = 'default'
        return self

    def with_anonymous_out_caller_id(self) -> Self:
        self._out_caller_id = 'anonymous'
        return self

    def with_custom_out_caller_id(self, caller_id: str) -> Self:
        self._out_caller_id = caller_id
        return self

    def with_user_field(self, userfield: str) -> Self:
        self._userfield = userfield
        return self

    def with_moh(self, moh: str) -> Self:
        self._musiconhold = moh
        return self

    def build(self) -> objects.User:
        user = Mock(objects.User)
        user.callerid = self._caller_id
        user.outcallerid = self._out_caller_id
        user.userfield = self._userfield
        user.musiconhold = self._musiconhold
        return user


def an_outcall() -> OutCallBuilder:
    return OutCallBuilder()


def a_tenant() -> TenantBuilder:
    return TenantBuilder()


def a_trunk() -> TrunkBuilder:
    return TrunkBuilder()


def a_user() -> UserBuilder:
    return UserBuilder()


class BaseOutgoingFeaturesTestCase(unittest.TestCase):
    def setUp(self):
        config = {
            'call_recording': {
                'filename_template': '{{ mock }}',
                'filename_extension': 'wav',
            }
        }
        agi_environment = {'agi_channel': 'PJSIP/my-channel-0001'}
        self._channel_variables: defaultdict[str, Any] = defaultdict(str)
        self._agi = Mock(config=config, env=agi_environment)
        self._agi.get_variable.side_effect = self._channel_variables.get
        self._cursor = Mock()
        self._args = Mock()
        self.outgoing_features = OutgoingFeatures(self._agi, self._cursor, self._args)


class TestSetTrunkInfo(BaseOutgoingFeaturesTestCase):
    def test_set_trunk_info(self) -> None:
        trunk1 = (
            a_trunk()
            .with_interface('PJSIP/abc')
            .with_outgoing_caller_id_format('+E164')
            .build()
        )
        trunk2 = (
            a_trunk()
            .with_interface('PJSIP/def')
            .with_outgoing_caller_id_format('national')
            .build()
        )
        outcall = an_outcall().with_trunk(trunk1).with_trunk(trunk2).build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.dstnum = '911'

        self.outgoing_features._set_trunk_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                # Trunk 0
                call('WAZO_OUTGOING_CALLER_ID_FORMAT0', '+E164'),
                call('WAZO_INTERFACE0', 'PJSIP'),
                call(f'{dv.TRUNK_EXTEN}0', '911@abc'),
                call(f'{dv.TRUNK_SUFFIX}0', ''),
                # Trunk 1
                call('WAZO_OUTGOING_CALLER_ID_FORMAT1', 'national'),
                call('WAZO_INTERFACE1', 'PJSIP'),
                call(f'{dv.TRUNK_EXTEN}1', '911@def'),
                call(f'{dv.TRUNK_SUFFIX}1', ''),
            ),
        )


class TestSetUserField(BaseOutgoingFeaturesTestCase):
    def test_user_field_value(self) -> None:
        userfield = 'CP1234'
        user = a_user().with_user_field(userfield).build()
        outcall = an_outcall().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_userfield()

        self._agi.set_variable.assert_called_once_with('CHANNEL(userfield)', userfield)

    def test_empty(self) -> None:
        user = a_user().build()
        outcall = an_outcall().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_userfield()

        assert_that(
            self._agi.set_variable.call_count, equal_to(0), 'Set variable call count'
        )

    def test_no_user_no_error(self) -> None:
        outcall = an_outcall().build()

        self.outgoing_features.outcall = outcall

        self.outgoing_features._set_userfield()


class TestSetTenantCountry(BaseOutgoingFeaturesTestCase):
    def test_no_tenant(self) -> None:
        self.outgoing_features._set_tenant_country()

        self._agi.set_variable.assert_called_once_with('WAZO_TENANT_COUNTRY', '')

    def test_tenant_has_no_country(self) -> None:
        tenant = a_tenant().build()
        self.outgoing_features.tenant = tenant

        self.outgoing_features._set_tenant_country()

        self._agi.set_variable.assert_called_once_with('WAZO_TENANT_COUNTRY', '')

    def test_tenant_with_a_country(self) -> None:
        tenant = a_tenant().with_country('CA').build()
        self.outgoing_features.tenant = tenant

        self.outgoing_features._set_tenant_country()

        self._agi.set_variable.assert_called_once_with('WAZO_TENANT_COUNTRY', 'CA')


class TestSetUserMusicOnHold(BaseOutgoingFeaturesTestCase):
    def test_set_value(self) -> None:
        moh = 'a-moh'
        user = a_user().with_moh(moh).build()
        outcall = an_outcall().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_user_music_on_hold()

        self._agi.set_variable.assert_called_once_with('CHANNEL(musicclass)', moh)

    def test_empty(self) -> None:
        user = a_user().build()
        outcall = an_outcall().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_user_music_on_hold()

        assert_that(
            self._agi.set_variable.call_count, equal_to(0), 'Set variable call count'
        )

    def test_no_user_no_error(self) -> None:
        outcall = an_outcall().build()

        self.outgoing_features.outcall = outcall

        self.outgoing_features._set_user_music_on_hold()


class TestSetCallerId(BaseOutgoingFeaturesTestCase):
    @patch('wazo_agid.objects.CallerID.set')
    def test_outcall_internal(self, mock_set_caller_id) -> None:
        user = a_user().build()
        outcall = an_outcall().internal().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        self.assertFalse(mock_set_caller_id.called)

    @patch('wazo_agid.objects.CallerID.set')
    def test_no_user_and_outcall_external(self, mock_set_caller_id) -> None:
        user = None
        outcall = an_outcall().external().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        self.assertFalse(mock_set_caller_id.called)

    @patch('wazo_agid.objects.CallerID.set')
    def test_no_user_and_outcall_external_caller_id(self, mock_set_caller_id) -> None:
        user = None
        outcall = an_outcall().external().with_caller_id('27857218').build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        mock_set_caller_id.assert_called_once_with(self._agi, '27857218')

    @patch('wazo_agid.objects.CallerID.set')
    def test_user_default_and_outcall_external(self, mock_set_caller_id) -> None:
        user = a_user().with_default_outgoing_caller_id().build()
        outcall = an_outcall().external().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        self.assertFalse(mock_set_caller_id.called)

    @patch('wazo_agid.objects.CallerID.set')
    def test_user_default_and_outcall_external_caller_id(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_default_outgoing_caller_id().build()
        outcall = an_outcall().external().with_caller_id('27857218').build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        mock_set_caller_id.assert_called_once_with(self._agi, '27857218')

    @patch('wazo_agid.objects.CallerID.set')
    def test_user_anonymous_and_outcall_external(self, mock_set_caller_id) -> None:
        user = a_user().with_anonymous_out_caller_id().build()
        outcall = an_outcall().external().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        expected_calls = [
            call('CALLERID(pres)', 'prohib'),
            call('WAZO_OUTGOING_ANONYMOUS_CALL', '1'),
        ]
        self.assertEqual(self._agi.set_variable.call_args_list, expected_calls)
        self.assertFalse(mock_set_caller_id.called)

    @patch('wazo_agid.objects.CallerID.set')
    def test_user_anonymous_and_outcall_external_caller_id(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_anonymous_out_caller_id().build()
        outcall = an_outcall().external().with_caller_id('27857218').build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        expected_calls = [
            call('CALLERID(pres)', 'prohib'),
            call('WAZO_OUTGOING_ANONYMOUS_CALL', '1'),
            call('_WAZO_OUTCALL_PAI_NUMBER', '27857218'),
        ]
        self.assertEqual(self._agi.set_variable.call_args_list, expected_calls)
        self.assertFalse(mock_set_caller_id.called)

    @patch('wazo_agid.objects.CallerID.set')
    def test_user_custom_and_outcall_external(self, mock_set_caller_id) -> None:
        user = a_user().with_custom_out_caller_id('"Custom1"').build()
        outcall = an_outcall().external().build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        mock_set_caller_id.assert_called_once_with(self._agi, '"Custom1"')

    @patch('wazo_agid.objects.CallerID.set')
    def test_user_custom_and_outcall_external_caller_id(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_custom_out_caller_id('"Custom1"').build()
        outcall = an_outcall().external().with_caller_id('27857218').build()

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        mock_set_caller_id.assert_called_once_with(self._agi, '"Custom1"')

    @patch('wazo_agid.objects.CallerID.set')
    def test_from_SIP_header_user_custom_outcall_custom(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_custom_out_caller_id('"Custom1"').build()
        outcall = an_outcall().external().with_caller_id('27857218').build()
        caller_id_header = '5555551234'
        self._channel_variables[
            'PJSIP_HEADER(read,X-Wazo-Selected-Caller-ID)'
        ] = caller_id_header

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        self._agi.set_variable.assert_called_once_with(
            dv.SELECTED_CALLER_ID, caller_id_header
        )

    @patch('wazo_agid.objects.CallerID.set')
    def test_anonymous_caller_id_from_SIP_header_user_custom_outcall_custom(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_custom_out_caller_id('"Custom1"').build()
        outcall = an_outcall().external().with_caller_id('27857218').build()
        caller_id_header = 'anonymous'
        self._channel_variables[
            'PJSIP_HEADER(read,X-Wazo-Selected-Caller-ID)'
        ] = caller_id_header

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        calls = [
            call('CALLERID(pres)', 'prohib'),
            call('WAZO_OUTGOING_ANONYMOUS_CALL', '1'),
            call('_WAZO_OUTCALL_PAI_NUMBER', '27857218'),
        ]
        for mock_call in calls:
            assert mock_call in self._agi.set_variable.call_args_list

    @patch('wazo_agid.objects.CallerID.set')
    def test_anonymous_caller_id_from_SIP_header_no_outcall_cid(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_custom_out_caller_id('"Custom1"').build()
        outcall = an_outcall().external().build()
        caller_id_header = 'anonymous'
        self._channel_variables[
            'PJSIP_HEADER(read,X-Wazo-Selected-Caller-ID)'
        ] = caller_id_header

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        calls = [
            call('CALLERID(pres)', 'prohib'),
            call('WAZO_OUTGOING_ANONYMOUS_CALL', '1'),
        ]
        for mock_call in calls:
            assert mock_call in self._agi.set_variable.call_args_list

    @patch('wazo_agid.objects.CallerID.set')
    def test_anonymous_caller_id_from_SIP_header_user_default(
        self, mock_set_caller_id
    ) -> None:
        user = a_user().with_custom_out_caller_id('default').build()
        outcall = an_outcall().external().build()
        caller_id_header = 'anonymous'
        self._channel_variables[
            'PJSIP_HEADER(read,X-Wazo-Selected-Caller-ID)'
        ] = caller_id_header

        self.outgoing_features.outcall = outcall
        self.outgoing_features.user = user

        self.outgoing_features._set_caller_id()

        calls = [
            call('CALLERID(pres)', 'prohib'),
            call('WAZO_OUTGOING_ANONYMOUS_CALL', '1'),
        ]
        for mock_call in calls:
            assert mock_call in self._agi.set_variable.call_args_list


class TestRetrieveOutcall(BaseOutgoingFeaturesTestCase):
    def test_retreive_outcall(self) -> None:
        outcall = Mock(objects.Outcall)
        self.outgoing_features.outcall = outcall
        self.outgoing_features.dialpattern_id = '23'

        self.outgoing_features._retrieve_outcall()

        outcall.retrieve_values.assert_called_once_with('23')
