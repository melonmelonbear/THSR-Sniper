from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Union
import re

STATION_MAP = [
    "Nangang",
    "Taipei",
    "Banqiao",
    "Taoyuan",
    "Hsinchu",
    "Miaoli",
    "Taichung",
    "Changhua",
    "Yunlin",
    "Chiayi",
    "Tainan",
    "Zuouing",
]

TIME_TABLE = [
    "1201A",
    "1230A",
    "600A",
    "630A",
    "700A",
    "730A",
    "800A",
    "830A",
    "900A",
    "930A",
    "1000A",
    "1030A",
    "1100A",
    "1130A",
    "1200N",
    "1230P",
    "100P",
    "130P",
    "200P",
    "230P",
    "300P",
    "330P",
    "400P",
    "430P",
    "500P",
    "530P",
    "600P",
    "630P",
    "700P",
    "730P",
    "800P",
    "830P",
    "900P",
    "930P",
    "1000P",
    "1030P",
    "1100P",
    "1130P",
]

class TicketType:
    Adult = "F"
    Child = "H"
    Disabled = "W"
    Elder = "E"
    College = "P"


# Taiwan timezone utilities
TAIWAN_TZ = timezone(timedelta(hours=8))
THSR_SPECIAL_BOOKING_URL = "https://www.thsrc.com.tw/ArticleContent/60dbfb79-ac20-4280-8ffb-b09e7c94f043"
SPECIAL_BOOKING_CACHE_TTL = timedelta(hours=6)
_SPECIAL_BOOKING_WINDOWS_CACHE = {
    "fetched_at": None,
    "windows": [],
}


def get_taiwan_now() -> datetime:
    """Get current time in Taiwan timezone."""
    return datetime.now(TAIWAN_TZ)


def get_ticket_booking_window_end(now: Optional[datetime] = None):
    """Return the latest travel date currently open for THSR reserved-seat booking."""
    taiwan_now = now.astimezone(TAIWAN_TZ) if now else get_taiwan_now()
    today = taiwan_now.date()

    # THSR normally opens tickets within 29 days including today.
    latest_date = today + timedelta(days=28)

    # On Fridays and Saturdays, booking extends through the Sunday four weeks later.
    # Example: Friday 2024/01/05 can book through Sunday 2024/02/04.
    if today.weekday() in (4, 5):
        days_until_this_sunday = 6 - today.weekday()
        latest_date = today + timedelta(days=days_until_this_sunday + 28)

    return latest_date


def _parse_thsr_date(text: str):
    """Extract a THSR date value from text such as '2026/02/13 (五)'."""
    match = re.search(r"\d{4}/\d{1,2}/\d{1,2}", text or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y/%m/%d").date()
    except ValueError:
        return None


def _parse_special_booking_windows(html: str) -> List[Dict[str, object]]:
    """Parse THSR special transport periods and presale dates from the official table."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    windows = []

    for row in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("th,td")]
        if len(cells) < 3 or "疏運期間" in cells[1]:
            continue

        period_dates = re.findall(r"\d{4}/\d{1,2}/\d{1,2}", cells[1])
        if len(period_dates) < 2:
            continue

        start_date = _parse_thsr_date(period_dates[0])
        end_date = _parse_thsr_date(period_dates[1])
        presale_date = _parse_thsr_date(cells[2])

        if start_date and end_date and presale_date:
            windows.append({
                "name": cells[0],
                "start_date": start_date,
                "end_date": end_date,
                "presale_date": presale_date,
            })

    return windows


def get_special_booking_windows(now: Optional[datetime] = None, force_refresh: bool = False) -> List[Dict[str, object]]:
    """Fetch and cache THSR special transport presale windows from the official page."""
    taiwan_now = now.astimezone(TAIWAN_TZ) if now else get_taiwan_now()
    fetched_at = _SPECIAL_BOOKING_WINDOWS_CACHE["fetched_at"]

    if (
        not force_refresh and
        fetched_at and
        taiwan_now - fetched_at < SPECIAL_BOOKING_CACHE_TTL
    ):
        return list(_SPECIAL_BOOKING_WINDOWS_CACHE["windows"])

    try:
        import requests

        response = requests.get(
            THSR_SPECIAL_BOOKING_URL,
            timeout=10,
            headers={"User-Agent": "THSR-Sniper/1.0"},
        )
        response.raise_for_status()
        windows = _parse_special_booking_windows(response.text)
        _SPECIAL_BOOKING_WINDOWS_CACHE["fetched_at"] = taiwan_now
        _SPECIAL_BOOKING_WINDOWS_CACHE["windows"] = windows
        return list(windows)
    except Exception:
        return list(_SPECIAL_BOOKING_WINDOWS_CACHE["windows"])


def get_special_presale_date(booking_date_obj, now: Optional[datetime] = None):
    """Return the special presale date if the booking date is in a THSR transport period."""
    for window in get_special_booking_windows(now):
        if window["start_date"] <= booking_date_obj <= window["end_date"]:
            return window["presale_date"]
    return None


def is_ticket_sales_open(booking_date: str) -> bool:
    """
    Check if ticket sales are open for the given booking date.
    THSR opens reserved-seat booking for 29 days including today. On Fridays and
    Saturdays, booking extends through the Sunday four weeks later. For special
    transport periods, the official presale table takes precedence when available.
    """
    try:
        booking_date_obj = datetime.strptime(booking_date, "%Y/%m/%d").date()
        taiwan_now = get_taiwan_now()

        if booking_date_obj < taiwan_now.date():
            return False

        special_presale_date = get_special_presale_date(booking_date_obj, taiwan_now)
        if special_presale_date:
            return taiwan_now.date() >= special_presale_date

        return booking_date_obj <= get_ticket_booking_window_end(taiwan_now)
    except ValueError:
        return False


def parse_time_string(time_str: str) -> Optional[datetime]:
    """
    Parse time string from train data (e.g., "0800", "1430", "07:58") to datetime object.
    Returns None if parsing fails.
    """
    try:
        # Handle HH:MM format (e.g., "07:58")
        if ':' in time_str:
            hour, minute = time_str.split(':')
            hour = int(hour)
            minute = int(minute)
            return datetime.now(TAIWAN_TZ).replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Handle HHMM format (e.g., "0800")
        elif len(time_str) == 4:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            return datetime.now(TAIWAN_TZ).replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (ValueError, IndexError):
        pass
    return None


TimePreference = Union[int, str]


def get_time_preference_datetime(time_preference: TimePreference) -> Optional[datetime]:
    """Convert a legacy time slot ID or HH:MM value into a comparable datetime."""
    if isinstance(time_preference, int):
        if time_preference < 1 or time_preference > len(TIME_TABLE):
            return None
        return _parse_time_table_to_datetime(TIME_TABLE[time_preference - 1])

    if isinstance(time_preference, str):
        value = time_preference.strip()
        if not value:
            return None
        if value.isdigit():
            return get_time_preference_datetime(int(value))
        return parse_time_string(value)

    return None


def is_valid_time_preference(time_preference: TimePreference) -> bool:
    """Validate legacy time slot IDs and minute-level HH:MM values."""
    return get_time_preference_datetime(time_preference) is not None


def format_time_preference_for_form(time_preference: TimePreference) -> Optional[str]:
    """Convert a time preference to the value expected by the THSR booking form."""
    if isinstance(time_preference, int):
        if 1 <= time_preference <= len(TIME_TABLE):
            return TIME_TABLE[time_preference - 1]
        return None

    if isinstance(time_preference, str):
        value = time_preference.strip()
        if not value:
            return None
        if value.isdigit():
            return format_time_preference_for_form(int(value))
        parsed = parse_time_string(value)
        if parsed:
            return _get_time_table_option_at_or_before(parsed)

    return None


def _get_time_table_option_at_or_before(target_time: datetime) -> str:
    """Return the nearest official THSR query time option at or before the target."""
    parsed_options = []
    for option in TIME_TABLE:
        parsed = _parse_time_table_to_datetime(option)
        if parsed:
            parsed_options.append((parsed, option))

    earlier_options = [
        (parsed, option)
        for parsed, option in parsed_options
        if parsed.time() <= target_time.time()
    ]
    if earlier_options:
        return max(earlier_options, key=lambda item: item[0].time())[1]

    return parsed_options[0][1]


def parse_travel_minutes(travel_time: str) -> Optional[int]:
    """Parse THSR travel duration strings into minutes."""
    if not travel_time:
        return None

    value = travel_time.strip()
    if ":" in value:
        try:
            hours, minutes = value.split(":", 1)
            return int(hours) * 60 + int(minutes)
        except ValueError:
            return None

    hour_match = re.search(r"(\d+)\s*(?:小時|時|h)", value, re.IGNORECASE)
    minute_match = re.search(r"(\d+)\s*(?:分鐘|分|m)", value, re.IGNORECASE)
    if hour_match or minute_match:
        hours = int(hour_match.group(1)) if hour_match else 0
        minutes = int(minute_match.group(1)) if minute_match else 0
        return hours * 60 + minutes

    if value.isdigit():
        return int(value)

    return None


def find_closest_train_within_range(trains: List[Dict[str, str]], target_time: TimePreference, tolerance_hours: float = 0.5) -> Optional[Dict[str, str]]:
    """
    Find the closest train within ±tolerance_hours of the target time.
    Returns the shortest travel-time train, using departure closeness as a tie-breaker.
    """
    if not trains:
        return None
    
    target_datetime = get_time_preference_datetime(target_time)
    if not target_datetime:
        return None
    
    valid_trains = []
    
    for train in trains:
        depart_time_str = train.get('depart', '')
        if not depart_time_str:
            continue
            
        train_time = parse_time_string(depart_time_str)
        if not train_time:
            continue
        
        time_diff_minutes = abs((train_time - target_datetime).total_seconds()) / 60
        
        if time_diff_minutes <= tolerance_hours * 60:
            travel_minutes = parse_travel_minutes(train.get("travel_time", ""))
            valid_trains.append((
                train,
                time_diff_minutes,
                travel_minutes if travel_minutes is not None else float("inf"),
                train_time.time(),
            ))
    
    if not valid_trains:
        return None
    
    valid_trains.sort(key=lambda x: (x[2], x[1], x[3]))
    return valid_trains[0][0]


def _parse_time_table_to_datetime(time_str: str) -> Optional[datetime]:
    """
    Parse time string from TIME_TABLE (e.g., "800A", "200P") to datetime object.
    Returns None if parsing fails.
    """
    try:
        # Remove the last character (A/P/N)
        time_part = time_str[:-1]
        period = time_str[-1]
        
        # Convert to integer
        time_int = int(time_part)
        
        # Handle special cases
        if period == 'A' and time_int // 100 == 12:
            # 1201A, 1230A -> 00:01, 00:30
            time_int = time_int % 1200
        elif period == 'P' and time_int != 1230:
            # PM times (except 1230P which is noon)
            time_int += 1200
        elif period == 'N':
            # 1200N is noon
            time_int = 1200
        
        hour = time_int // 100
        minute = time_int % 100
        
        return datetime.now(TAIWAN_TZ).replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (ValueError, IndexError):
        return None
