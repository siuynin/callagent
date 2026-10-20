"""Business calendar maths (plan/docs/03 business_calendars, AC23, AC24).

Pure functions, no DB: weekly hours per ISO weekday (1 = Thứ Hai … 7 = Chủ nhật) plus dated exceptions.
All evaluation happens in the calendar's IANA timezone; callers pass and get back aware datetimes.
Holidays are not in IANA data and Tết follows the lunar calendar, so they are entered per year.

Precedence for a given date: any holiday/closed exception closes the whole day; otherwise the last
special_hours exception replaces the weekly hours; otherwise the weekly hours apply. Windows never cross
midnight (overnight shifts are two windows on two days); "24:00" as an end time means end of day.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EXCEPTION_KINDS = ("holiday", "closed", "special_hours")
WEEKDAY_KEYS = tuple(str(i) for i in range(1, 8))
HORIZON_DAYS = 400  # a year of holidays plus margin; beyond this the calendar is considered misconfigured
_HHMM = re.compile(r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")

Window = tuple[str, str]  # ("08:00", "17:30")


@dataclass(frozen=True)
class DayException:
    date_from: date
    date_to: date
    kind: str
    hours: list[Window] = field(default_factory=list)
    label: str = ""

    def covers(self, day: date) -> bool:
        return self.date_from <= day <= self.date_to


@dataclass(frozen=True)
class Calendar:
    timezone: str
    weekly_hours: dict[str, list[Window]]
    exceptions: tuple[DayException, ...] = ()

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _t(hhmm: str) -> time:
    if hhmm == "24:00":
        return time.max
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def window_problems(windows: list, where: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(windows, list):
        return [f"{where}: phải là danh sách khung giờ"]
    parsed = []
    for w in windows:
        if not (isinstance(w, list | tuple) and len(w) == 2 and all(isinstance(x, str) for x in w)):
            problems.append(f'{where}: khung giờ phải có dạng ["08:00", "17:30"]')
            continue
        if not (_HHMM.match(w[0]) and _HHMM.match(w[1])) or w[0] == "24:00":
            problems.append(f"{where}: giờ phải theo dạng HH:MM")
            continue
        if _t(w[0]) >= _t(w[1]):
            problems.append(f"{where}: giờ đóng cửa phải sau giờ mở cửa ({w[0]}–{w[1]})")
            continue
        parsed.append((_t(w[0]), _t(w[1])))
    parsed.sort()
    for (_, end), (start, _) in zip(parsed, parsed[1:], strict=False):
        if start < end:
            problems.append(f"{where}: các khung giờ bị chồng nhau")
    return problems


def weekly_problems(weekly: dict) -> list[str]:
    if not isinstance(weekly, dict) or set(weekly) - set(WEEKDAY_KEYS):
        return ["Giờ làm việc phải theo thứ trong tuần, khóa 1 (Thứ Hai) đến 7 (Chủ nhật)"]
    problems = [p for k, v in weekly.items() for p in window_problems(v, f"Ngày {k}")]
    if not problems and not any(weekly.get(k) for k in WEEKDAY_KEYS):
        problems.append("Cần ít nhất một ngày mở cửa trong tuần")
    return problems


def timezone_problem(name: str) -> str | None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return f"Múi giờ không hợp lệ: {name}"
    return None


def windows_on(cal: Calendar, day: date) -> list[tuple[time, time]]:
    """Opening windows for a local date, after applying exceptions."""
    covering = [e for e in cal.exceptions if e.covers(day)]
    if any(e.kind in ("holiday", "closed") for e in covering):
        return []
    special = [e for e in covering if e.kind == "special_hours"]
    raw = special[-1].hours if special else cal.weekly_hours.get(str(day.isoweekday()), [])
    return sorted((_t(a), _t(b)) for a, b in raw)


def exception_on(cal: Calendar, day: date) -> DayException | None:
    covering = [e for e in cal.exceptions if e.covers(day)]
    closed = [e for e in covering if e.kind in ("holiday", "closed")]
    return (closed or covering or [None])[-1]


@dataclass(frozen=True)
class Status:
    open: bool
    closes_at: datetime | None  # end of the current window when open
    opens_at: datetime | None  # start of the next window when closed (None if none within horizon)
    reason: str  # "open" | "outside_hours" | holiday label


def status_at(cal: Calendar, at: datetime) -> Status:
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    tz = cal.tz
    local = at.astimezone(tz)
    for start, end in windows_on(cal, local.date()):
        if start <= local.time() < end:
            return Status(True, datetime.combine(local.date(), end, tz), None, "open")
    exc = exception_on(cal, local.date())
    reason = exc.label or exc.kind if exc and exc.kind != "special_hours" else "outside_hours"
    return Status(False, None, next_open(cal, at), reason)


def next_open(cal: Calendar, at: datetime) -> datetime | None:
    """`at` itself when open, otherwise the start of the next opening window (AC23)."""
    tz = cal.tz
    local = at.astimezone(tz)
    for offset in range(HORIZON_DAYS):
        day = local.date() + timedelta(days=offset)
        for start, end in windows_on(cal, day):
            if offset == 0 and local.time() >= end:
                continue
            if offset == 0 and start <= local.time():
                return at
            return datetime.combine(day, start, tz)
    return None


def due_in_next_window(cal: Calendar, at: datetime, grace: timedelta) -> datetime | None:
    """Due time for work that arrives at `at`: `grace` after it if open now, else `grace` after the next
    opening, clamped to the end of that window so the task is due while someone is at work (AC24)."""
    start = next_open(cal, at)
    if start is None:
        return None
    local = start.astimezone(cal.tz)
    for w_start, w_end in windows_on(cal, local.date()):
        if w_start <= local.time() < w_end:
            return min(start + grace, datetime.combine(local.date(), w_end, cal.tz))
    return start + grace
