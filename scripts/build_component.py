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
            "--no-emit-project",
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

    shutil.copytree(
        component_dir / "src",
        stage_dir / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
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
