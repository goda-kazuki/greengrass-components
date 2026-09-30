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
