from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class Scd4xDevice(Protocol):
    data_ready: bool
    CO2: int
    temperature: float
    relative_humidity: float

    def start_periodic_measurement(self) -> None: ...


@dataclass
class SensorReading:
    co2_ppm: int
    temperature_c: float
    humidity_percent: float


class Scd40Sensor:
    def __init__(
        self,
        device: Scd4xDevice,
        poll_interval_seconds: float = 1.0,
        *,
        max_wait_seconds: float = 30.0,
    ) -> None:
        self._device = device
        self._poll_interval_seconds = poll_interval_seconds
        self._max_wait_seconds = max_wait_seconds
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._device.start_periodic_measurement()
            self._started = True

    def read(self) -> SensorReading:
        self.start()
        deadline = time.monotonic() + self._max_wait_seconds
        while not self._device.data_ready:
            if time.monotonic() >= deadline:
                # 次のサイクルで測定開始コマンドを再送させる
                self._started = False
                raise TimeoutError(
                    f"センサーのデータ準備が{self._max_wait_seconds}秒以内に完了しませんでした"
                )
            time.sleep(self._poll_interval_seconds)
        return SensorReading(
            co2_ppm=self._device.CO2,
            temperature_c=self._device.temperature,
            humidity_percent=self._device.relative_humidity,
        )


def create_hardware_sensor() -> Scd40Sensor:
    import board
    import busio
    from adafruit_scd4x import SCD4X

    i2c = busio.I2C(board.SCL, board.SDA)
    return Scd40Sensor(SCD4X(i2c))
