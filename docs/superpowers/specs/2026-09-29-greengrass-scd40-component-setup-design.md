# Greengrassコンポーネント管理リポジトリ セットアップ 設計書

- 日付: 2026-09-29
- 対象リポジトリ: greengrass-components

## 背景・目的

手元のRaspberry Piに既にAWS IoT Greengrassをセットアップ済みであり、そのGreengrassデバイスに対してこのリポジトリで開発したコンポーネントをデプロイしていく。本リポジトリの役割は「開発したGreengrassコンポーネントの管理(開発・ビルド・デプロイ)」である。

言語はPython、パッケージ管理はuvを使用する。

第一弾のコンポーネントとして、Raspberry Piに接続済みのSCD40センサー(CO2・温度・湿度が取得可能)の値を定期的にAWS IoT Coreへパブリッシュするコンポーネントを実装する。ただし将来的に複数のコンポーネントを本リポジトリで管理していく前提のため、モノレポ構成とする。

## スコープ

### 今回実施する範囲

- リポジトリの構成整備(uvワークスペース、モノレポ構成)
- SCD40センサー値をAWS IoT Coreへパブリッシュするコンポーネント(`scd40-publisher`)の実装
- コンポーネントのビルドスクリプト・デプロイスクリプトの整備
- 開発・デプロイ手順のドキュメント整備

### 今回実施しない範囲(スコープ外)

- AWS側リソースの作成(アーティファクト格納用S3バケット、IoT Thing、IoT Thing Group、IAMロール/ポリシーなど)。これらは別途ユーザーが用意する前提とし、必要なリソースと前提条件をドキュメントに明記するのみとする。
- CI(GitHub Actionsなどによるlint/テストの自動実行)の導入。現時点ではローカル実行のみで十分とする。

## 全体アーキテクチャ

### リポジトリレイアウト

```
greengrass-components/
├── pyproject.toml          # uvワークスペースルート(ワークスペースメンバー定義)
├── uv.lock
├── README.md
├── .python-version
├── components/
│   └── scd40-publisher/
│       ├── pyproject.toml          # コンポーネント個別の依存関係
│       ├── recipe.yaml             # Greengrassレシピ(テンプレート、バージョンはビルド時に注入)
│       ├── src/
│       │   └── scd40_publisher/
│       │       ├── __init__.py
│       │       ├── main.py         # エントリポイント(定期実行ループ)
│       │       ├── sensor.py       # SCD40読み取りラッパー
│       │       └── publisher.py    # IoT Core送信ラッパー(Greengrass IPC経由)
│       └── tests/
│           ├── test_sensor.py
│           └── test_publisher.py
├── scripts/
│   ├── build_component.py   # 指定コンポーネントのビルド(zipアーティファクト作成)
│   └── deploy_component.py  # S3アップロード・コンポーネント登録・デプロイ作成
└── docs/
    └── deploy.md            # 前提AWSリソースとデプロイ手順
```

新しいコンポーネントを追加する際は `components/` 配下にディレクトリを1つ追加し、ルートのuvワークスペースメンバーに加えるだけで済む構成とする。

### 依存関係管理の方針(uvの使用範囲)

uvはリポジトリ内の開発体験(依存関係解決・ロックファイル・モノレポのワークスペース管理・テスト実行)に一貫して使用する。一方、Raspberry Pi(Greengrassデバイス)側にはuvをインストールせず、Greengrassが元々前提とする `python3` / `pip3` のみで動作させる。

理由: デバイス側の依存を最小限にし、デプロイ時にuvのインストールやuv自体のネットワーク到達性に依存させないことで運用をシンプルかつ安定させるため。

具体的には、ビルドスクリプトが `uv export --no-dev --format requirements-txt` でロック済みの依存関係を `requirements.txt` として書き出し、Greengrassレシピの `Install` ライフサイクルで通常の `pip3 install -r requirements.txt` を実行する。

## コンポーネント設計: scd40-publisher

### センサー接続

- ライブラリ: `adafruit-circuitpython-scd4x`(importは `adafruit_scd4x`)、`adafruit-blinka`(`board`, `busio`)を使用したI2C接続
- 実装済みの動作確認スクリプト(ユーザー提供)をベースに `sensor.py` へラップする

```python
import board
import busio
from adafruit_scd4x import SCD4X

i2c = busio.I2C(board.SCL, board.SDA)
scd4x = SCD4X(i2c)
scd4x.start_periodic_measurement()
# scd4x.data_ready / scd4x.CO2 / scd4x.temperature / scd4x.relative_humidity
```

### 実行フロー

1. `main.py` 起動時に `sensor.py` のSCD40リーダーを初期化する
2. 定期実行ループ(デフォルト測定間隔: 60秒。環境変数/レシピパラメータで変更可能)でCO2・温度・湿度を取得する
3. 取得値を `publisher.py` がGreengrass IPC(`awsiotsdk` の `greengrasscoreipc` モジュール、operation: `PublishToIoTCore`)経由でAWS IoT Coreへパブリッシュする

### MQTTトピック・ペイロード

- トピック: `greengrass-components/scd40-publisher/<thingName>/telemetry`
- ペイロード(JSON):

```json
{
  "co2_ppm": 812,
  "temperature_c": 24.3,
  "humidity_percent": 45.2,
  "timestamp": "2026-09-29T12:00:00Z"
}
```

- トピック名・測定間隔はGreengrassレシピの `ComponentConfiguration` でパラメータ化し、デプロイ時にオーバーライド可能にする

### エラーハンドリング

- センサー読み取り失敗(I2Cタイムアウト等): ログに記録し、プロセスは継続。次の測定サイクルで再試行する
- AWS IoT Coreへの送信失敗: ログに記録してそのデータはドロップする(ローカルキューは持たない。シンプルさを優先)
- 起動時にI2Cデバイスが検出できない場合: エラーログを出してプロセスを終了し、再起動はGreengrassのライフサイクル管理に委ねる

### テスト方針

- `pytest` + `unittest.mock` を使用し、実機依存部分(I2C/`board`/`busio`、Greengrass IPCクライアント)をモック化した単体テストを用意する
- `sensor.py` はI2C初期化処理を薄く分離し、テスト時にモックへ差し替えやすい構造にする
- `publisher.py` もIPCクライアントを注入可能にし、実際のIPC接続なしにパブリッシュ処理のロジック(ペイロード整形など)を検証できるようにする
- 本リポジトリの開発機(Raspberry Pi以外の環境)でも `uv run pytest` がハードウェアなしで実行できることを確認する

## ビルド・デプロイツーリング

### `scripts/build_component.py`

- 使い方: `uv run python scripts/build_component.py <component名>`
- 処理内容:
  1. 対象コンポーネントディレクトリで `uv export --no-dev --format requirements-txt` を実行し `requirements.txt` を生成
  2. `src/`、生成した `requirements.txt`、`recipe.yaml` を `build/<component>/<version>/` にまとめ、zipアーティファクトを作成
  3. バージョン番号は `pyproject.toml` の `version` フィールドから取得する

### `scripts/deploy_component.py`

- 使い方: `uv run python scripts/deploy_component.py <component名> --version <version>`
- 処理内容:
  1. `boto3` を用いて、ビルド済みzipをS3(バケット名は環境変数 `GG_ARTIFACT_BUCKET` で指定)へアップロード
  2. `recipe.yaml` のS3 URI・バージョンを注入し、`aws greengrassv2 create-component-version` 相当の呼び出しでコンポーネントバージョンを登録
  3. `aws greengrassv2 create-deployment` 相当の呼び出しで対象のThing/Thing Groupへデプロイを作成
- AWS認証情報は環境変数 `AWS_PROFILE` で指定されたプロファイルを利用する(AWS CLIの設定済みプロファイルを前提とする)

### `docs/deploy.md`

- 前提として必要なAWSリソース(アーティファクト格納用S3バケット、対象のIoT Thing / Thing Group、Greengrassコンポーネントが `PublishToIoTCore` を行うために必要なIAMポリシー/認可設定)を明記する
- これらのリソース作成は本リポジトリのスコープ外であり、ユーザーが別途用意する前提であることを明記する
- ビルド・デプロイスクリプトの実行手順、必要な環境変数(`GG_ARTIFACT_BUCKET`, `AWS_PROFILE` など)を記載する

## 非対応・今後の検討事項

- CI(lint/テスト自動化)は今回導入しない。将来必要になった時点で別途検討する
- AWSリソースのIaC化(CloudFormation/CDK等によるS3バケット・IoT Thing Group等の自動作成)は今回のスコープ外。将来複数コンポーネント・複数デバイスを管理する規模になった際に検討する
- ローカルキューイングやリトライの高度化(送信失敗時のバッファリング等)は今回は行わない
