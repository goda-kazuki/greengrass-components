import zipfile
from pathlib import Path

import pytest

from build_component import build_artifact, main


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
    pycache_dir = src_dir / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "x.pyc").write_bytes(b"\x00")


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
            "--no-emit-project",
            "--no-header",
            "--format",
            "requirements-txt",
        ]
    ]

    with zipfile.ZipFile(zip_path) as zip_file:
        names = set(zip_file.namelist())
        assert "recipe.yaml" in names
        assert "requirements.txt" in names
        assert "src/scd40_publisher/main.py" in names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert zip_file.read("requirements.txt").decode() == "adafruit-blinka==8.0.0\n"


def test_main_exits_with_message_when_component_is_missing():
    with pytest.raises(SystemExit) as exc_info:
        main(["no-such-component"])

    assert exc_info.value.code
    assert "no-such-component" in str(exc_info.value.code)
