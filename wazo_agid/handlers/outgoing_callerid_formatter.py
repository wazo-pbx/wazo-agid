# Copyright 2024-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import re

import phonenumbers

from wazo_agid import dialplan_variables as dv
from wazo_agid import objects
from wazo_agid.handlers import handler

VALID_PHONE_NUMBER_RE = re.compile(r'^\+?\d{3,15}$')
CALLER_ID_ALL_REGEX = re.compile(r'^"(.*)" <(\+?\d{3,15})>$')


logger = logging.getLogger(__name__)


def _remove_none_numeric_char(raw: str) -> str:
    return ''.join(c for c in raw if c.isdigit())


class CallerIDFormatter(handler.Handler):
    def execute(self) -> None:
        self.set_caller_id()

    def set_caller_id(self) -> None:
        selected_cid = self._agi.get_variable(dv.SELECTED_CALLER_ID)
        cid_format = self._agi.get_variable(dv.TRUNK_CID_FORMAT)
        tenant_country = self._agi.get_variable('WAZO_TENANT_COUNTRY')

        if not selected_cid:
            return

        if not cid_format:
            return

        matches = CALLER_ID_ALL_REGEX.match(selected_cid)
        if matches:
            cid_name = matches.group(1)
            cid_number = matches.group(2)
        else:
            cid_name = ''
            cid_number = selected_cid

        try:
            parsed_cid_number = phonenumbers.parse(cid_number, tenant_country)
        except phonenumbers.phonenumberutil.NumberParseException:
            logger.info(
                'caller id number %s cannot be parsed '
                'as a valid number for tenant country %s',
                cid_number,
                tenant_country,
            )
            self._set_raw_number(cid_name, cid_number)
        else:
            self._set_formated_number(cid_name, parsed_cid_number, cid_format)

    def _set_raw_number(self, name: str, number: str) -> None:
        matches = VALID_PHONE_NUMBER_RE.match(number)
        if matches:
            self._set_caller_id(name, number)
        else:
            self._agi.verbose(
                f'Ignoring selected caller ID {number} not matching supported pattern'
            )

    def _set_formated_number(
        self, cid_name: str, number: phonenumbers.PhoneNumber, cid_format: str
    ) -> None:
        if cid_format == 'national':
            formated_number = _remove_none_numeric_char(
                phonenumbers.format_number(
                    number,
                    phonenumbers.PhoneNumberFormat.NATIONAL,
                )
            )
        elif cid_format == 'E164':
            formated_number = _remove_none_numeric_char(
                phonenumbers.format_number(
                    number,
                    phonenumbers.PhoneNumberFormat.E164,
                )
            )
        elif cid_format == '+E164':
            formated_number = phonenumbers.format_number(
                number,
                phonenumbers.PhoneNumberFormat.E164,
            )
        else:
            self._agi.verbose(f'Unknown supported {dv.TRUNK_CID_FORMAT} "{cid_format}"')

        self._set_caller_id(cid_name, formated_number)

    def _set_caller_id(self, name: str, number: str) -> None:
        if name:
            objects.CallerID.set(self._agi, f'"{name}" <{number}>')
        else:
            objects.CallerID.set(self._agi, number)
