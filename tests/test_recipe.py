from fnmatch import fnmatchcase
from pathlib import Path

import yaml

RECIPE_PATH = (
    Path(__file__).resolve().parents[1]
    / "components"
    / "scd40-publisher"
    / "recipe.yaml"
)

COMPONENT_NAME = "com.example.Scd40Publisher"


def load_recipe() -> dict:
    return yaml.safe_load(RECIPE_PATH.read_text())


def test_recipe_default_configuration_values():
    recipe = load_recipe()

    assert recipe["ComponentName"] == COMPONENT_NAME
    default_config = recipe["ComponentConfiguration"]["DefaultConfiguration"]

    assert default_config["measurementIntervalSeconds"] == "60"
    topic_name = default_config["topicName"]
    assert "{iot:thingName}" in topic_name
    assert topic_name.startswith("greengrass-components/scd40-publisher/")


def test_recipe_grants_mqttproxy_publish_access_to_default_topic():
    # アクセス制御ポリシーが無いと、実機では全publishが UnauthorizedError で拒否される
    default_config = load_recipe()["ComponentConfiguration"]["DefaultConfiguration"]
    mqttproxy = default_config["accessControl"]["aws.greengrass.ipc.mqttproxy"]

    policies = [
        policy
        for policy_id, policy in mqttproxy.items()
        if policy_id.startswith(f"{COMPONENT_NAME}:")
    ]
    assert policies

    default_topic = default_config["topicName"].replace("{iot:thingName}", "thing-1")
    for policy in policies:
        assert "aws.greengrass#PublishToIoTCore" in policy["operations"]
    assert any(
        fnmatchcase(default_topic, resource)
        for policy in policies
        for resource in policy["resources"]
    )


def test_recipe_lifecycle_installs_requirements_and_runs_main():
    recipe = load_recipe()
    manifest = recipe["Manifests"][0]
    lifecycle = manifest["Lifecycle"]
    install = lifecycle["Install"]
    run = lifecycle["Run"]

    # ZIPアーティファクトは {artifacts:decompressedPath}/<zip名> 配下に展開される。
    # {artifacts:path} は展開前のzipの場所を指すため、使ってはならない。
    assert manifest["Artifacts"][0]["Unarchive"] == "ZIP"
    assert (
        install["Script"]
        == "pip3 install --user -r "
        "{artifacts:decompressedPath}/scd40-publisher/requirements.txt"
    )
    # コールドスタートのpip installはデフォルトの120秒では足りないことがある
    assert install["Timeout"] == 600
    assert "scd40_publisher.main" in run
    assert 'PYTHONPATH="{artifacts:decompressedPath}/scd40-publisher/src"' in run
    assert "{artifacts:path}" not in install["Script"]
    assert "{artifacts:path}" not in run

    # レシピの設定は環境変数経由で main.py に渡される
    assert 'GG_TOPIC_NAME="{configuration:/topicName}"' in run
    assert (
        'GG_MEASUREMENT_INTERVAL_SECONDS="{configuration:/measurementIntervalSeconds}"'
        in run
    )
