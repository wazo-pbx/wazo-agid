# Copyright 2006-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import re

from wazo_agid import dialplan_variables as dv

logger = logging.getLogger(__name__)

RIGHTCALL_AUTHORIZATION_COLNAME = "rightcall.authorization"
RIGHTCALL_PASSWD_COLNAME = "rightcall.passwd"

rep = (
    ('_', r''),
    ('*', r'\*'),
    ('+', r'\+'),
    ('X', r'[0-9]'),
    ('Z', r'[1-9]'),
    ('N', r'[2-9]'),
    ('.', r'[0-9#\*]+'),
    ('!', r'[0-9#\*]*'),
)


class RuleAppliedException(Exception):
    pass


def allow(agi):
    agi.set_variable(dv.AUTHORIZATION, "ALLOW")
    raise RuleAppliedException()


def deny(agi, password):
    if password:
        agi.set_variable(dv.PASSWORD, password)

    agi.set_variable(dv.AUTHORIZATION, "DENY")
    raise RuleAppliedException()


def extension_matches(number, pattern):
    for key, val in rep:
        pattern = pattern.replace(key, val)
    return bool(re.match(rf"^{pattern}$", number))


def apply_rules(agi, rules):
    if not rules:
        return

    column_name = RIGHTCALL_AUTHORIZATION_COLNAME.split('.')[1]
    for rule in rules:
        if rule[column_name]:
            allow(agi)

    deny(agi, rule[RIGHTCALL_PASSWD_COLNAME.split('.')[1]])
