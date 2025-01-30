# Copyright 2013-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime
import unittest
from unittest.mock import Mock, call

from wazo_agid import dialplan_variables as dv
from wazo_agid.schedule import (
    DaysChecker,
    HoursChecker,
    MonthsChecker,
    ScheduleAction,
    ScheduleBuilder,
    SchedulePeriod,
    SchedulePeriodBuilder,
    WeekdaysChecker,
)


class TestHoursChecker(unittest.TestCase):
    def test_range_is_in(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('08:07').build()

        self._assert_time_is_in(current_time, value)

    def _assert_time_is_in(self, current_time, value):
        hours_checker = HoursChecker.new_from_value(value)
        self.assertTrue(hours_checker.is_in(current_time))

    def _assert_time_is_not_in(self, current_time, value):
        hours_checker = HoursChecker.new_from_value(value)
        self.assertFalse(hours_checker.is_in(current_time))

    def test_upper_limit_is_in(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('08:10').build()

        self._assert_time_is_in(current_time, value)

    def test_lower_limit_is_in(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('08:05').build()

        self._assert_time_is_in(current_time, value)

    def test_upper_limit_plus_one_is_not_in(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('08:11').build()

        self._assert_time_is_not_in(current_time, value)

    def test_upper_limit_less_one_is_not_in(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('08:04').build()

        self._assert_time_is_not_in(current_time, value)

    def test_minute_is_in_but_hour_is_more(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('09:07').build()

        self._assert_time_is_not_in(current_time, value)

    def test_minute_is_in_but_hour_is_less(self):
        value = '08:05-08:10'
        current_time = _a_time().hour('07:07').build()

        self._assert_time_is_not_in(current_time, value)


class TestWeekdaysChecker(unittest.TestCase):
    def test_single_weekday_is_in(self):
        value = '3'
        current_time = _a_time().weekday('3').build()

        self._assert_time_is_in(current_time, value)

    def _assert_time_is_in(self, current_time, value):
        weekdays_checker = WeekdaysChecker.new_from_value(value)
        self.assertTrue(weekdays_checker.is_in(current_time))

    def _assert_time_is_not_in(self, current_time, value):
        weekdays_checker = WeekdaysChecker.new_from_value(value)
        self.assertFalse(weekdays_checker.is_in(current_time))

    def test_single_weekday_range_is_in(self):
        value = '1-5'
        current_time = _a_time().weekday('3').build()

        self._assert_time_is_in(current_time, value)

    def test_upper_limit_single_weekday_range(self):
        value = '1-5'
        current_time = _a_time().weekday('5').build()

        self._assert_time_is_in(current_time, value)

    def test_lower_limit_single_weekday_range(self):
        value = '1-5'
        current_time = _a_time().weekday('1').build()

        self._assert_time_is_in(current_time, value)

    def test_upper_limit_plus_one_is_not_in(self):
        value = '1-5'
        current_time = _a_time().weekday('6').build()

        self._assert_time_is_not_in(current_time, value)

    def test_lower_limit_less_one_is_not_in(self):
        value = '2-5'
        current_time = _a_time().weekday('1').build()

        self._assert_time_is_not_in(current_time, value)

    def test_mixed_weekday_range_is_in(self):
        value = '1,3-4,7'

        weekdays_checker = WeekdaysChecker.new_from_value(value)
        self.assertTrue(weekdays_checker.is_in(_a_time().weekday('1').build()))
        self.assertFalse(weekdays_checker.is_in(_a_time().weekday('2').build()))
        self.assertTrue(weekdays_checker.is_in(_a_time().weekday('3').build()))
        self.assertTrue(weekdays_checker.is_in(_a_time().weekday('4').build()))
        self.assertFalse(weekdays_checker.is_in(_a_time().weekday('5').build()))
        self.assertFalse(weekdays_checker.is_in(_a_time().weekday('6').build()))
        self.assertTrue(weekdays_checker.is_in(_a_time().weekday('7').build()))


class TestDaysChecker(unittest.TestCase):
    def test_simple_day(self):
        value = '5'

        days_checker = DaysChecker.new_from_value(value)

        self.assertTrue(days_checker.is_in(_a_time().day('5').build()))
        self.assertFalse(days_checker.is_in(_a_time().day('6').build()))


class TestMonthsChecker(unittest.TestCase):
    def test_simple_month(self):
        value = '5'

        months_checker = MonthsChecker.new_from_value(value)

        self.assertTrue(months_checker.is_in(_a_time().month('5').build()))
        self.assertFalse(months_checker.is_in(_a_time().month('6').build()))


class TestSchedulePeriod(unittest.TestCase):
    def test_is_in_with_true_checker(self):
        checker = self._new_true_checker()

        schedule_period = SchedulePeriod([checker], None)

        self.assertTrue(schedule_period.is_in(None))

    def _new_true_checker(self):
        mock = Mock()
        mock.is_in.return_value = True
        return mock

    def test_is_in_with_false_checker(self):
        checker = self._new_false_checker()

        schedule_period = SchedulePeriod([checker], None)

        self.assertFalse(schedule_period.is_in(None))

    def _new_false_checker(self):
        mock = Mock()
        mock.is_in.return_value = False
        return mock

    def test_is_in_with_true_and_false_checker(self):
        checker1 = self._new_true_checker()
        checker2 = self._new_false_checker()

        schedule_period = SchedulePeriod([checker1, checker2], None)

        self.assertFalse(schedule_period.is_in(None))


class TestSchedule(unittest.TestCase):
    def test_schedule_is_opened_when_hours_is_in_open_period(self):
        schedule = (
            _a_schedule().opened(_a_period().hours('18:00-18:10').build()).build()
        )
        current_time = _a_time().hour('18:05').build()

        self._assert_schedule_is_in_state(schedule, current_time, 'opened')

    def _assert_schedule_is_in_state(self, schedule, current_time, state, action=None):
        schedule_state = schedule.compute_state(current_time)
        self.assertEqual(state, schedule_state.state)
        if action is not None:
            self.assertEqual(action, schedule_state.action)

    def test_simple_schedule_is_closed_when_hours_not_in_open_period(self):
        schedule = (
            _a_schedule().opened(_a_period().hours('18:00-18:10').build()).build()
        )
        current_time = _a_time().hour('18:15').build()

        self._assert_schedule_is_in_state(schedule, current_time, 'closed')

    def test_schedule_is_closed_when_day_doesnt_match(self):
        schedule = _a_schedule().opened(_a_period().days('22').build()).build()
        current_time = _a_time().day('23').build()

        self._assert_schedule_is_in_state(schedule, current_time, 'closed')

    def test_schedule_is_closed_when_weekday_doesnt_match(self):
        schedule = _a_schedule().opened(_a_period().weekdays('6').build()).build()
        current_time = _a_time().weekday('7').build()

        self._assert_schedule_is_in_state(schedule, current_time, 'closed')

    def test_schedule_is_closed_when_month_doesnt_match(self):
        schedule = _a_schedule().opened(_a_period().months('3').build()).build()
        current_time = _a_time().month('4').build()

        self._assert_schedule_is_in_state(schedule, current_time, 'closed')

    def test_complex_schedule(self):
        schedule = (
            _a_schedule()
            .opened(_a_period().hours('16:00-17:00').build())
            .closed(_a_period().hours('16:05-16:07').days('5').action(1).build())
            .closed(_a_period().hours('16:05-16:07').days('6').action(2).build())
            .build()
        )
        current_time_builder = _a_time().hour('16:06')

        current_time = current_time_builder.day('5').build()
        self._assert_schedule_is_in_state(schedule, current_time, 'closed', action=1)
        current_time = current_time_builder.day('6').build()
        self._assert_schedule_is_in_state(schedule, current_time, 'closed', action=2)
        current_time = current_time_builder.day('7').build()
        self._assert_schedule_is_in_state(schedule, current_time, 'opened')


def _a_schedule():
    return ScheduleBuilder()


def _a_period():
    return SchedulePeriodBuilder()


def _a_time():
    return _DatetimeBuilder()


class _DatetimeBuilder:
    def __init__(self):
        self._year = 1970
        self._month = 1
        self._day = 1
        self._hour = 0
        self._minute = 0

    def hour(self, hour):
        hour, minute = hour.split(':', 1)
        self._hour = int(hour)
        self._minute = int(minute)
        return self

    def month(self, month):
        self._month = int(month)
        return self

    def day(self, day):
        self._day = int(day)
        return self

    def weekday(self, weekday):
        # monday = 1, sunday = 7
        weekday = int(weekday)
        self._year = 1970
        self._month = 1
        self._day = 4 + weekday
        return self

    def build(self):
        return datetime.datetime(
            self._year, self._month, self._day, self._hour, self._minute
        )


class TestScheduleAction(unittest.TestCase):
    def test_action_arg2_is_not_set_if_none(self):
        action = ScheduleAction('foo', 'bar', None)
        agi = Mock()

        action.set_variables_in_agi(agi)

        expected_call_args = [
            call(dv.FWD_SCHEDULE_OUT_ACTION, 'foo'),
            call(dv.FWD_SCHEDULE_OUT_ACTIONARG1, 'bar'),
        ]
        self.assertEqual(expected_call_args, agi.set_variable.call_args_list)
