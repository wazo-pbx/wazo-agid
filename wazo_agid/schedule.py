# Copyright 2010-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime
import re

import pytz

from wazo_agid import dialplan_variables as dv


class Schedule:
    def __init__(self, opened_periods, closed_periods, default_action, timezone_name):
        self._opened_periods = opened_periods
        self._closed_periods = closed_periods
        self._default_action = default_action
        self._timezone_name = timezone_name

    def compute_state(self, current_datetime):
        for closed_period in self._closed_periods:
            if closed_period.is_in(current_datetime):
                return ScheduleState.new_closed_state(closed_period.action)
        for open_period in self._opened_periods:
            if open_period.is_in(current_datetime):
                return ScheduleState.new_opened_state()
        return ScheduleState.new_closed_state(self._default_action)

    def compute_state_for_now(self):
        current_datetime = self._get_current_localized_time()
        return self.compute_state(current_datetime)

    def _get_current_localized_time(self):
        timezone = pytz.timezone(self._timezone_name)
        utc_now = pytz.utc.localize(datetime.datetime.utcnow())
        return utc_now.astimezone(timezone)


class AlwaysOpenedSchedule:
    def compute_state(self, current_datetime):
        return ScheduleState.new_opened_state()

    def compute_state_for_now(self):
        return ScheduleState.new_opened_state()


class ScheduleState:
    def __init__(self, state, action):
        self.state = state
        self.action = action

    @classmethod
    def new_opened_state(cls):
        return cls('opened', None)

    @classmethod
    def new_closed_state(cls, action):
        return cls('closed', action)


class ScheduleAction:
    def __init__(self, action, actionarg1, actionarg2):
        self.action = action
        self.actionarg1 = actionarg1
        self.actionarg2 = actionarg2

    def set_variables_in_agi(self, agi):
        agi.set_variable(dv.FWD_SCHEDULE_OUT_ACTION, self.action)
        agi.set_variable(dv.FWD_SCHEDULE_OUT_ACTIONARG1, self.actionarg1)
        if self.actionarg2 is not None:
            agi.set_variable(dv.FWD_SCHEDULE_OUT_ACTIONARG2, self.actionarg2)


class ScheduleBuilder:
    def __init__(self):
        self._opened_periods = []
        self._closed_periods = []
        self._default_action = None
        self._timezone_name = None

    def opened(self, opened_period):
        self._opened_periods.append(opened_period)
        return self

    def closed(self, closed_period):
        self._closed_periods.append(closed_period)
        return self

    def default_action(self, action):
        self._default_action = action
        return self

    def timezone_name(self, timezone_name):
        self._timezone_name = timezone_name
        return self

    def build(self):
        return Schedule(
            self._opened_periods,
            self._closed_periods,
            self._default_action,
            self._timezone_name,
        )


class SchedulePeriod:
    def __init__(self, checkers, action):
        self._checkers = list(checkers)
        self.action = action

    def is_in(self, tested_datetime):
        for checker in self._checkers:
            if not checker.is_in(tested_datetime):
                return False
        return True


class SchedulePeriodBuilder:
    def __init__(self):
        self._hours = None
        self._weekdays = None
        self._days = None
        self._months = None
        self._action = None

    def hours(self, hours):
        self._hours = hours
        return self

    def weekdays(self, weekdays):
        self._weekdays = weekdays
        return self

    def days(self, days):
        self._days = days
        return self

    def months(self, months):
        self._months = months
        return self

    def action(self, action):
        self._action = action
        return self

    def build(self):
        checkers = []
        if self._hours:
            checkers.append(HoursChecker.new_from_value(self._hours))
        if self._weekdays:
            checkers.append(WeekdaysChecker.new_from_value(self._weekdays))
        if self._days:
            checkers.append(DaysChecker.new_from_value(self._days))
        if self._months:
            checkers.append(MonthsChecker.new_from_value(self._months))
        return SchedulePeriod(checkers, self._action)


class HoursChecker:
    def __init__(self, start_hour, start_minute, end_hour, end_minute):
        self._start_time = (start_hour, start_minute)
        self._end_time = (end_hour, end_minute)

    def is_in(self, tested_datetime):
        tested_time = (tested_datetime.hour, tested_datetime.minute)
        return self._start_time <= tested_time <= self._end_time

    _HOURS_VALUE_REGEX = re.compile(r'^(\d\d):([0-5]\d)-(\d\d):([0-5]\d)$')

    @classmethod
    def new_from_value(cls, value):
        m = cls._HOURS_VALUE_REGEX.match(value)
        if not m:
            raise ValueError(value)
        else:
            start_hour = int(m.group(1))
            if start_hour > 23:
                raise ValueError(f'start hour: {start_hour}')
            start_min = int(m.group(2))
            end_hour = int(m.group(3))
            if end_hour > 23:
                raise ValueError(f'end hour: {end_hour}')
            end_min = int(m.group(4))
            if (start_hour, start_min) > (end_hour, end_min):
                raise ValueError('end hour before start hour')
            return cls(start_hour, start_min, end_hour, end_min)


class _SimpleChecker:
    def __init__(self, accepted_values):
        self._accepted_values = accepted_values

    def is_in(self, tested_datetime):
        tested_value = self._extract_tested_value_from_datetime(tested_datetime)
        return tested_value in self._accepted_values

    def _extract_tested_value_from_datetime(self, tested_datetime):
        raise NotImplementedError()

    @classmethod
    def new_from_value(cls, value):
        accepted_values = set()
        tokens = value.split(',')
        for token in tokens:
            if '-' in token:
                low, high = token.split('-')
                accepted_values.update(list(range(int(low), int(high) + 1)))
            else:
                accepted_values.add(int(token))
        return cls(accepted_values)


class WeekdaysChecker(_SimpleChecker):
    def _extract_tested_value_from_datetime(self, tested_datetime):
        return tested_datetime.isoweekday()


class DaysChecker(_SimpleChecker):
    def _extract_tested_value_from_datetime(self, tested_datetime):
        return tested_datetime.day


class MonthsChecker(_SimpleChecker):
    def _extract_tested_value_from_datetime(self, tested_datetime):
        return tested_datetime.month
