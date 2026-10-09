import pytest
import time
from app.bot.utils.formatters import (
    traffic_gb_to_bytes,
    bytes_to_human,
    days_to_epoch_expire,
    format_price,
    progress_bar,
    remaining_time_human,
    format_timestamp,
)


def test_traffic_gb_to_bytes():
    assert traffic_gb_to_bytes(1.0) == 1024 ** 3
    assert traffic_gb_to_bytes(10.0) == 10 * (1024 ** 3)
    assert traffic_gb_to_bytes(0.5) == int(0.5 * (1024 ** 3))


def test_bytes_to_human():
    assert bytes_to_human(1024 ** 3) == "1.00 GB"
    assert bytes_to_human(10 * 1024 ** 3) == "10.00 GB"
    assert bytes_to_human(512 * 1024 ** 2) == "512.0 MB"
    assert bytes_to_human(0) == "0.0 MB"


def test_days_to_epoch_expire():
    now = int(time.time())
    expire = days_to_epoch_expire(30)
    assert expire >= now + (30 * 86400) - 2
    assert expire <= now + (30 * 86400) + 2


def test_format_price():
    assert format_price(100000, "تومان") == "100،000 تومان"
    assert format_price(50000, "IRT") == "50،000 IRT"


def test_progress_bar():
    bar_0 = progress_bar(0, 100, length=10)
    assert bar_0 == "[░░░░░░░░░░] 0%"

    bar_50 = progress_bar(50, 100, length=10)
    assert bar_50 == "[█████░░░░░] 50%"

    bar_100 = progress_bar(100, 100, length=10)
    assert bar_100 == "[██████████] 100%"


def test_remaining_time_human():
    now = int(time.time())
    # Past
    assert "منقضی شده" in remaining_time_human(now - 100)

    # Future: 5 days
    res = remaining_time_human(now + (5 * 86400) + 3600)
    assert "5 روز" in res


def test_format_timestamp():
    epoch = 1775730000  # A valid timestamp in future/past
    formatted = format_timestamp(epoch, include_time=True)
    assert len(formatted) > 5
    assert "/" in formatted
