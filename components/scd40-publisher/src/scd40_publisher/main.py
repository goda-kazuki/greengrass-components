from __future__ import annotations

import logging
import math
import os
import sys
import time
from typing import Callable, Optional

from scd40_publisher.publisher import IoTCorePublisher, create_ipc_publisher
from scd40_publisher.sensor import Scd40Sensor, create_hardware_sensor

logger = logging.getLogger("scd40_publisher")

DEFAULT_TOPIC = "greengrass-components/scd40-publisher/default/telemetry"
DEFAULT_INTERVAL_SECONDS = 60.0


def _validate_interval(interval_str: str, default: float) -> float:
    """Validate and parse the measurement interval in seconds.

    Valid: parses as float, is finite, and > 0.
    Invalid: non-numeric, 0, negative, nan, inf.
    """
    value_to_parse = interval_str if interval_str else default
    try:
        interval = float(value_to_parse)
    except (ValueError, TypeError) as e:
        raise ValueError(f"非数値: {interval_str}") from e

    if not math.isfinite(interval) or interval <= 0:
        raise ValueError(f"正の有限値ではありません: {interval}")

    return interval


def run_cycle(sensor: Scd40Sensor, publisher: IoTCorePublisher) -> None:
    try:
        reading = sensor.read()
    except Exception:
        logger.exception("センサー読み取りに失敗しました。次のサイクルで再試行します。")
        return

    try:
        publisher.publish(reading)
    except Exception:
        logger.exception("AWS IoT Coreへの送信に失敗しました。このデータは破棄します。")


def main(
    sensor_factory: Callable[[], Scd40Sensor] = create_hardware_sensor,
    publisher_factory: Callable[[str], IoTCorePublisher] = create_ipc_publisher,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_cycles: Optional[int] = None,
) -> None:
    logging.basicConfig(level=logging.INFO)

    topic = os.environ.get("GG_TOPIC_NAME", DEFAULT_TOPIC)
    interval_str = os.environ.get("GG_MEASUREMENT_INTERVAL_SECONDS", "")

    try:
        interval_seconds = _validate_interval(interval_str, DEFAULT_INTERVAL_SECONDS)
    except ValueError:
        logger.exception(
            f"無効な測定間隔です。環境変数 GG_MEASUREMENT_INTERVAL_SECONDS={interval_str} "
            f"(デフォルト: {DEFAULT_INTERVAL_SECONDS})"
        )
        sys.exit(1)

    try:
        sensor = sensor_factory()
    except Exception:
        logger.exception("SCD40センサーの初期化に失敗しました。起動を中止します。")
        sys.exit(1)

    publisher = publisher_factory(topic)

    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        run_cycle(sensor, publisher)
        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            sleep_fn(interval_seconds)


if __name__ == "__main__":
    main()
