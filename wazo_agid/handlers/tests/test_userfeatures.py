# Copyright 2013-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from unittest.mock import Mock, call, patch, sentinel

from hamcrest import assert_that, contains_exactly, equal_to
from requests.exceptions import HTTPError

from wazo_agid import dialplan_variables as dv
from wazo_agid import objects
from wazo_agid.handlers.userfeatures import UserFeatures


class NotEmptyStringMatcher:
    def __eq__(self, other):
        return isinstance(other, str) and bool(other)


class _BaseTestCase(unittest.TestCase):
    def setUp(self):
        self._auth_mock = Mock()
        self._confd_mock = Mock()
        self._set_confd_mock_outgoing_callerids([])
        config = {
            'auth': {'client': self._auth_mock},
            'call_recording': {
                'filename_template': '{{ mock }}',
                'filename_extension': 'wav',
            },
            'confd': {'client': self._confd_mock},
        }
        self._agi = Mock(config=config)
        self._cursor = Mock(cast=lambda x, y: '')
        self._args = Mock()

    def _set_confd_mock_outgoing_callerids(self, value):
        self._confd_mock.users.relations.return_value.list_outgoing_callerids.return_value = {
            'items': value
        }

    def _set_confd_mock_outgoing_callerids_side_effect(self, error):
        self._confd_mock.users.relations.return_value.list_outgoing_callerids.side_effect = (
            error
        )


class TestUserFeatures(_BaseTestCase):
    def setUp(self):
        super().setUp()
        self._variables = {
            'WAZO_USERID': '42',
            'WAZO_DSTID': '33',
            'WAZO_CALLORIGIN': 'my_origin',
            'WAZO_SRCNUM': '1000',
            'WAZO_DSTNUM': '1003',
            'WAZO_DST_EXTEN_ID': '983274',
            'WAZO_BASE_CONTEXT': 'default',
            'WAZO_CALL_RECORD_ACTIVE': '0',
            'WAZO_USER_MOH_UUID': '00000000-feed-dada-1ced-c0ffee000000',
        }

        self._agi.get_variable = lambda name: self._variables.get(name, '')

    def test_userfeatures(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        self.assertEqual(userfeatures._agi, self._agi)
        self.assertEqual(userfeatures._cursor, self._cursor)
        self.assertEqual(userfeatures._args, self._args)

    @patch('wazo_agid.objects.User', Mock())
    def test_set_members(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            userfeatures, _set_caller=Mock(), _set_line=Mock(), _set_user=Mock()
        ):
            userfeatures._set_members()

            self.assertEqual(userfeatures._userid, self._variables['WAZO_USERID'])
            self.assertEqual(userfeatures._dstid, self._variables['WAZO_DSTID'])
            self.assertEqual(userfeatures._zone, self._variables['WAZO_CALLORIGIN'])
            self.assertEqual(userfeatures._srcnum, self._variables['WAZO_SRCNUM'])
            self.assertEqual(userfeatures._dstnum, self._variables['WAZO_DSTNUM'])
            self.assertEqual(
                userfeatures._moh_uuid, self._variables['WAZO_USER_MOH_UUID']
            )
            self.assertTrue(userfeatures._set_caller.called)  # type: ignore
            self.assertTrue(userfeatures._set_line.called)  # type: ignore
            self.assertTrue(userfeatures._set_user.called)  # type: ignore

    def test_set_options_with_moh(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        moh = userfeatures._moh = Mock()
        moh.name = 'my-music-class'
        userfeatures._user = Mock(
            dtmf_hangup=False,
            enablexfer=False,
            enableonlinerec=False,
            incallfilter=False,
        )

        userfeatures._set_options()

        self._agi.set_variable.assert_called_once_with(
            'WAZO_CALLOPTIONS', 'm(my-music-class)'
        )

    def test_set_caller(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._set_caller()

        self.assertTrue(userfeatures._caller is None)

        userfeatures._userid = self._variables['WAZO_USERID']

        with patch('wazo_agid.objects.User') as user_init:
            user_init.return_value.simultcalls = 5

            userfeatures._set_caller()

            user_init.assert_called_with(
                self._agi, self._cursor, int(self._variables['WAZO_USERID'])
            )
            self._agi.set_variable.assert_called_once_with('WAZO_CALLER_SIMULTCALLS', 5)
        self.assertTrue(userfeatures._caller is not None)

    def test_set_call_record_enabled_incoming_external_call(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        userfeatures._user = Mock()
        userfeatures._zone = ''

        userfeatures._user.call_record_incoming_external_enabled = False
        userfeatures._set_call_record_enabled()
        self._agi.set_variable.assert_not_called()
        self._agi.set_variable.reset_mock()

        userfeatures._user.call_record_incoming_external_enabled = True
        userfeatures._set_call_record_enabled()

    def test_set_call_record_enabled_incoming_internal_call(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        userfeatures._user = Mock()
        userfeatures._zone = 'intern'

        userfeatures._user.call_record_incoming_internal_enabled = False
        userfeatures._set_call_record_enabled()
        self._agi.set_variable.assert_not_called()
        self._agi.set_variable.reset_mock()

        userfeatures._user.call_record_incoming_internal_enabled = True
        userfeatures._set_call_record_enabled()

    def test_set_call_record_enabled_already_recorded(self):
        self._variables['WAZO_CALL_RECORD_ACTIVE'] = '1'

        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        userfeatures._user = Mock(
            call_record_incoming_internal_enabled=True,
            call_record_incoming_external_enabled=True,
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=True,
        )
        userfeatures._caller = Mock(
            call_record_incoming_internal_enabled=True,
            call_record_incoming_external_enabled=True,
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=True,
        )

        userfeatures._set_call_record_enabled()

        self._agi.set_variable.assert_not_called()

    def test_set_call_record_enabled_from_group(self):
        self._variables['WAZO_FROMGROUP'] = '1'

        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        userfeatures._user = Mock(
            call_record_incoming_internal_enabled=True,
            call_record_incoming_external_enabled=True,
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=True,
        )
        userfeatures._caller = Mock(
            call_record_incoming_internal_enabled=True,
            call_record_incoming_external_enabled=True,
            call_record_outgoing_internal_enabled=True,
            call_record_outgoing_external_enabled=True,
        )

        userfeatures._set_call_record_enabled()

        self._agi.set_variable.assert_not_called()

    @patch('wazo_agid.handlers.userfeatures.extension_dao')
    @patch('wazo_agid.handlers.userfeatures.line_extension_dao')
    @patch('wazo_agid.handlers.userfeatures.line_dao')
    @patch('wazo_agid.handlers.userfeatures.user_line_dao')
    def test_set_line(self, user_line_dao, line_dao, line_extension_dao, extension_dao):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._set_line()
        self.assertEqual(userfeatures.lines, [])

        userfeatures._dstid = self._variables['WAZO_DSTID']
        user_lines = [Mock(user_id=1, line_id=10)]
        line = Mock(main_line=True)
        extension = Mock(exten='1234')

        user_line_dao.find_all_by.return_value = user_lines
        line_dao.find_by.return_value = line
        line_extension_dao.find_all_by.return_value = [Mock(extension_id=100)]
        extension_dao.get_by.return_value = extension

        userfeatures._set_line()

        self.assertEqual([line], userfeatures.lines)
        self.assertEqual(extension, userfeatures.main_extension)
        self.assertEqual(line, userfeatures.main_line)

    def test_set_user(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            userfeatures,
            _set_user_name=Mock(),
            _set_redirecting_info=Mock(),
            _set_wazo_uuid=Mock(),
        ):
            userfeatures._set_user()

            self.assertTrue(userfeatures._user is None)
            self.assertEqual(userfeatures._set_user_name.call_count, 0)  # type: ignore

            userfeatures._dstid = self._variables['WAZO_DSTID']

            with patch.object(objects.User, '__init__') as user_init:
                user_init.return_value = None

                userfeatures._set_user()

                userfeatures._set_user_name.assert_called_once()  # type: ignore
                userfeatures._set_redirecting_info.assert_called_once()  # type: ignore
                userfeatures._set_wazo_uuid.assert_called_once()  # type: ignore
                self.assertTrue(userfeatures._user is not None)
                self.assertTrue(isinstance(userfeatures._user, objects.User))

    def test_execute(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            userfeatures,
            _set_members=Mock(),
            _set_interfaces=Mock(),
            _call_filtering=Mock(),
        ):
            userfeatures.execute()
            userfeatures._set_members.assert_called_once()  # type: ignore
            userfeatures._set_interfaces.assert_called_once()  # type: ignore

    def test_build_interface_from_custom_line(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        line = Mock()
        line.protocol = 'CUSTOM'
        line.name = 'sip/abcd'

        interface = userfeatures._build_interface_from_line(line)

        self.assertEqual(interface, 'sip/abcd')

    def test_set_user_name(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._set_user_name()

        self._agi.assert_not_called()

        self._agi.set_variable.reset_mock()

        userfeatures._user = Mock()
        userfeatures._user.firstname = 'firstname'
        userfeatures._user.lastname = 'lastname'

        userfeatures._set_user_name()

        self._agi.set_variable.assert_called_once()

    def test_set_redirecting_info_full_callerid(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._user = Mock()
        userfeatures._user.callerid = '"Foobar" <123>'
        userfeatures._dstnum = '42'

        userfeatures._set_redirecting_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.DST_REDIRECTING_NAME, 'Foobar'),
                call(dv.DST_REDIRECTING_NUM, '123'),
                call('WAZO_DST_REDIRECTING_EXTERN_NAME', ''),
                call('WAZO_DST_REDIRECTING_EXTERN_NUM', ''),
            ),
        )

    def test_set_redirecting_info_no_callerid(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._user = Mock()
        userfeatures._user.firstname = 'First'
        userfeatures._user.lastname = 'Last'
        userfeatures._user.callerid = ''
        userfeatures._dstnum = '42'

        userfeatures._set_redirecting_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.DST_REDIRECTING_NAME, 'First Last'),
                call(dv.DST_REDIRECTING_NUM, '42'),
                call('WAZO_DST_REDIRECTING_EXTERN_NAME', ''),
                call('WAZO_DST_REDIRECTING_EXTERN_NUM', ''),
            ),
        )

    def test_set_redirecting_info_line(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._user = Mock()
        userfeatures._user.callerid = '"Foobar"'
        userfeatures.main_extension = Mock(exten='32')
        userfeatures._dstnum = '42'

        userfeatures._set_redirecting_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.DST_REDIRECTING_NAME, 'Foobar'),
                call(dv.DST_REDIRECTING_NUM, '32'),
                call('WAZO_DST_REDIRECTING_EXTERN_NAME', ''),
                call('WAZO_DST_REDIRECTING_EXTERN_NUM', ''),
            ),
        )

    def test_set_redirecting_info_no_outgoing_callerids(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._user = Mock()
        userfeatures._user.callerid = '"Foobar"'
        userfeatures.main_extension = Mock(exten='32')
        userfeatures._dstnum = '42'
        self._set_confd_mock_outgoing_callerids_side_effect(HTTPError(404))

        userfeatures._set_redirecting_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.DST_REDIRECTING_NAME, 'Foobar'),
                call(dv.DST_REDIRECTING_NUM, '32'),
                call('WAZO_DST_REDIRECTING_EXTERN_NAME', ''),
                call('WAZO_DST_REDIRECTING_EXTERN_NUM', ''),
            ),
        )

    def test_set_redirecting_info_associated_outgoing_callerid(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._user = Mock()
        userfeatures._user.callerid = '"Foobar"'
        userfeatures.main_extension = Mock(exten='32')
        userfeatures._dstnum = '42'
        self._set_confd_mock_outgoing_callerids(
            [
                {
                    'type': 'associated',
                    'number': '4242',
                },
                {
                    'type': 'main',
                    'number': '4343',
                },
            ]
        )

        userfeatures._set_redirecting_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.DST_REDIRECTING_NAME, 'Foobar'),
                call(dv.DST_REDIRECTING_NUM, '32'),
                call('WAZO_DST_REDIRECTING_EXTERN_NAME', '4242'),
                call('WAZO_DST_REDIRECTING_EXTERN_NUM', '4242'),
            ),
        )

    def test_set_redirecting_info_associated_main_callerid(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)

        userfeatures._user = Mock()
        userfeatures._user.callerid = '"Foobar"'
        userfeatures.main_extension = Mock(exten='32')
        userfeatures._dstnum = '42'
        self._set_confd_mock_outgoing_callerids(
            [
                {
                    'type': 'main',
                    'number': '4343',
                },
                {
                    'type': 'shared',
                    'number': '4444',
                },
            ]
        )

        userfeatures._set_redirecting_info()

        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.DST_REDIRECTING_NAME, 'Foobar'),
                call(dv.DST_REDIRECTING_NUM, '32'),
                call('WAZO_DST_REDIRECTING_EXTERN_NAME', '4343'),
                call('WAZO_DST_REDIRECTING_EXTERN_NUM', '4343'),
            ),
        )

    def test_set_callfilter_ringseconds_zero(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        name = 'WAZO_CALLFILTER_TIMEOUT'
        value = 0

        userfeatures._set_callfilter_ringseconds('TIMEOUT', value)

        self._agi.set_variable.assert_called_once_with(name, '')

    def test_set_callfilter_ringseconds_negative(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        name = 'WAZO_CALLFILTER_TIMEOUT'
        value = -42

        userfeatures._set_callfilter_ringseconds('TIMEOUT', value)

        self._agi.set_variable.assert_called_once_with(name, '')

    def test_set_callfilter_ringseconds(self):
        userfeatures = UserFeatures(self._agi, self._cursor, self._args)
        name = 'WAZO_CALLFILTER_TIMEOUT'
        value = 1

        userfeatures._set_callfilter_ringseconds('TIMEOUT', value)

        self._agi.set_variable.assert_called_once_with(name, value)

    def test_set_video_enabled(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        self._variables['CHANNEL(videonativeformat)'] = '(vp9)'

        user_features._set_video_enabled()

        assert_that(self._agi.set_variable.called_once_with('WAZO_VIDEO_ENABLED', '1'))


class TestSetForwardNoAnswer(_BaseTestCase):
    def test_forward_no_answer_to_a_user_dialaction(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        user_features._user = Mock(objects.User, id=sentinel.userid)
        self._cursor.fetchone = Mock(
            return_value={
                'action': 'user',
                'actionarg1': '5',
                'actionarg2': '',
            }
        )

        enabled = user_features._set_rna_from_dialaction()

        assert_that(enabled, equal_to(True))
        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.FWD_USER_NOANSWER_ACTION, 'user'),
                call(dv.FWD_USER_NOANSWER_ISDA, '1'),
                call(dv.FWD_USER_NOANSWER_ACTIONARG1, '5'),
                call(dv.FWD_USER_NOANSWER_ACTIONARG2, ''),
            ),
        )

    def test_forward_no_answer_to_a_user_from_exten_fwdrna_disabled_on_user(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        user_features._user = Mock(objects.User, enablerna=False)

        enabled = user_features._set_rna_from_exten()

        assert_that(enabled, equal_to(False))

    def test_forward_no_answer_to_a_user_from_exten(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        user_features._user = Mock(objects.User, destrna='555', enablerna=True)
        user_features.main_extension = Mock(context=sentinel.context)

        enabled = user_features._set_rna_from_exten()

        assert_that(enabled, equal_to(True))
        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.FWD_USER_NOANSWER_ACTION, 'extension'),
                call(dv.FWD_USER_NOANSWER_ACTIONARG1, '555'),
                call(dv.FWD_USER_NOANSWER_ACTIONARG2, sentinel.context),
            ),
        )

    def test_setrna_exten_disabled_noanswer_enabled(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            user_features,
            _set_rna_from_exten=Mock(return_value=False),
            _set_rna_from_dialaction=Mock(return_value=True),
        ):
            user_features._setrna()
            user_features._set_rna_from_exten.assert_called_once_with()  # type: ignore
            assert_that(self._agi.set_variable.called_once_with(dv.ENABLERNA, True))

    def test_setrna_exten_disabled_noanswer_disabled(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            user_features,
            _set_rna_from_exten=Mock(return_value=False),
            _set_rna_from_dialaction=Mock(return_value=False),
        ):
            user_features._setrna()

            user_features._set_rna_from_exten.assert_called_once_with()  # type: ignore
            user_features._set_rna_from_dialaction.assert_called_once_with()  # type: ignore

            self._agi.set_variable.assert_not_called()


class TestSetForwardBusy(_BaseTestCase):
    def test_forward_busy_to_a_user_dialaction(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        user_features._user = Mock(objects.User, id=sentinel.userid)
        self._cursor.fetchone = Mock(
            return_value={
                'action': 'user',
                'actionarg1': '5',
                'actionarg2': '',
            }
        )

        enabled = user_features._set_rbusy_from_dialaction()

        assert_that(enabled, equal_to(True))
        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.FWD_USER_BUSY_ACTION, 'user'),
                call(dv.FWD_USER_BUSY_ISDA, '1'),
                call(dv.FWD_USER_BUSY_ACTIONARG1, '5'),
                call(dv.FWD_USER_BUSY_ACTIONARG2, ''),
            ),
        )

    def test_forward_busy_to_a_user_from_exten_fwdbusy_disabled_on_user(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        user_features._user = Mock(objects.User, enablebusy=False)

        enabled = user_features._set_rbusy_from_exten()

        assert_that(enabled, equal_to(False))

    def test_forward_busy_to_a_user_from_exten(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        user_features._user = Mock(objects.User, destbusy='666', enablebusy=True)
        user_features.main_extension = Mock(context=sentinel.context)

        enabled = user_features._set_rbusy_from_exten()

        assert_that(enabled, equal_to(True))
        assert_that(
            self._agi.set_variable.call_args_list,
            contains_exactly(
                call(dv.FWD_USER_BUSY_ACTION, 'extension'),
                call(dv.FWD_USER_BUSY_ACTIONARG1, '666'),
                call(dv.FWD_USER_BUSY_ACTIONARG2, sentinel.context),
            ),
        )

    def test_set_rbusy_exten_disabled_noanswer_enabled(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            user_features,
            _set_rbusy_from_exten=Mock(return_value=False),
            _set_rbusy_from_dialaction=Mock(return_value=True),
        ):
            user_features._setbusy()
            user_features._set_rbusy_from_exten.assert_called_once_with()  # type: ignore
            assert_that(self._agi.set_variable.called_once_with(dv.ENABLEBUSY, True))

    def test_set_busy_exten_disabled_noanswer_disabled(self):
        user_features = UserFeatures(self._agi, self._cursor, self._args)
        with patch.multiple(
            user_features,
            _set_rbusy_from_exten=Mock(return_value=False),
            _set_rbusy_from_dialaction=Mock(return_value=False),
        ):
            user_features._setbusy()

            user_features._set_rbusy_from_exten.assert_called_once_with()  # type: ignore
            user_features._set_rbusy_from_dialaction.assert_called_once_with()  # type: ignore

            self._agi.set_variable.assert_not_called()
