# -*- coding: utf-8 -*-
# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_agid import agid


def wake_mobile(agi, cursor, args):
    user_uuid = args[0]
    should_wake_mobile = agi.get_variable('WAZO_WAIT_FOR_MOBILE') or False
    if not should_wake_mobile:
        return

    video_enabled = agi.get_variable('WAZO_VIDEO_ENABLED')
    geolocation = agi.get_variable('PJSIP_HEADER(read,Geolocation)')

    agi.appexec(
        'UserEvent',
        'Pushmobile,WAZO_DST_UUID: {},WAZO_VIDEO_ENABLED: {},Geolocation: {}'.format(
            user_uuid, video_enabled, geolocation
        ),
    )


agid.register(wake_mobile)
