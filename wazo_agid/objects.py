# Copyright 2007-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from psycopg2.extras import DictCursor, DictRow
from psycopg2.sql import SQL, Composable, Identifier
from xivo_dao import user_dao

from wazo_agid import dialplan_variables as dv
from wazo_agid.schedule import (
    AlwaysOpenedSchedule,
    Schedule,
    ScheduleAction,
    SchedulePeriodBuilder,
)

if TYPE_CHECKING:
    from typing import Literal

    from wazo_agid.agid import FastAGI

logger = logging.getLogger(__name__)


class DBUpdateException(Exception):
    pass


def sanitize_column(name: str) -> Identifier:
    """
    Take a list of fields and join them together for insertion, safely, into SQL query.
    """
    return Identifier(*name.split("."))


def sanitize_aliased_column(name: str, alias: str) -> Composable:
    return Identifier(*name.split(".")) + SQL(" AS ") + Identifier(alias)


def join_column_names(fields: Sequence[str]) -> Composable:
    """
    Take a list of fields and join them together for insertion, safely, into SQL query.
    """
    return SQL(',').join(sanitize_column(f) for f in fields)


class ExtenFeatures:
    FEATURES = {
        'agents': (
            'agentstaticlogin',
            'agentstaticlogoff',
            'agentstaticlogtoggle',
        ),
        'forwards': (
            'fwdbusy',
            'fwdrna',
            'fwdunc',
        ),
        'groupmember': (
            'groupmemberjoin',
            'groupmemberleave',
            'groupmembertoggle',
        ),
        'services': (
            'enablevm',
            'callrecord',
            'incallfilter',
            'enablednd',
        ),
    }

    def __init__(self, agi, cursor: DictCursor):
        self.agi = agi
        self.cursor = cursor

        featureslist: list[str] = []

        for xtype in self.FEATURES.values():
            for x in xtype:
                featureslist.append(x)

        self.featureslist = tuple(featureslist)

        self.cursor.execute(
            "SELECT feature FROM feature_extension "
            "WHERE feature IN (" + ", ".join(["%s"] * len(self.featureslist)) + ") "
            "AND enabled = true",
            self.featureslist,
        )
        res: list[DictRow] = self.cursor.fetchall()

        if not res:
            enabled_features = []
        else:
            enabled_features = [row['feature'] for row in res]

        for feature in self.featureslist:
            setattr(self, feature, (feature in enabled_features))

    def get_name_by_exten(self, exten):
        self.cursor.execute(
            "SELECT feature FROM feature_extension "
            "WHERE feature IN (" + ", ".join(["%s"] * len(self.featureslist)) + ") "
            "AND (exten = %s "
            "OR (SUBSTR(exten,1,1) = '_' "
            "    AND SUBSTR(exten, 2, %s) LIKE %s)) "
            "AND enabled = true",
            self.featureslist + (exten, len(exten), f"{exten}%"),
        )

        res: DictRow = self.cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find feature by exten (exten = {exten!r})")

        return res['feature']

    def get_exten_by_name(self, name):
        query = "SELECT exten FROM feature_extension WHERE feature = %s"
        params = [name]

        self.cursor.execute(query, params)

        res: DictRow = self.cursor.fetchone()

        if not res:
            raise LookupError(f"Unable to find feature by name (name = {name!r})")

        return res['exten']


class VMBox:
    id: int
    mailbox: str
    context: str
    password: str | None
    email: str | None
    commented: Literal[0, 1]
    language: str | None
    skipcheckpass: Literal[0, 1]

    def __init__(
        self,
        agi,
        cursor: DictCursor,
        xid=None,
        mailbox=None,
        context=None,
        commentcond=True,
    ):
        self.agi = agi
        self.cursor = cursor

        vm_columns = (
            'uniqueid',
            'mailbox',
            'context',
            'password',
            'email',
            'commented',
            'language',
            'skipcheckpass',
        )
        columns = ["voicemail." + c for c in vm_columns]

        if commentcond:
            where_comment = "AND voicemail.commented = 0"
        else:
            where_comment = ""

        if xid:
            query = SQL(
                "SELECT {columns} FROM voicemail WHERE voicemail.uniqueid = %s "
                + where_comment
            )
            cursor.execute(query.format(columns=join_column_names(columns)), (xid,))
        elif mailbox and context:
            contextinclude = Context(agi, cursor, context).include
            query = SQL(
                "SELECT {columns} FROM voicemail "
                "WHERE voicemail.mailbox = %s "
                "AND voicemail.context IN ("
                + ", ".join(["%s"] * len(contextinclude))
                + ") "
                + where_comment
            )
            cursor.execute(
                query.format(columns=join_column_names(columns)),
                [mailbox] + contextinclude,
            )
        else:
            raise LookupError(
                "id or mailbox@context must be provided to look up a voicemail entry"
            )

        res: DictRow = cursor.fetchone()

        if not res:
            raise LookupError(
                f"Unable to find voicemail box (id: {xid}, mailbox: {mailbox}, context: {context})"
            )

        self.id = res['uniqueid']
        self.mailbox = res['mailbox']
        self.context = res['context']
        self.password = res['password']
        self.email = res['email']
        self.commented = res['commented']
        self.language = res['language']
        self.skipcheckpass = res['skipcheckpass']

    def toggle_enable(self, enabled=None):
        if enabled is None:
            enabled = int(not self.commented)
        else:
            enabled = int(not bool(enabled))

        self.cursor.execute(
            "UPDATE voicemail SET commented = %s WHERE uniqueid = %s",
            (enabled, self.id),
        )

        if self.cursor.rowcount != 1:
            raise DBUpdateException("Unable to perform the requested update")
        self.commented = enabled

    def has_password(self) -> bool:
        return bool(self.password) and self.skipcheckpass == 0


class Meeting:
    def __init__(self, agi, cursor: DictCursor, tenant_uuid, uuid=None, number=None):
        self.agi = agi
        self.cursor = cursor
        self.uuid = uuid
        self.number = number
        self.tenant_uuid = tenant_uuid

        query = SQL(
            "SELECT uuid, name FROM meeting WHERE {field} = %s and tenant_uuid = %s"
        )
        if uuid:
            field = 'uuid'
            arguments = (uuid, tenant_uuid)
        elif number:
            field = 'number'
            arguments = (number, tenant_uuid)
        else:
            raise Exception('Cannot find a meeting with no UUID or number')

        cursor.execute(query.format(field=Identifier(field)), arguments)

        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f'Unable to find Meeting {uuid} in tenant {tenant_uuid}')

        self.uuid = res['uuid']
        self.name = res['name']


class MOH:
    def __init__(self, agi, cursor, uuid):
        self.agi = agi
        self.cursor = cursor
        self.name = None

        cursor.execute(
            "SELECT name FROM moh WHERE uuid = %s",
            (uuid,),
        )

        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f'Unable to find MOH {uuid}')

        self.name = res['name']


class Paging:
    def __init__(self, agi, cursor, number, userid):
        self.agi = agi
        self.cursor = cursor
        self.lines = set()

        columns = (
            'id',
            'number',
            'duplex',
            'ignore',
            'record',
            'quiet',
            'timeout',
            'announcement_file',
            'announcement_play',
            'announcement_caller',
            'commented',
            'tenant_uuid',
        )

        query = SQL("SELECT {columns} FROM paging WHERE number = %s AND commented = 0")
        cursor.execute(query.format(columns=join_column_names(columns)), (number,))
        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find paging entry (number: {number})")

        paging_id = res['id']
        self.tenant_uuid = res['tenant_uuid']
        self.number = res['number']
        self.duplex = res['duplex']
        self.ignore = res['ignore']
        self.record = res['record']
        self.quiet = res['quiet']
        self.timeout = res['timeout']
        self.announcement_file = res['announcement_file']
        self.announcement_play = res['announcement_play']
        self.announcement_caller = res['announcement_caller']

        cursor.execute(
            "SELECT userfeaturesid FROM paginguser "
            "WHERE userfeaturesid = %s AND pagingid = %s "
            "AND caller = 1",
            (userid, paging_id),
        )

        paging_user_res: DictRow = cursor.fetchone()
        if not paging_user_res:
            raise LookupError(
                f"Unable to find paging caller entry (userfeaturesid: {userid})"
            )

        paging_user_columns: tuple[str, ...] = (
            'endpoint_sip_uuid',
            'endpoint_sccp_id',
            'endpoint_custom_id',
            'name',
        )

        query = SQL(
            "SELECT {columns} FROM paginguser "
            "JOIN user_line ON paginguser.userfeaturesid = user_line.user_id "
            "JOIN linefeatures ON user_line.line_id = linefeatures.id "
            "WHERE paginguser.pagingid = %s "
            "AND paginguser.caller = 0"
        )
        cursor.execute(
            query.format(columns=join_column_names(paging_user_columns)), (paging_id,)
        )
        line_res: list[DictRow] = cursor.fetchall()
        if not line_res:
            raise LookupError(f"Unable to find paging users entry (id: {paging_id})")

        for line in line_res:
            if line['endpoint_sip_uuid']:
                line = f'PJSIP/{line["name"]}'
            elif line['endpoint_sccp_id']:
                line = f'SCCP/{line["name"]}/autoanswer'
            elif line['endpoint_custom_id']:
                line = f'CUSTOM/{line["name"]}'
            else:
                raise LookupError(f"Unable to find protocol for user (id: {paging_id})")

            self.lines.add(line)


class User:
    def __init__(
        self, agi, cursor: DictCursor, xid=None, exten=None, context=None, agent_id=None
    ):
        self.agi = agi
        self.cursor = cursor

        if xid:
            user_row = user_dao.get(xid)
        elif exten and context:
            user_row = user_dao.get_user_by_number_context(exten, context)
        elif agent_id:
            user_row = user_dao.get_user_by_agent_id(agent_id)
        else:
            raise LookupError(
                '"id", "exten@context" or "agent_id" must be provided to look up an user entry'
            )

        self.id = user_row.id
        self.uuid = user_row.uuid
        self.tenant_uuid = user_row.tenant_uuid
        self.firstname = user_row.firstname
        self.lastname = user_row.lastname
        self.language = user_row.language
        self.userfield = user_row.userfield
        self.callerid = user_row.callerid
        self.mobilephonenumber = user_row.mobilephonenumber
        self.musiconhold = user_row.musiconhold
        self.outcallerid = user_row.outcallerid
        self.ringseconds = int(user_row.ringseconds)
        self.simultcalls = user_row.simultcalls
        self.enablevoicemail = user_row.enablevoicemail
        self.voicemailid = user_row.voicemailid
        self.enablexfer = user_row.enablexfer
        self.dtmf_hangup = user_row.dtmf_hangup
        self.enableonlinerec = user_row.enableonlinerec
        self.incallfilter = user_row.incallfilter
        self.enablednd = user_row.enablednd
        self.enableunc = user_row.enableunc
        self.destunc = user_row.destunc
        self.enablerna = user_row.enablerna
        self.destrna = user_row.destrna
        self.enablebusy = user_row.enablebusy
        self.destbusy = user_row.destbusy
        self.preprocess_subroutine = user_row.preprocess_subroutine
        self.bsfilter = user_row.bsfilter
        self.rightcallcode = user_row.rightcallcode
        self.call_record_outgoing_external_enabled = (
            user_row.call_record_outgoing_external_enabled
        )
        self.call_record_outgoing_internal_enabled = (
            user_row.call_record_outgoing_internal_enabled
        )
        self.call_record_incoming_external_enabled = (
            user_row.call_record_incoming_external_enabled
        )
        self.call_record_incoming_internal_enabled = (
            user_row.call_record_incoming_internal_enabled
        )
        self.call_record_enabled = all(
            (
                self.call_record_outgoing_external_enabled,
                self.call_record_outgoing_internal_enabled,
                self.call_record_incoming_external_enabled,
                self.call_record_incoming_internal_enabled,
            )
        )

        if self.destunc == '':
            self.enableunc = 0

        if self.destrna == '':
            self.enablerna = 0

        if self.destbusy == '':
            self.enablebusy = 0

        self.vmbox = None
        if self.enablevoicemail and self.voicemailid:
            try:
                self.vmbox = VMBox(agi, cursor, self.voicemailid)
            except LookupError:
                self.vmbox = None

        if not self.vmbox:
            self.enablevoicemail = 0

    def toggle_feature(self, feature):
        if feature == 'enablevoicemail':
            enabled = int(not self.enablevoicemail)
            self.cursor.execute(
                "UPDATE userfeatures SET enablevoicemail = %s WHERE id = %s",
                (enabled, self.id),
            )
            self.enablevoicemail = enabled
        elif feature == 'callrecord':
            enabled = not self.call_record_enabled
            self.cursor.execute(
                "UPDATE userfeatures SET "
                "call_record_outgoing_external_enabled = %s, "
                "call_record_outgoing_internal_enabled = %s, "
                "call_record_incoming_external_enabled = %s, "
                "call_record_incoming_internal_enabled = %s "
                "WHERE id = %s",
                (enabled, enabled, enabled, enabled, self.id),
            )
            self.call_record_enabled = enabled
        else:
            raise ValueError("invalid feature")

        if self.cursor.rowcount != 1:
            raise DBUpdateException("Unable to perform the requested update")


class Queue:
    def __init__(self, agi: FastAGI, cursor: DictCursor, queue_id: int):
        self.agi = agi
        self.cursor = cursor

        queuefeatures_columns = [
            'id',
            'tenant_uuid',
            'number',
            'context',
            'name',
            'data_quality',
            'dtmf_record_toggle',
            'hitting_callee',
            'hitting_caller',
            'retries',
            'ring',
            'transfer_user',
            'transfer_call',
            'write_caller',
            'write_calling',
            'ignore_forward',
            'url',
            'announceoverride',
            'timeout',
            'preprocess_subroutine',
            'announce_holdtime',
            'waittime',
            'waitratio',
            'mark_answered_elsewhere',
        ]
        queuefeatures_columns = ["queuefeatures." + c for c in queuefeatures_columns]
        queue_columns = ['queue.wrapuptime', 'queue.musicclass']

        columns = queuefeatures_columns + queue_columns

        if not queue_id:
            raise LookupError("id must be provided to look up a queue")

        query = SQL(
            "SELECT {columns} FROM queuefeatures "
            "INNER JOIN queue "
            "ON queuefeatures.name = queue.name "
            "WHERE queuefeatures.id = %s "
            "AND queue.commented = 0 "
            "AND queue.category = 'queue'"
        )
        cursor.execute(
            query.format(columns=join_column_names(columns)),
            (queue_id,),
        )
        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find queue (id: {queue_id})")

        self.id = res['id']
        self.tenant_uuid = res['tenant_uuid']
        self.number = res['number']
        self.context = res['context']
        self.name = res['name']
        self.data_quality = res['data_quality']
        self.dtmf_record_toggle = res['dtmf_record_toggle']
        self.hitting_callee = res['hitting_callee']
        self.hitting_caller = res['hitting_caller']
        self.retries = res['retries']
        self.ring = res['ring']
        self.transfer_user = res['transfer_user']
        self.transfer_call = res['transfer_call']
        self.write_caller = res['write_caller']
        self.write_calling = res['write_calling']
        self.ignore_forward = res['ignore_forward']
        self.url = res['url']
        self.announceoverride = res['announceoverride']
        self.timeout = res['timeout']
        self.preprocess_subroutine = res['preprocess_subroutine']
        self.announce_holdtime = res['announce_holdtime']
        self.waittime = res['waittime']
        self.waitratio = res['waitratio']
        self.wrapuptime = res['wrapuptime']
        self.musiconhold = res['musicclass']
        self.mark_answered_elsewhere = res['mark_answered_elsewhere']

    def set_dial_actions(self):
        for event in ['congestion', 'busy', 'chanunavail', 'qwaittime', 'qwaitratio']:
            DialAction(self.agi, self.cursor, event, "queue", self.id).set_variables()

        # case NOANSWER (timeout): we also set correct queuelog event
        action = DialAction(self.agi, self.cursor, 'noanswer', "queue", self.id)
        action.set_variables()
        if action.action in ['voicemail', 'sound']:
            self.agi.set_variable(dv.QUEUELOG_EVENT, "REROUTEGUIDE")

    def rewrite_cid(self):
        CallerID(self.agi, self.cursor, "queue", self.id).rewrite(force_rewrite=False)

    def pickupgroups(self):
        self.cursor.execute(
            "SELECT p.id FROM pickup p, pickupmember pm "
            "WHERE p.commented = 0 AND p.id = pm.pickupid "
            "AND pm.category = 'member' AND pm.membertype = 'queue'"
            "AND pm.memberid = %s",
            (self.id,),
        )

        res: list[DictRow] = self.cursor.fetchall()
        if res is None:
            raise LookupError(f"Unable to fetch queue {self.id} pickupgroups")

        return [str(row[0]) for row in res]


class Agent:
    _columns = (
        'id',
        'tenant_uuid',
        'number',
        'passwd',
        'firstname',
        'lastname',
        'language',
        'preprocess_subroutine',
    )

    def __init__(
        self,
        id: int,
        tenant_uuid: str,
        number: str,
        passwd: str | None,
        firstname: str | None,
        lastname: str | None,
        language: str | None,
        preprocess_subroutine: str | None,
    ) -> None:
        self.id = id
        self.tenant_uuid = tenant_uuid
        self.number = number
        self.passwd = passwd
        self.firstname = firstname
        self.lastname = lastname
        self.language = language
        self.preprocess_subroutine = preprocess_subroutine

    @classmethod
    def from_id(cls, cursor: DictCursor, agent_id: str, tenant_uuid: str) -> Agent:
        query = SQL(
            "SELECT {columns} FROM agentfeatures WHERE id = %s AND tenant_uuid = %s"
        ).format(columns=join_column_names(cls._columns))
        return cls._from_query(cursor, query, agent_id, tenant_uuid)

    @classmethod
    def from_id_any_tenant(cls, cursor: DictCursor, agent_id: str) -> Agent:
        query = SQL("SELECT {columns} FROM agentfeatures WHERE id = %s").format(
            columns=join_column_names(cls._columns)
        )
        return cls._from_query(cursor, query, agent_id)

    @classmethod
    def from_number(cls, cursor: DictCursor, number: str, tenant_uuid: str) -> Agent:
        query = SQL(
            "SELECT {columns} FROM agentfeatures WHERE number = %s AND tenant_uuid = %s"
        ).format(
            columns=join_column_names(cls._columns),
        )
        return cls._from_query(cursor, query, number, tenant_uuid)

    @classmethod
    def _from_query(cls, cursor: DictCursor, query: SQL, *args: str) -> Agent:
        cursor.execute(query, args)
        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find agent {args}")

        return cls(**res)


class DialAction:
    @staticmethod
    def set_agi_variables(
        agi, event, category, action, actionarg1, actionarg2, isda=True
    ):
        xtype = f"{category}_{event}".upper()
        agi.set_variable(f"WAZO_FWD_{xtype}_ACTION", action)

        # Sometimes, it's useful to know whether these variables were
        # set manually, or by this object.
        if isda:
            agi.set_variable(f"WAZO_FWD_{xtype}_ISDA", "1")

        action_arg_1 = actionarg1.replace('|', ';') if actionarg1 else ""
        action_arg_2 = actionarg2 or ""

        agi.set_variable(f"WAZO_FWD_{xtype}_ACTIONARG1", action_arg_1)
        agi.set_variable(f"WAZO_FWD_{xtype}_ACTIONARG2", action_arg_2)

    def __init__(self, agi, cursor: DictCursor, event, category, categoryval):
        self.agi = agi
        self.cursor = cursor
        self.event = event
        self.category = category

        cursor.execute(
            "SELECT action, actionarg1, actionarg2 FROM dialaction "
            "WHERE event = %s "
            "AND category = %s "
            "AND categoryval::INTEGER = %s ",
            (event, category, categoryval),
        )
        res: DictRow = cursor.fetchone()
        if not res:
            self.action = "none"
            self.actionarg1 = None
            self.actionarg2 = None
        else:
            self.action = res['action']
            self.actionarg1 = res['actionarg1']
            self.actionarg2 = res['actionarg2']

    def set_variables(self):
        category_no_isda = (
            'none',
            'endcall:busy',
            'endcall:congestion',
            'endcall:hangup',
        )

        DialAction.set_agi_variables(
            self.agi,
            self.event,
            self.category,
            self.action,
            self.actionarg1,
            self.actionarg2,
            (self.category not in category_no_isda),
        )


class Tenant:
    def __init__(self, agi: FastAGI, cursor: DictCursor, tenant_uuid: str):
        self.agi = agi
        self.cursor = cursor
        self.tenant_uuid = tenant_uuid
        self.country = ''

        columns = [
            'country',
        ]
        query = SQL('SELECT {columns} FROM tenant WHERE uuid = %s')
        cursor.execute(
            query.format(columns=join_column_names(columns)),
            (tenant_uuid,),
        )
        res = cursor.fetchone()
        if not res:
            raise LookupError(f'Unable to find tenant (uuid: {tenant_uuid})')

        self.country = res['country']


class Trunk:
    def __init__(self, agi, cursor: DictCursor, xid):
        self.agi = agi
        self.cursor = cursor
        columns = [
            'endpoint_sip_uuid',
            'endpoint_iax_id',
            'endpoint_custom_id',
            'outgoing_caller_id_format',
        ]
        query = SQL(
            "SELECT {columns} FROM trunkfeatures WHERE id = %s",
        )
        cursor.execute(
            query.format(columns=join_column_names(columns)),
            (xid,),
        )
        res: DictRow = cursor.fetchone()
        self.agi.verbose(f'res {res}')

        if not res:
            raise LookupError(f"Unable to find trunk (id: {xid:d})")

        self.id = xid
        self.outgoing_caller_id_format = res['outgoing_caller_id_format']
        if res['endpoint_sip_uuid']:
            (self.interface, self.intfsuffix) = ChanSIP.get_intf_and_suffix(
                cursor, res['endpoint_sip_uuid']
            )
        elif res['endpoint_iax_id']:
            (self.interface, self.intfsuffix) = ChanIAX2.get_intf_and_suffix(
                cursor, res['endpoint_iax_id']
            )
        elif res['endpoint_custom_id']:
            (self.interface, self.intfsuffix) = ChanCustom.get_intf_and_suffix(
                cursor, res['endpoint_custom_id']
            )
        else:
            raise ValueError(f"Unknown protocol for trunk {xid}")


class DID:
    def __init__(self, agi, cursor: DictCursor, incall_id):
        self.agi = agi
        self.cursor = cursor

        if not incall_id:
            raise LookupError("id must be provided to look up a DID entry")

        columns = (
            'incall.id',
            'incall.preprocess_subroutine',
            'incall.greeting_sound',
            'extensions.exten',
            'extensions.context',
        )

        query = SQL(
            "SELECT {columns} FROM incall "
            "JOIN extensions ON extensions.type = 'incall' "
            "AND extensions.typeval = CAST(incall.id AS VARCHAR(255)) "
            "WHERE incall.id = %s "
            "AND incall.commented = 0 AND extensions.commented = 0"
        )
        cursor.execute(
            query.format(columns=join_column_names(columns)),
            (incall_id,),
        )
        res: DictRow = cursor.fetchone()

        if not res:
            raise LookupError(f"Unable to find DID entry (id: {incall_id})")

        self.id = res['id']
        self.exten = res['exten']
        self.context = res['context']
        self.preprocess_subroutine = res['preprocess_subroutine']
        self.greeting_sound = res['greeting_sound']

    def set_dial_actions(self):
        DialAction(self.agi, self.cursor, "answer", "incall", self.id).set_variables()

    def rewrite_cid(self):
        CallerID(self.agi, self.cursor, "incall", self.id).rewrite(force_rewrite=True)


class Outcall:
    trunks: list[Trunk]

    def __init__(self, agi, cursor: DictCursor):
        self.agi = agi
        self.cursor = cursor

    def retrieve_values(self, dialpattern_id):
        columns = (
            'outcall.name',
            'outcall.context',
            'outcall.internal',
            'outcall.preprocess_subroutine',
            'outcall.hangupringtime',
            'outcall.commented',
            'outcall.id',
            'dialpattern.typeid',
            'dialpattern.type',
            'dialpattern.exten',
            'dialpattern.stripnum',
            'dialpattern.externprefix',
            'dialpattern.callerid',
            'dialpattern.prefix',
        )

        if not dialpattern_id:
            raise LookupError(
                "id or exten@context must be provided to look up an outcall entry"
            )

        query = SQL(
            "SELECT {columns} FROM outcall, dialpattern "
            "WHERE dialpattern.typeid = outcall.id "
            "AND dialpattern.type = 'outcall' "
            "AND dialpattern.id = %s"
            "AND outcall.commented = 0"
        )
        self.cursor.execute(
            query.format(columns=join_column_names(columns)), (dialpattern_id,)
        )

        res: DictRow = self.cursor.fetchone()
        if not res:
            raise LookupError(
                f"Unable to find outcall entry (outgoing extension id: {dialpattern_id})"
            )

        self.id = res['id']
        self.exten = res['exten']
        self.context = res['context']
        self.externprefix = res['externprefix']
        self.stripnum = res['stripnum']
        self.callerid = res['callerid']
        self.internal = res['internal']
        self.preprocess_subroutine = res['preprocess_subroutine']
        self.hangupringtime = res['hangupringtime']

        self.cursor.execute(
            "SELECT trunkfeaturesid FROM outcalltrunk "
            "WHERE outcallid = %s "
            "ORDER BY priority ASC",
            (self.id,),
        )
        trunk_res: list[DictRow] = self.cursor.fetchall()

        if not trunk_res:
            raise ValueError(
                f"No trunk associated with outcall (outgoing extension id: {dialpattern_id})"
            )

        self.trunks = []
        for row in trunk_res:
            try:
                trunk = Trunk(self.agi, self.cursor, row['trunkfeaturesid'])
            except LookupError:
                continue

            self.trunks.append(trunk)


class ScheduleDataMapper:
    @classmethod
    def get_from_path(cls, cursor: DictCursor, path, path_id):
        # fetch schedule info
        columns = (
            'id',
            'timezone',
            'fallback_action',
            'fallback_actionid',
            'fallback_actionargs',
        )
        query = SQL(
            "SELECT {columns} FROM schedule_path p "
            "LEFT JOIN schedule s ON p.schedule_id = s.id "
            "WHERE p.path = %s "
            "AND p.pathid = %s "
            "AND s.commented = 0"
        )
        cursor.execute(
            query.format(columns=join_column_names(columns)), (path, path_id)
        )

        res: DictRow = cursor.fetchone()
        if not res:
            return AlwaysOpenedSchedule()

        schedule_id = res['id']
        timezone = res['timezone']
        if not timezone:
            cursor.execute("SELECT timezone FROM infos")
            infos = cursor.fetchone()
            timezone = infos['timezone']

        default_action = ScheduleAction(
            res['fallback_action'], res['fallback_actionid'], res['fallback_actionargs']
        )

        # fetch schedule periods
        schedule_columns: tuple[str, ...] = (
            'mode',
            'hours',
            'weekdays',
            'monthdays',
            'months',
            'action',
            'actionid',
            'actionargs',
        )
        query = SQL("SELECT {columns} FROM schedule_time WHERE schedule_id = %s")
        cursor.execute(
            query.format(columns=join_column_names(schedule_columns)), (schedule_id,)
        )
        schedule_res: list[DictRow] = cursor.fetchall()

        opened_periods = []
        closed_periods = []
        for res_period in schedule_res:
            period_builder = SchedulePeriodBuilder()
            period_builder.hours(res_period['hours'])
            period_builder.weekdays(res_period['weekdays'])
            period_builder.days(res_period['monthdays'])
            period_builder.months(res_period['months'])

            if res_period['mode'] == 'opened':
                opened_periods.append(period_builder.build())
            else:
                action = ScheduleAction(
                    res_period['action'],
                    res_period['actionid'],
                    res_period['actionargs'],
                )
                period_builder.action(action)
                closed_periods.append(period_builder.build())

        return Schedule(opened_periods, closed_periods, default_action, timezone)


class Context:
    # TODO: Recursive inclusion
    def __init__(self, agi, cursor: DictCursor, context):
        self.agi = agi
        self.cursor = cursor

        columns = ('context.name', 'context.displayname', 'contextinclude.include')
        query = SQL(
            "SELECT {columns} FROM context "
            "LEFT JOIN contextinclude "
            "ON context.name = contextinclude.context "
            "LEFT JOIN context AS contextinc "
            "ON contextinclude.include = contextinc.name "
            "AND context.commented = contextinc.commented "
            "WHERE context.name = %s "
            "AND context.commented = 0 "
            "AND (contextinclude.include IS NULL OR contextinc.name IS NOT NULL) "
            "ORDER BY contextinclude.priority ASC",
        )
        cursor.execute(query.format(columns=join_column_names(columns)), (context,))

        res: list[DictRow] = cursor.fetchall()
        if not res:
            raise LookupError(f"Unable to find context entry (name: {context})")

        self.name = res[0]['name']
        self.displayname = res[0]['displayname']
        self.include = [self.name]

        for row in res:
            if row['include']:
                self.include.append(row['include'])


CALLERID_MATCHER = re.compile(
    r'^(?:"(.+)"|([a-zA-Z0-9\-\.\!%\*_\+`\'\~]+)) ?(?:<(\+?[0-9\*#]+)>)?$'
).match
CALLERIDNUM_MATCHER = re.compile(r'^\+?[0-9\*#]+$').match


class CallerID:
    @staticmethod
    def parse(callerid):
        logger.debug('caller_id parse: parsing "%s"', callerid)
        m = CALLERID_MATCHER(callerid)

        if not m:
            logger.debug('caller_id parse: could not match callerid, giving up')
            return

        calleridname = m.group(1)
        calleridnum = m.group(3)
        logger.debug(
            'caller_id parse: calleridname: "%s", calleridnum: "%s"',
            calleridname,
            calleridnum,
        )

        if calleridname is None:
            calleridname = m.group(2)
            logger.debug(
                'caller_id parse: using fallback calleridname: '
                'calleridname: "%s", calleridnum: "%s"',
                calleridname,
                calleridnum,
            )

            if calleridnum is None and CALLERIDNUM_MATCHER(calleridname):
                calleridnum = m.group(2)
                logger.debug(
                    'caller_id parse: using fallback calleridnum: '
                    'calleridname: "%s", calleridnum: "%s"',
                    calleridname,
                    calleridnum,
                )

        return calleridname, calleridnum

    @staticmethod
    def set(agi, callerid):
        logger.debug('caller_id set: parsing "%s"', callerid)
        cid_parsed = CallerID.parse(callerid)

        if not cid_parsed:
            logger.debug('caller_id set: parsing result: "%s", giving up', cid_parsed)
            return

        calleridname, calleridnum = cid_parsed
        logger.debug(
            'caller_id set: calleridname: "%s", calleridnum: "%s"',
            calleridname,
            calleridnum,
        )

        if calleridname is None and calleridnum is not None:
            calleridname = calleridnum
            logger.debug(
                'caller_id set: using calleridnum as calleridname: '
                f'calleridname: "{calleridname}", calleridnum: "{calleridnum}"',
            )

        if calleridname is not None and calleridnum is None:
            logger.debug(
                'caller_id set: applying calleridname only: calleridname: "%s"',
                calleridname,
            )
            agi.set_variable('CALLERID(name)', calleridname)
        else:
            logger.debug(
                'caller_id set: applying callerid name and num: '
                f'calleridname: "{calleridname}", calleridnum: "{calleridnum}"',
            )
            agi.set_variable('CALLERID(all)', f'"{calleridname}" <{calleridnum}>')

        return True

    def __init__(self, agi, cursor: DictCursor, xtype, typeval):
        self.agi = agi
        self.cursor = cursor
        self.type = xtype
        self.typeval = typeval

        cursor.execute(
            "SELECT mode, callerdisplay FROM callerid "
            "WHERE type = %s "
            "AND typeval = %s "
            "AND mode IS NOT NULL",
            (xtype, typeval),
        )
        res: DictRow = cursor.fetchone()

        self.mode = None
        self.calleridname = None
        self.calleridnum = None

        if res:
            cid_parsed = self.parse(res['callerdisplay'])

            if cid_parsed:
                self.mode = res['mode']
                self.calleridname, self.calleridnum = cid_parsed

    def rewrite(self, force_rewrite):
        """
        Set/Modify the caller ID if needed and allowed and create
        the WAZO_CID_REWRITTEN channel variable in some cases.

        @force_rewrite:
            True <=> CID modification is always allowed in this case.
                WAZO_CID_REWRITTEN is neither taken into account nor
                written.
            False <=> CID modification is only allowed if the channel
                variable WAZO_CID_REWRITTEN is not set prior to the
                call to this method.  If the CID modification really
                took place, WAZO_CID_REWRITTEN is created.
        """
        if not self.mode:
            return

        cidrewritten = self.agi.get_variable(dv.CID_REWRITTEN)

        if force_rewrite or not cidrewritten:
            calleridname = self.agi.get_variable('CALLERID(name)')
            calleridnum = self.agi.get_variable('CALLERID(num)')

            if self.calleridnum is not None:
                calleridnum = self.calleridnum
            elif calleridnum in (None, ''):
                calleridnum = 'unknown'

            if calleridname in (None, '', '""'):
                calleridname = calleridnum
            elif calleridname[0] == '"' and calleridname[-1] == '"':
                calleridname = calleridname[1:-1]

            if (
                self.mode in ('prepend', 'append')
                and self.calleridname == calleridname
                and calleridnum == calleridname
            ):
                name = calleridname
            elif self.mode == 'prepend':
                name = f"{self.calleridname} - {calleridname}"
            elif self.mode == 'overwrite':
                name = self.calleridname
            elif self.mode == 'append':
                name = f"{calleridname} - {self.calleridname}"
            else:
                raise RuntimeError(f"Unknown callerid mode: {self.mode!r}")

            self.agi.set_variable('CALLERID(name-pres)', 'allowed')
            self.agi.set_variable('CALLERID(num-pres)', 'allowed')
            self.agi.set_variable('CALLERID(all)', f'"{name}" <{calleridnum}>')

            if not force_rewrite:
                self.agi.set_variable(dv.CID_REWRITTEN, 1)


class ChanSIP:
    @staticmethod
    def get_intf_and_suffix(cursor: DictCursor, xid):
        cursor.execute(
            "SELECT name FROM endpoint_sip WHERE uuid = %s",
            (xid,),
        )
        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find endpoint_sip entry (uuid: {xid})")
        return f'PJSIP/{res["name"]}', None


class ChanIAX2:
    @staticmethod
    def get_intf_and_suffix(cursor: DictCursor, xid):
        cursor.execute(
            "SELECT name FROM useriax WHERE id = %s AND commented = 0",
            (xid,),
        )
        res: DictRow = cursor.fetchone()

        if not res:
            raise LookupError(f'Unable to find useriax entry (id: {xid})')

        return f'IAX2/{res["name"]}', None


class ChanCustom:
    @staticmethod
    def get_intf_and_suffix(cursor: DictCursor, xid):
        cursor.execute(
            "SELECT interface, intfsuffix FROM usercustom WHERE id = %s AND commented = 0",
            (xid,),
        )

        res: DictRow = cursor.fetchone()
        if not res:
            raise LookupError(f"Unable to find usercustom entry (id: {xid})")

        # In case the suffix is the integer 0, bool(intfsuffix)
        # returns False though there is a suffix. Casting it to
        # a string prevents such an error.
        return res['interface'], str(res['intfsuffix'])
