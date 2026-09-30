from __future__ import annotations

import logging
import os
import sys
import time
from typing import Callable, Optional

from scd40_publisher.publisher import IoTCorePublisher, create_ipc_publisher
from scd40_publisher.sensor import Scd40Sensor, create_hardware_sensor

logger = logging.getLogger("scd40_publisher")

DEFAULT_TOPIC = "greengrass-components/scd40-publisher/default/telemetry"
DEFAULT_INTERVAL_SECONDS = 60.0


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
    interval_seconds = float(
        os.environ.get("GG_MEASUREMENT_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)
    )

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
