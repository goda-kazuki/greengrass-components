import pytest

from scd40_publisher.sensor import Scd40Sensor, SensorReading


class FakeDevice:
    def __init__(self) -> None:
        self.data_ready = False
        self.CO2 = 812
        self.temperature = 24.3
        self.relative_humidity = 45.2
        self.start_call_count = 0
        self._reads_before_ready = 2

    def start_periodic_measurement(self) -> None:
        self.start_call_count += 1

    def tick(self) -> None:
        self._reads_before_ready -= 1
        if self._reads_before_ready <= 0:
            self.data_ready = True


def test_read_starts_measurement_once():
    device = FakeDevice()
    device.data_ready = True
    sensor = Scd40Sensor(device, poll_interval_seconds=0)

    sensor.read()
    sensor.read()

    assert device.start_call_count == 1


def test_read_waits_until_data_ready(monkeypatch):
    device = FakeDevice()
    sleeps = []
    monkeypatch.setattr(
        "scd40_publisher.sensor.time.sleep",
        lambda s: (sleeps.append(s), device.tick()),
    )

    sensor = Scd40Sensor(device, poll_interval_seconds=0.01)
    reading = sensor.read()

    assert reading == SensorReading(co2_ppm=812, temperature_c=24.3, humidity_percent=45.2)
    assert sleeps == [0.01, 0.01]


def test_read_raises_timeout_when_data_never_ready_and_restarts_measurement(monkeypatch):
    device = FakeDevice()
    device._reads_before_ready = 10**9  # data_ready が永遠に true にならない
    now = [1000.0]

    def fake_sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr("scd40_publisher.sensor.time.sleep", fake_sleep)
    monkeypatch.setattr("scd40_publisher.sensor.time.monotonic", lambda: now[0])

    sensor = Scd40Sensor(device, poll_interval_seconds=1.0, max_wait_seconds=5.0)

    with pytest.raises(TimeoutError, match="5"):
        sensor.read()
    assert device.start_call_count == 1
    assert now[0] - 1000.0 == 5.0

    # 次のサイクルでは start_periodic_measurement を再送する
    with pytest.raises(TimeoutError):
        sensor.read()
    assert device.start_call_count == 2
