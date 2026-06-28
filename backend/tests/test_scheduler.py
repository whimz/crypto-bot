from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import scheduler


@pytest.fixture(autouse=True)
def reset_scheduler_state(monkeypatch):
    """Each test gets a clean slate for the module-level state _check_inactivity reads/writes."""
    monkeypatch.setattr(scheduler, "_last_cycle_at", None)
    monkeypatch.setattr(scheduler, "_last_inactivity_alert_at", None)
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler.telegram, "notify_inactive", MagicMock())
    monkeypatch.setattr(scheduler.telegram, "notify_error", MagicMock())


def test_check_inactivity_does_nothing_when_cycle_is_fresh():
    scheduler._last_cycle_at = datetime.now(timezone.utc)
    scheduler._check_inactivity()
    scheduler.telegram.notify_inactive.assert_not_called()
    scheduler.telegram.notify_error.assert_not_called()


def test_check_inactivity_does_nothing_without_a_baseline_cycle():
    scheduler._check_inactivity()  # _last_cycle_at is None
    scheduler.telegram.notify_inactive.assert_not_called()


def test_check_inactivity_recovers_stalled_run_cycle_job():
    scheduler._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=scheduler.INACTIVITY_THRESHOLD_MINUTES + 1)
    mock_scheduler = MagicMock()
    scheduler._scheduler = mock_scheduler

    scheduler._check_inactivity()

    scheduler.telegram.notify_inactive.assert_called_once()
    mock_scheduler.add_job.assert_called_once()
    args, kwargs = mock_scheduler.add_job.call_args
    assert args[0] is scheduler.run_cycle
    assert kwargs["id"] == "run_cycle"
    assert kwargs["replace_existing"] is True
    scheduler.telegram.notify_error.assert_called_once()


def test_check_inactivity_recovery_is_a_noop_without_a_scheduler_instance():
    scheduler._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=scheduler.INACTIVITY_THRESHOLD_MINUTES + 1)
    scheduler._scheduler = None

    scheduler._check_inactivity()  # must not raise

    scheduler.telegram.notify_inactive.assert_called_once()
    scheduler.telegram.notify_error.assert_not_called()


def test_check_inactivity_respects_cooldown_between_recovery_attempts():
    scheduler._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=scheduler.INACTIVITY_THRESHOLD_MINUTES + 1)
    mock_scheduler = MagicMock()
    scheduler._scheduler = mock_scheduler

    scheduler._check_inactivity()
    scheduler._check_inactivity()  # still within INACTIVITY_ALERT_COOLDOWN_MINUTES

    scheduler.telegram.notify_inactive.assert_called_once()
    mock_scheduler.add_job.assert_called_once()
