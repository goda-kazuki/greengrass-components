from scd40_publisher.sensor import Scd40Sensor, SensorReading


class FakeDevice:
    def __init__(self) -> None:
        self.data_ready = False
        self.CO2 = 812
        self.temperature = 24.3
        self.relative_humidity = 45.2
        self.start_called = False
        self._reads_before_ready = 2

    def start_periodic_measurement(self) -> None:
        self.start_called = True

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

    assert device.start_called is True


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
    assert len(sleeps) == 2
