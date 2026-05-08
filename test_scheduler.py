import signal
import sys
from datetime import datetime

import scheduler as scheduler_module
from scheduler import GracefulShutdown, Scheduler, run_with_schedule


class FakeSchedule:
    def __init__(self):
        self.jobs = []
        self.pending_calls = 0
        self.scheduled_times = []

    def every(self):
        return FakeEvery(self)

    def get_jobs(self):
        return list(self.jobs)

    def run_pending(self):
        self.pending_calls += 1


class FakeEvery:
    def __init__(self, schedule):
        self.schedule = schedule

    @property
    def day(self):
        return self

    def at(self, schedule_time):
        self.schedule.scheduled_times.append(schedule_time)
        return self

    def do(self, callback):
        job = FakeJob(callback)
        self.schedule.jobs.append(job)
        return job


class FakeJob:
    def __init__(self, callback):
        self.callback = callback
        self.next_run = datetime(2026, 5, 8, 18, 30, 0)


class FakeShutdown:
    def __init__(self):
        self.checks = 0

    @property
    def should_shutdown(self):
        self.checks += 1
        return self.checks > 1


def test_graceful_shutdown_registers_handlers_and_records_signal(monkeypatch):
    registered = []
    monkeypatch.setattr(scheduler_module.signal, "signal", lambda signum, handler: registered.append((signum, handler)))

    shutdown = GracefulShutdown()

    assert [call[0] for call in registered] == [signal.SIGINT, signal.SIGTERM]
    assert shutdown.should_shutdown is False

    registered[0][1](signal.SIGINT, None)

    assert shutdown.should_shutdown is True


def test_scheduler_sets_daily_task_and_runs_callback(monkeypatch):
    fake_schedule = FakeSchedule()
    monkeypatch.setitem(sys.modules, "schedule", fake_schedule)
    monkeypatch.setattr(scheduler_module, "GracefulShutdown", lambda: FakeShutdown())
    calls = []

    scheduler = Scheduler(schedule_time="18:30")
    scheduler.set_daily_task(lambda: calls.append("ran"), run_immediately=True)

    assert fake_schedule.scheduled_times == ["18:30"]
    assert len(fake_schedule.jobs) == 1
    assert calls == ["ran"]
    assert scheduler._get_next_run_time() == "2026-05-08 18:30:00"


def test_safe_run_task_ignores_missing_task_and_logs_exceptions(monkeypatch, caplog):
    fake_schedule = FakeSchedule()
    monkeypatch.setitem(sys.modules, "schedule", fake_schedule)
    monkeypatch.setattr(scheduler_module, "GracefulShutdown", lambda: FakeShutdown())

    scheduler = Scheduler()
    scheduler._safe_run_task()

    def broken_task():
        raise RuntimeError("boom")

    scheduler._task_callback = broken_task
    scheduler._safe_run_task()

    assert "boom" in caplog.text


def test_scheduler_run_processes_pending_jobs_until_shutdown(monkeypatch):
    fake_schedule = FakeSchedule()
    monkeypatch.setitem(sys.modules, "schedule", fake_schedule)
    monkeypatch.setattr(scheduler_module, "GracefulShutdown", lambda: FakeShutdown())
    sleeps = []
    monkeypatch.setattr(scheduler_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    scheduler = Scheduler()
    scheduler.run()

    assert scheduler._running is True
    assert fake_schedule.pending_calls == 1
    assert sleeps == [30]

    scheduler.stop()

    assert scheduler._running is False


def test_run_with_schedule_delegates_to_scheduler(monkeypatch):
    events = []

    class FakeScheduler:
        def __init__(self, schedule_time):
            events.append(("init", schedule_time))

        def set_daily_task(self, task, run_immediately=True):
            events.append(("set", task(), run_immediately))

        def run(self):
            events.append(("run",))

    monkeypatch.setattr(scheduler_module, "Scheduler", FakeScheduler)

    run_with_schedule(lambda: "task-result", schedule_time="09:15", run_immediately=False)

    assert events == [("init", "09:15"), ("set", "task-result", False), ("run",)]
