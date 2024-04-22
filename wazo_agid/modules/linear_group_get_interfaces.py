# Copyright 2018-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from xivo_dao.alchemy.groupfeatures import GroupFeatures
from xivo_dao.resources.group import dao as group_dao

from wazo_agid import agid

if TYPE_CHECKING:
    from psycopg2.extras import DictCursor

    from wazo_agid.agid import FastAGI


logger = logging.getLogger(__name__)


@dataclass
class UserMemberInfo:
    uuid: str
    type: Literal['user'] = 'user'


@dataclass
class ExtensionMemberInfo:
    extension: str
    context: str
    type: Literal['extension'] = 'extension'


@dataclass
class GroupInfo:
    members: list[UserMemberInfo | ExtensionMemberInfo]
    name: str
    ring_in_use: bool


def build_user_interface(user_uuid: str, user_interfaces):
    return f'Local/{user_uuid}@usersharedlines'


def build_extension_interface(extension: str, context: str):
    return f'Local/{extension}@{context}'


def get_group_info(group_id: int) -> GroupInfo:
    group: GroupFeatures = group_dao.get(group_id=group_id)

    user_member_info = [
        UserMemberInfo(
            uuid=user_member.user.uuid,
        )
        for user_member in group.user_queue_members
    ]

    extension_member_info = [
        ExtensionMemberInfo(
            extension=extension_member.extension.exten,
            context=extension_member.extension.context,
        )
        for extension_member in group.extension_queue_members
    ]

    group_info = GroupInfo(
        members=user_member_info + extension_member_info,
        name=group.name,
        ring_in_use=group.ring_in_use,
    )

    return group_info


def linear_group_get_interfaces(
    agi: FastAGI, cursor: DictCursor, args: list[str]
) -> None:
    group_id = int(args[0])
    group_info = get_group_info(group_id)
    for i, member in enumerate(group_info.members):
        if member.type == 'user':
            extension = f'{member.uuid}@usersharedlines'
            extension_state = agi.get_variable(f'EXTENSION_STATE({extension})')
            if not group_info.ring_in_use and extension_state in (
                'NOT_INUSE',
                'UNKNOWN',
            ):
                interface = f'Local/{extension}'
                agi.set_variable(
                    f'WAZO_GROUP_LINEAR_{i}_INTERFACE',
                    interface,
                )
        elif member.type == 'extension':
            extension = f'{member.extension}@{member.context}'
            extension_state = agi.get_variable(f'EXTENSION_STATE({extension})')
            if not group_info.ring_in_use and extension_state in (
                'NOT_INUSE',
                'UNKNOWN',
            ):
                interface = f'Local/{extension}'
                agi.set_variable(
                    f'WAZO_GROUP_LINEAR_{i}_INTERFACE',
                    interface,
                )
            else:
                logger.info(
                    'Extension %s@%s is not available(state %s), '
                    'excluding from linear group dial list',
                    member.extension,
                    member.context,
                    extension_state,
                )


agid.register(linear_group_get_interfaces)
