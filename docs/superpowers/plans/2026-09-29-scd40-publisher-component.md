# scd40-publisher Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** リポジトリをuvワークスペースによるモノレポとして整備し、SCD40センサー(CO2・温度・湿度)の値をAWS IoT Coreへ定期送信するGreengrassカスタムコンポーネント`scd40-publisher`を実装し、ビルドスクリプトとドキュメントを揃える。デプロイ(S3アップロード・コンポーネント登録・デプロイ作成)は、アーティファクト用S3バケットが未作成のため今回のスコープ外とする。

**Architecture:** ルートにuvワークスペースを置き、`components/scd40-publisher/`配下にsrcレイアウトのPythonパッケージとしてコンポーネントを実装する。ハードウェア依存(I2C/`board`/`busio`)とGreengrass IPC依存は、実オブジェクトを生成する「ファクトリ関数」に隔離し、テストはファクトリを経由しないダックタイピングのフェイクオブジェクトで実行ロジックを検証する。ビルドはPythonスクリプト(`scripts/build_component.py`)として実装し、`subprocess`(uv export呼び出し)を注入可能にしてテストする。

**Tech Stack:** Python 3.13, uv(依存管理・ワークスペース), pytest, adafruit-circuitpython-scd4x, adafruit-blinka, awsiotsdk(Greengrass IPC), PyYAML

**Spec:** `docs/superpowers/specs/2026-09-29-greengrass-scd40-component-setup-design.md`

## Global Constraints

- パッケージ管理はuvを使用する。Raspberry Pi(Greengrassデバイス)側にはuvをインストールせず、`pip3`のみで依存を導入する(仕様書「依存関係管理の方針」)。
- モノレポ構成とし、コンポーネントは`components/`配下にディレクトリを追加する形で管理する。
- AWS側リソース(S3バケット、IoT Thing/Thing Group、IAMポリシー)の作成は本タスクのスコープ外。
- デプロイ関連(デプロイスクリプト、S3アップロード、コンポーネント登録、デプロイ作成、デプロイ手順書)は本タスクのスコープ外。アーティファクト用S3バケットが現在存在しないため。仕様書のデプロイ関連の記述は、S3バケット準備後の別タスクで実施する。
- CI(GitHub Actionsなど)の導入は本タスクのスコープ外。
- Pythonのバージョンは3.13とする。
- IoT Coreへの送信失敗時はローカルキューを持たず、ログ記録のみでデータを破棄する(仕様書「エラーハンドリング」)。
- 測定間隔のデフォルトは60秒、MQTTトピックのデフォルトは`greengrass-components/scd40-publisher/<thingName>/telemetry`(仕様書「MQTTトピック・ペイロード」)。

## Review Focus

- センサー読み取り失敗時にプロセスが落ちず、次の測定サイクルで継続すること。
- AWS IoT Coreへの送信失敗時にログのみを記録し、そのデータを破棄して処理を継続すること(例外を伝播させない)。
- 起動時にI2Cデバイスが検出できない場合にプロセスを終了し、再起動をGreengrassのライフサイクル管理に委ねること。
- レシピのComponentConfiguration(トピック名・測定間隔)が環境変数経由でmain.pyの実行に正しく反映されること。

---

## File Structure

```
greengrass-components/
├── pyproject.toml                          # uvワークスペースルート、共有dev依存(pytest/pyyaml)
├── .python-version
├── .gitignore
├── README.md                               # 更新: リポジトリの役割とセットアップ手順を追記
├── tests/
│   ├── test_recipe.py                      # recipe.yamlの構造検証
│   └── test_build_component.py             # scripts/build_component.pyの単体テスト
├── scripts/
│   └── build_component.py                  # ビルド(requirements.txt生成+zip化)
└── components/
    └── scd40-publisher/
        ├── pyproject.toml                  # コンポーネント個別の依存関係
        ├── recipe.yaml                     # Greengrassレシピ(バージョン/URIは仮の値。デプロイ整備時に注入する)
        ├── src/
        │   └── scd40_publisher/
        │       ├── __init__.py
        │       ├── sensor.py                # Scd40Sensor, SensorReading, create_hardware_sensor
        │       ├── publisher.py             # IoTCorePublisher, create_ipc_publisher
        │       └── main.py                  # run_cycle, main (エントリポイント)
        └── tests/
            ├── test_sensor.py
            ├── test_publisher.py
            └── test_main.py
```

---

### Task 1: uvワークスペースとコンポーネント雛形の作成

**Files:**
- Create: `pyproject.toml`(ルート)
- Create: `.python-version`
- Create: `.gitignore`
- Create: `components/scd40-publisher/pyproject.toml`
- Create: `components/scd40-publisher/src/scd40_publisher/__init__.py`
- Create: `components/scd40-publisher/tests/__init__.py`は作らない(src配置のためpytestのrootdir自動検出に委ねる)
- Modify: `README.md`

**Interfaces:**
- Produces: `scd40_publisher`パッケージ(空の`__init__.py`)、`uv run pytest`が実行可能な状態

- [ ] **Step 1: 雛形作成前の状態を確認する(失敗するテストを先に書く)**

`components/scd40-publisher/tests/test_package.py`を作成する。

```python
def test_package_is_importable():
    import scd40_publisher

    assert scd40_publisher is not None
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_package.py -v`
Expected: FAIL(uvワークスペースが未設定、または`scd40_publisher`が見つからないエラー)

- [ ] **Step 3: ルートのuvワークスペース設定を作成する**

`pyproject.toml`(ルート):

```toml
[project]
name = "greengrass-components"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pyyaml",
]

[tool.uv.workspace]
members = ["components/*"]

[tool.uv]
package = false

[dependency-groups]
dev = ["pytest"]

[tool.pytest.ini_options]
pythonpath = ["scripts"]
testpaths = ["tests", "components"]
```

`.python-version`:

```
3.13
```

`.gitignore`:

```
.venv/
build/
__pycache__/
*.pyc
```

- [ ] **Step 4: コンポーネントの雛形を作成する**

`components/scd40-publisher/pyproject.toml`:

```toml
[project]
name = "scd40-publisher"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "adafruit-circuitpython-scd4x",
    "adafruit-blinka",
    "awsiotsdk",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/scd40_publisher"]
```

`components/scd40-publisher/src/scd40_publisher/__init__.py`:

```python
```

(空ファイルでよい)

- [ ] **Step 5: `uv sync`を実行し、依存関係を解決する**

Run: `uv sync`
Expected: Python 3.13の`.venv`が作成され、ワークスペース全体の依存関係(pytest, pyyaml, adafruit-circuitpython-scd4x, adafruit-blinka, awsiotsdk)がインストールされる

- [ ] **Step 6: テストが通ることを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_package.py -v`
Expected: PASS

- [ ] **Step 7: README.mdを更新する**

`README.md`に以下を追記する。

```markdown
# greengrass-components

Raspberry Pi上のAWS IoT Greengrassデバイスにデプロイする、自作コンポーネントの開発・ビルドを管理するモノレポです。

## セットアップ

```bash
uv sync
uv run pytest
```

## コンポーネント一覧

- `components/scd40-publisher`: SCD40センサー(CO2・温度・湿度)の値をAWS IoT Coreへ定期送信するコンポーネント

## ビルド

```bash
uv run python scripts/build_component.py scd40-publisher
```

`build/scd40-publisher/<version>/scd40-publisher.zip`が生成されます。

## デプロイ

未整備です(アーティファクト格納用のS3バケットを用意した後に追加します)。
```

- [ ] **Step 8: コミットする**

```bash
git add pyproject.toml .python-version .gitignore README.md components/scd40-publisher
git commit -m "uvワークスペースとscd40-publisherコンポーネントの雛形を追加"
```

---

### Task 2: `sensor.py` — SCD40読み取りロジック(TDD)

**Files:**
- Create: `components/scd40-publisher/src/scd40_publisher/sensor.py`
- Test: `components/scd40-publisher/tests/test_sensor.py`

**Interfaces:**
- Produces:
  - `class SensorReading`(dataclass): フィールド `co2_ppm: int`, `temperature_c: float`, `humidity_percent: float`
  - `class Scd40Sensor.__init__(self, device, poll_interval_seconds: float = 1.0)`
  - `Scd40Sensor.read(self) -> SensorReading`
  - `create_hardware_sensor() -> Scd40Sensor`(実機の`board`/`busio`/`adafruit_scd4x`を関数内で遅延importする。テストからは呼び出さない)

- [ ] **Step 1: 失敗するテストを書く**

`components/scd40-publisher/tests/test_sensor.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_sensor.py -v`
Expected: FAIL(`sensor`モジュールが存在しない)

- [ ] **Step 3: 実装する**

`components/scd40-publisher/src/scd40_publisher/sensor.py`:

```python
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
    def __init__(self, device: Scd4xDevice, poll_interval_seconds: float = 1.0) -> None:
        self._device = device
        self._poll_interval_seconds = poll_interval_seconds
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._device.start_periodic_measurement()
            self._started = True

    def read(self) -> SensorReading:
        self.start()
        while not self._device.data_ready:
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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_sensor.py -v`
Expected: PASS(2件)

- [ ] **Step 5: コミットする**

```bash
git add components/scd40-publisher/src/scd40_publisher/sensor.py components/scd40-publisher/tests/test_sensor.py
git commit -m "SCD40センサー読み取りロジックを実装"
```

---

### Task 3: `publisher.py` — AWS IoT Coreへのパブリッシュ(TDD)

**Files:**
- Create: `components/scd40-publisher/src/scd40_publisher/publisher.py`
- Test: `components/scd40-publisher/tests/test_publisher.py`

**Interfaces:**
- Consumes: `SensorReading`(`scd40_publisher.sensor`, Task 2で定義)
- Produces:
  - `class IoTCorePublisher.__init__(self, ipc_client, topic: str)`
  - `IoTCorePublisher.publish(self, reading: SensorReading) -> None`
  - `create_ipc_publisher(topic: str) -> IoTCorePublisher`(実際のGreengrass IPC接続を関数内で遅延importする。テストからは呼び出さない)

- [ ] **Step 1: 失敗するテストを書く**

`components/scd40-publisher/tests/test_publisher.py`:

```python
import json

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
    assert "timestamp" in body
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_publisher.py -v`
Expected: FAIL(`publisher`モジュールが存在しない)

- [ ] **Step 3: 実装する**

`components/scd40-publisher/src/scd40_publisher/publisher.py`:

```python
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_publisher.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add components/scd40-publisher/src/scd40_publisher/publisher.py components/scd40-publisher/tests/test_publisher.py
git commit -m "AWS IoT CoreへのパブリッシュロジックをGreengrass IPC経由で実装"
```

---

### Task 4: `main.py` — エントリポイントと実行ループ(TDD)

**Files:**
- Create: `components/scd40-publisher/src/scd40_publisher/main.py`
- Test: `components/scd40-publisher/tests/test_main.py`

**Interfaces:**
- Consumes:
  - `Scd40Sensor`, `create_hardware_sensor`(`scd40_publisher.sensor`)
  - `IoTCorePublisher`, `create_ipc_publisher`(`scd40_publisher.publisher`)
- Produces:
  - `run_cycle(sensor, publisher) -> None`
  - `main(sensor_factory=create_hardware_sensor, publisher_factory=create_ipc_publisher, sleep_fn=time.sleep, max_cycles=None) -> None`
  - 環境変数 `GG_TOPIC_NAME`(既定値: `greengrass-components/scd40-publisher/default/telemetry`)、`GG_MEASUREMENT_INTERVAL_SECONDS`(既定値: `60`)を読み取る

- [ ] **Step 1: 失敗するテストを書く**

`components/scd40-publisher/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_main.py -v`
Expected: FAIL(`main`モジュールが存在しない)

- [ ] **Step 3: 実装する**

`components/scd40-publisher/src/scd40_publisher/main.py`:

```python
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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest components/scd40-publisher/tests/test_main.py -v`
Expected: PASS(6件)

- [ ] **Step 5: コミットする**

```bash
git add components/scd40-publisher/src/scd40_publisher/main.py components/scd40-publisher/tests/test_main.py
git commit -m "scd40-publisherのエントリポイントと実行ループを実装"
```

---

### Task 5: `recipe.yaml` — Greengrassレシピと検証テスト

**Files:**
- Create: `components/scd40-publisher/recipe.yaml`
- Test: `tests/test_recipe.py`(ルートの`tests/`)

**Interfaces:**
- Produces: `recipe.yaml`(`ComponentConfiguration.DefaultConfiguration.topicName`, `measurementIntervalSeconds`。`ComponentVersion`と`Manifests[0].Artifacts[0].URI`は、将来のデプロイ処理(本計画のスコープ外)が書き換える前提のプレースホルダーであり、今回は仮の値のままとする)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_recipe.py`:

```python
from pathlib import Path

import yaml

RECIPE_PATH = (
    Path(__file__).resolve().parents[1]
    / "components"
    / "scd40-publisher"
    / "recipe.yaml"
)


def test_recipe_has_required_top_level_keys():
    recipe = yaml.safe_load(RECIPE_PATH.read_text())

    assert recipe["ComponentName"] == "com.example.Scd40Publisher"
    assert "DefaultConfiguration" in recipe["ComponentConfiguration"]


def test_recipe_default_configuration_has_topic_and_interval():
    recipe = yaml.safe_load(RECIPE_PATH.read_text())
    default_config = recipe["ComponentConfiguration"]["DefaultConfiguration"]

    assert "topicName" in default_config
    assert "measurementIntervalSeconds" in default_config


def test_recipe_lifecycle_installs_requirements_and_runs_main():
    recipe = yaml.safe_load(RECIPE_PATH.read_text())
    manifest = recipe["Manifests"][0]

    assert "requirements.txt" in manifest["Lifecycle"]["Install"]
    assert "scd40_publisher.main" in manifest["Lifecycle"]["Run"]
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_recipe.py -v`
Expected: FAIL(`recipe.yaml`が存在しない)

- [ ] **Step 3: `recipe.yaml`を作成する**

`components/scd40-publisher/recipe.yaml`:

```yaml
# ComponentVersion と Manifests[0].Artifacts[0].URI は仮の値。
# デプロイ処理を整備する際に、実際の値へ書き換える仕組みを追加する。
RecipeFormatVersion: "2020-01-25"
ComponentName: "com.example.Scd40Publisher"
ComponentVersion: "0.0.0"
ComponentDescription: "SCD40センサーのCO2・温度・湿度をAWS IoT Coreへ定期送信するコンポーネント"
ComponentPublisher: "greengrass-components"
ComponentConfiguration:
  DefaultConfiguration:
    topicName: "greengrass-components/scd40-publisher/{iot:thingName}/telemetry"
    measurementIntervalSeconds: "60"
Manifests:
  - Platform:
      os: linux
    Lifecycle:
      Install: "pip3 install --user -r {artifacts:path}/requirements.txt"
      Run: |
        GG_TOPIC_NAME="{configuration:/topicName}" GG_MEASUREMENT_INTERVAL_SECONDS="{configuration:/measurementIntervalSeconds}" PYTHONPATH="{artifacts:path}/src" python3 -m scd40_publisher.main
    Artifacts:
      - URI: "s3://PLACEHOLDER_BUCKET/scd40-publisher/0.0.0/scd40-publisher.zip"
        Unarchive: ZIP
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest tests/test_recipe.py -v`
Expected: PASS(3件)

- [ ] **Step 5: コミットする**

```bash
git add components/scd40-publisher/recipe.yaml tests/test_recipe.py
git commit -m "scd40-publisherのGreengrassレシピを追加"
```

---

### Task 6: `scripts/build_component.py` — ビルドスクリプト(TDD)

**Files:**
- Create: `scripts/build_component.py`
- Test: `tests/test_build_component.py`

**Interfaces:**
- Produces:
  - `read_component_version(component_dir: Path) -> str`
  - `export_requirements(component_dir: Path, runner) -> str`(`runner: Callable[[list[str]], object]`。戻り値オブジェクトは`.stdout`属性を持つ)
  - `build_artifact(component_dir: Path, build_root: Path, runner) -> Path`(戻り値: 生成したzipのパス)
  - `main(argv: list[str] | None = None) -> None`(CLIエントリポイント。引数: `component`)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_build_component.py`:

```python
import zipfile
from pathlib import Path

from build_component import build_artifact


def _write_component(component_dir: Path) -> None:
    component_dir.mkdir(parents=True)
    (component_dir / "pyproject.toml").write_text(
        '[project]\nname = "scd40-publisher"\nversion = "0.1.0"\n'
    )
    (component_dir / "recipe.yaml").write_text("RecipeFormatVersion: '2020-01-25'\n")
    src_dir = component_dir / "src" / "scd40_publisher"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "main.py").write_text("def main():\n    pass\n")


def test_build_artifact_creates_zip_with_expected_contents(tmp_path):
    component_dir = tmp_path / "components" / "scd40-publisher"
    _write_component(component_dir)
    build_root = tmp_path / "build"

    calls = []

    def fake_runner(command):
        calls.append(command)

        class _Result:
            stdout = "adafruit-blinka==8.0.0\n"

        return _Result()

    zip_path = build_artifact(component_dir, build_root, fake_runner)

    assert zip_path == build_root / "scd40-publisher" / "0.1.0" / "scd40-publisher.zip"
    assert zip_path.exists()
    assert calls == [
        [
            "uv",
            "export",
            "--project",
            str(component_dir),
            "--no-dev",
            "--format",
            "requirements-txt",
        ]
    ]

    with zipfile.ZipFile(zip_path) as zip_file:
        names = set(zip_file.namelist())
        assert "recipe.yaml" in names
        assert "requirements.txt" in names
        assert "src/scd40_publisher/main.py" in names
        assert zip_file.read("requirements.txt").decode() == "adafruit-blinka==8.0.0\n"
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_build_component.py -v`
Expected: FAIL(`build_component`モジュールが存在しない)

- [ ] **Step 3: 実装する**

`scripts/build_component.py`:

```python
from __future__ import annotations

import argparse
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path
from typing import Callable

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess]


def read_component_version(component_dir: Path) -> str:
    pyproject = tomllib.loads((component_dir / "pyproject.toml").read_text())
    return pyproject["project"]["version"]


def export_requirements(component_dir: Path, runner: CommandRunner) -> str:
    result = runner(
        [
            "uv",
            "export",
            "--project",
            str(component_dir),
            "--no-dev",
            "--format",
            "requirements-txt",
        ]
    )
    return result.stdout


def build_artifact(
    component_dir: Path,
    build_root: Path,
    runner: CommandRunner,
) -> Path:
    component_name = component_dir.name
    version = read_component_version(component_dir)
    requirements_text = export_requirements(component_dir, runner)

    stage_dir = build_root / component_name / version / "stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    shutil.copytree(component_dir / "src", stage_dir / "src")
    shutil.copy(component_dir / "recipe.yaml", stage_dir / "recipe.yaml")
    (stage_dir / "requirements.txt").write_text(requirements_text)

    zip_path = build_root / component_name / version / f"{component_name}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(stage_dir.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(stage_dir))

    return zip_path


def _default_runner(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", help="components/配下のコンポーネント名")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    component_dir = repo_root / "components" / args.component
    build_root = repo_root / "build"

    zip_path = build_artifact(component_dir, build_root, _default_runner)
    print(f"ビルド完了: {zip_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest tests/test_build_component.py -v`
Expected: PASS

- [ ] **Step 5: 実際にビルドスクリプトを動かして確認する**

Run: `uv run python scripts/build_component.py scd40-publisher`
Expected: `build/scd40-publisher/0.1.0/scd40-publisher.zip`が生成され、「ビルド完了: ...」と表示される

- [ ] **Step 6: コミットする**

```bash
git add scripts/build_component.py tests/test_build_component.py
git commit -m "コンポーネントのビルドスクリプトを実装"
```
