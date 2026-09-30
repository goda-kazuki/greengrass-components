import logging

import pytest

from scd40_publisher.main import main, run_cycle
from scd40_publisher.sensor import SensorReading


class FakeSensor:
    def __init__(self, readings=None, fail=False):
        self._readings = list(readings or [])
        self._fail = fail

    def read(self):
        if self._fail:
            raise RuntimeError("sensor error")
        return self._readings.pop(0)


class FakePublisher:
    def __init__(self, fail=False):
        self.published = []
        self._fail = fail

    def publish(self, reading):
        if self._fail:
            raise RuntimeError("publish error")
        self.published.append(reading)


def test_run_cycle_publishes_reading_on_success():
    reading = SensorReading(co2_ppm=812, temperature_c=24.3, humidity_percent=45.2)
    sensor = FakeSensor(readings=[reading])
    publisher = FakePublisher()

    run_cycle(sensor, publisher)

    assert publisher.published == [reading]


def test_run_cycle_logs_and_continues_on_sensor_failure(caplog):
    sensor = FakeSensor(fail=True)
    publisher = FakePublisher()

    with caplog.at_level(logging.ERROR):
        run_cycle(sensor, publisher)

    assert publisher.published == []
    assert "センサー読み取りに失敗しました" in caplog.text


def test_run_cycle_logs_and_drops_on_publish_failure(caplog):
    reading = SensorReading(co2_ppm=812, temperature_c=24.3, humidity_percent=45.2)
    sensor = FakeSensor(readings=[reading])
    publisher = FakePublisher(fail=True)

    with caplog.at_level(logging.ERROR):
        run_cycle(sensor, publisher)

    assert "AWS IoT Coreへの送信に失敗しました" in caplog.text


def test_main_exits_when_sensor_factory_fails():
    def failing_sensor_factory():
        raise RuntimeError("no i2c device")

    with pytest.raises(SystemExit) as exc_info:
        main(
            sensor_factory=failing_sensor_factory,
            publisher_factory=lambda topic: FakePublisher(),
            max_cycles=1,
        )

    assert exc_info.value.code == 1


def test_main_runs_bounded_number_of_cycles():
    reading = SensorReading(co2_ppm=812, temperature_c=24.3, humidity_percent=45.2)
    sensor = FakeSensor(readings=[reading, reading, reading])
    publisher = FakePublisher()
    sleeps = []

    main(
        sensor_factory=lambda: sensor,
        publisher_factory=lambda topic: publisher,
        sleep_fn=sleeps.append,
        max_cycles=3,
    )

    assert len(publisher.published) == 3
    assert len(sleeps) == 2


def test_main_uses_environment_overrides_for_topic_and_interval(monkeypatch):
    monkeypatch.setenv("GG_TOPIC_NAME", "custom/topic")
    monkeypatch.setenv("GG_MEASUREMENT_INTERVAL_SECONDS", "5")

    reading = SensorReading(co2_ppm=1, temperature_c=2.0, humidity_percent=3.0)
    sensor = FakeSensor(readings=[reading, reading])
    captured_topics = []

    def publisher_factory(topic):
        captured_topics.append(topic)
        return FakePublisher()

    sleeps = []

    main(
        sensor_factory=lambda: sensor,
        publisher_factory=publisher_factory,
        sleep_fn=sleeps.append,
        max_cycles=2,
    )

    assert captured_topics == ["custom/topic"]
    assert sleeps == [5.0]
