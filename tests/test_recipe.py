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
    lifecycle = recipe["Manifests"][0]["Lifecycle"]
    install = lifecycle["Install"]
    run = lifecycle["Run"]

    assert "requirements.txt" in install
    assert "scd40_publisher.main" in run

    # ZIPアーティファクトは {artifacts:decompressedPath}/<zip名> 配下に展開される。
    # {artifacts:path} は展開前のzipの場所を指すため、使ってはならない。
    assert (
        "{artifacts:decompressedPath}/scd40-publisher/requirements.txt" in install
    )
    assert "{artifacts:decompressedPath}/scd40-publisher/src" in run
    assert "{artifacts:path}" not in install
    assert "{artifacts:path}" not in run

    # レシピの設定は環境変数経由で main.py に渡される
    assert 'GG_TOPIC_NAME="{configuration:/topicName}"' in run
    assert (
        'GG_MEASUREMENT_INTERVAL_SECONDS="{configuration:/measurementIntervalSeconds}"'
        in run
    )
