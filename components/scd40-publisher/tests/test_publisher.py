import json
import re

from scd40_publisher.publisher import IoTCorePublisher
from scd40_publisher.sensor import SensorReading


class FakeIpcClient:
    def __init__(self) -> None:
        self.published = []

    def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, payload))


def test_publish_sends_json_payload_to_configured_topic():
    fake_client = FakeIpcClient()
    publisher = IoTCorePublisher(
        fake_client, topic="greengrass-components/scd40-publisher/thing-1/telemetry"
    )
    reading = SensorReading(co2_ppm=812, temperature_c=24.3, humidity_percent=45.2)

    publisher.publish(reading)

    assert len(fake_client.published) == 1
    topic, payload = fake_client.published[0]
    assert topic == "greengrass-components/scd40-publisher/thing-1/telemetry"
    body = json.loads(payload.decode("utf-8"))
    assert body["co2_ppm"] == 812
    assert body["temperature_c"] == 24.3
    assert body["humidity_percent"] == 45.2
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", body["timestamp"])
