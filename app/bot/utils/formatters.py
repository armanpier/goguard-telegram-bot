import datetime
import time
from typing import Tuple
import jdatetime


def traffic_gb_to_bytes(gb: float) -> int:
    """Convert Gigabytes to exact Bytes."""
    return int(float(gb) * (1024 ** 3))


def bytes_to_human(byte_val: int) -> str:
    """Format bytes into readable GB / MB representation."""
    if byte_val < 0:
        return "0 MB"
    gb = byte_val / (1024 ** 3)
    if gb >= 1.0:
        return f"{gb:.2f} GB"
    mb = byte_val / (1024 ** 2)
    return f"{mb:.1f} MB"


def days_to_epoch_expire(days: int) -> int:
    """Calculate future Unix timestamp from current time in days."""
    return int(time.time() + (days * 86400))


def format_timestamp(epoch_ts: int, include_time: bool = True) -> str:
    """Convert Unix epoch timestamp to Jalali (Shamsi) formatted string."""
    try:
        dt = datetime.datetime.fromtimestamp(epoch_ts, tz=datetime.timezone.utc)
        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        if include_time:
            return jdt.strftime("%Y/%m/%d %H:%M")
        return jdt.strftime("%Y/%m/%d")
    except Exception:
        # Fallback to Gregorian if conversion fails
        return time.strftime("%Y-%m-%d %H:%M", time.gmtime(epoch_ts))


def remaining_time_human(epoch_ts: int) -> str:
    """Return human readable remaining time."""
    now = int(time.time())
    diff = epoch_ts - now
    if diff <= 0:
        return "منقضی شده ❌"

    days = diff // 86400
    hours = (diff % 86400) // 3600
    if days > 0:
        return f"{days} روز و {hours} ساعت باقی‌مانده"
    minutes = (diff % 3600) // 60
    return f"{hours} ساعت و {minutes} دقیقه باقی‌مانده"


def progress_bar(used: float, total: float, length: int = 10) -> str:
    """
    Generate visual progress bar string.
    Example: [██████░░░░] 60%
    """
    if total <= 0:
        return "░" * length + " 0%"

    percent = min(max(used / total, 0.0), 1.0)
    filled_len = int(round(length * percent))
    bar = "█" * filled_len + "░" * (length - filled_len)
    return f"[{bar}] {int(percent * 100)}%"


def format_price(amount: int, currency: str = "تومان") -> str:
    """Format numeric price with thousands separator and currency."""
    return f"{amount:,.0f} {currency}".replace(",", "،")
