# Copyright 2006-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from psycopg2.extras import DictCursor, DictRow
from psycopg2.sql import SQL, Literal, Placeholder

from wazo_agid import agid, call_rights
from wazo_agid import dialplan_variables as dv
from wazo_agid import objects
from wazo_agid.objects import join_column_names

logger = logging.getLogger(__name__)


def _user_set_call_rights(
    agi: agid.FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    userid = agi.get_variable('WAZO_USERID')
    dstnum = agi.get_variable('WAZO_DSTNUM')
    outcallid = agi.get_variable(dv.OUTCALL_ID)

    cursor.execute("SELECT rightcallid, exten FROM rightcallexten")
    res = cursor.fetchall()

    if not res:
        call_rights.allow(agi)

    rightcallidset = {
        row['rightcallid']
        for row in res
        if call_rights.extension_matches(dstnum, row['exten'])
    }

    if not rightcallidset:
        call_rights.allow(agi)

    rightcall_ids = SQL(',').join(Literal(str(el)) for el in rightcallidset)
    try:
        user = objects.User(agi, cursor, int(userid))
    except (ValueError, LookupError):
        if not outcallid:
            call_rights.allow(agi)
    else:
        query = SQL(
            "SELECT {columns} FROM rightcall "
            "INNER JOIN rightcallmember "
            "ON rightcall.id = rightcallmember.rightcallid "
            "WHERE rightcall.id IN ({rightcall_ids}) "
            "AND rightcallmember.type = 'user' "
            "AND rightcallmember.typeval = '%s' "
            "AND rightcall.commented = 0"
        )
        columns = (
            call_rights.RIGHTCALL_AUTHORIZATION_COLNAME,
            call_rights.RIGHTCALL_PASSWD_COLNAME,
        )
        cursor.execute(
            query.format(
                columns=join_column_names(columns),
                rightcall_ids=rightcall_ids,
            ),
            (user.id,),
        )
        call_rights_res: list[DictCursor] = cursor.fetchall()

        if user.rightcallcode:
            for i, value in enumerate(call_rights_res):
                if value[1]:
                    call_rights_res[i][1] = user.rightcallcode

        call_rights.apply_rules(agi, call_rights_res)

        cursor.execute(
            "SELECT groupfeatures.id FROM groupfeatures "
            "INNER JOIN queuemember "
            "ON groupfeatures.name = queuemember.queue_name "
            "INNER JOIN queue "
            "ON queue.name = queuemember.queue_name "
            "WHERE queuemember.userid = %s "
            "AND queuemember.usertype = 'user' "
            "AND queuemember.category = 'group' "
            "AND queuemember.commented = 0 "
            "AND queue.category = 'group' "
            "AND queue.commented = 0",
            (user.id,),
        )
        group_feature_res: list[DictRow] = cursor.fetchall()

        if group_feature_res:
            groupids = [row['id'] for row in group_feature_res]
            columns = (
                call_rights.RIGHTCALL_AUTHORIZATION_COLNAME,
                call_rights.RIGHTCALL_PASSWD_COLNAME,
            )
            query = SQL(
                "SELECT {columns} FROM rightcall "
                "INNER JOIN rightcallmember "
                "ON rightcall.id = rightcallmember.rightcallid "
                "WHERE rightcall.id IN ({rightcall_ids}) "
                "AND rightcallmember.type = 'group' "
                "AND rightcallmember.typeval IN ({typeval_choices}) "
                "AND rightcall.commented = 0"
            )
            cursor.execute(
                query.format(
                    columns=join_column_names(columns),
                    typeval_choices=SQL(',').join(
                        Placeholder() * len(group_feature_res)
                    ),
                    rightcall_ids=rightcall_ids,
                ),
                [str(group_id) for group_id in groupids],
            )
            member_res = cursor.fetchall()
            call_rights.apply_rules(agi, member_res)

    if outcallid:
        columns = (
            call_rights.RIGHTCALL_AUTHORIZATION_COLNAME,
            call_rights.RIGHTCALL_PASSWD_COLNAME,
        )
        query = SQL(
            "SELECT {columns} FROM rightcall "
            "INNER JOIN rightcallmember "
            "ON rightcall.id = rightcallmember.rightcallid "
            "INNER JOIN outcall "
            "ON CAST(rightcallmember.typeval AS integer) = outcall.id "
            "WHERE rightcall.id IN ({rightcall_ids}) "
            "AND rightcallmember.type = 'outcall' "
            "AND outcall.id = %s "
            "AND rightcall.commented = 0",
        )
        cursor.execute(
            query.format(
                columns=join_column_names(columns), rightcall_ids=rightcall_ids
            ),
            (outcallid,),
        )
        call_rights_res = cursor.fetchall()
        call_rights.apply_rules(agi, call_rights_res)

    call_rights.allow(agi)


def user_set_call_rights(
    agi: agid.FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    try:
        _user_set_call_rights(agi, cursor, args)
    except call_rights.RuleAppliedException:
        return


agid.register(user_set_call_rights)
