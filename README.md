# greengrass-components

Raspberry Pi上のAWS IoT Greengrassデバイスにデプロイする、自作コンポーネントの開発・ビルドを管理するモノレポです。

## セットアップ

```bash
uv sync
uv run pytest
```

## コンポーネント一覧

- `components/scd40-publisher`: SCD40センサー(CO2・温度・湿度)の値をAWS IoT Coreへ定期送信するコンポーネント

## コンポーネントの追加

1. `components/<name>/`ディレクトリを作成する(`pyproject.toml`・`recipe.yaml`・`src/`・`tests/`を置く)。
2. ルートの`pyproject.toml`の`dependencies`に`<name>`を追加し、`[tool.uv.sources]`に`<name> = { workspace = true }`を追記する(または`uv sync --all-packages`を実行する)。

## ビルド

```bash
uv run python scripts/build_component.py scd40-publisher
```

`build/scd40-publisher/<version>/scd40-publisher.zip`が生成されます。

## デプロイ

未整備です(アーティファクト格納用のS3バケットを用意した後に追加します)。

### 実機での初回デプロイ時に確認すること

- [ ] レシピの`topicName`に含まれる入れ子の`{iot:thingName}`がGreengrassによって解決されること
- [ ] Raspberry Pi OS Bookwormでは、PEP 668(externally-managed-environment)により`pip3 install --user`が失敗することがある。その場合は`--break-system-packages`を付けるか、`--system-site-packages`付きで作成したvenvを使う
- [ ] BlinkaのRaspberry Piピン対応には`RPi.GPIO`または`lgpio`が必要で、requirements.txtではなくaptで入れる(`python3-rpi.gpio` / `python3-rpi-lgpio`)
- [ ] エクスポートしたrequirements.txtはハッシュ固定のため、pipはハッシュ検証モードで動く。aarch64向けのwheelが提供されていることを確認する
- [ ] デバイスの`python3`のバージョンが、このプロジェクトのPython 3.13と合っているか確認する
- [ ] レシピの`ComponentVersion`とアーティファクトのURIは、デプロイ処理を整備するまでは仮の値である
- [ ] `topicName`を上書きする場合は、`accessControl`の`resources`も合わせて更新する
