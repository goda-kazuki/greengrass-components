from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Protocol

from scd40_publisher.sensor import SensorReading


class IpcPublishClient(Protocol):
    def publish(self, topic: str, payload: bytes) -> None: ...


class IoTCorePublisher:
    def __init__(self, ipc_client: IpcPublishClient, topic: str) -> None:
        self._ipc_client = ipc_client
        self._topic = topic

    def publish(self, reading: SensorReading) -> None:
        payload = {
            **asdict(reading),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._ipc_client.publish(self._topic, json.dumps(payload).encode("utf-8"))


def create_ipc_publisher(topic: str) -> IoTCorePublisher:
    import awsiot.greengrasscoreipc
    from awsiot.greengrasscoreipc.model import PublishToIoTCoreRequest, QOS

    connection = awsiot.greengrasscoreipc.connect()

    class _IpcAdapter:
        def publish(self, topic: str, payload: bytes) -> None:
            request = PublishToIoTCoreRequest(
                topic_name=topic, payload=payload, qos=QOS.AT_LEAST_ONCE
            )
            operation = connection.new_publish_to_iot_core()
            operation.activate(request)
            operation.get_response().result(timeout=10)

    return IoTCorePublisher(_IpcAdapter(), topic)
