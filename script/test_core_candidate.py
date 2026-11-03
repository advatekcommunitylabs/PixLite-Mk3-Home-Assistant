"""Run the exported sensor integration through Home Assistant's custom loader."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from prepare_core import ROOT, prepare


def main() -> None:
    """Build an isolated installation for the sensor-only contribution candidate."""
    with tempfile.TemporaryDirectory(prefix="pixlite-core-") as directory:
        root = Path(directory)
        exported = root / "export"
        prepare(exported, "0.1.0", draft=True)
        component = root / "custom_components/advatek_pixlite"
        shutil.copytree(
            exported / "homeassistant/components/advatek_pixlite", component
        )
        manifest_path = component / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.update(version="0.0.0", requirements=[], quality_scale="custom")
        manifest_path.write_text(json.dumps(manifest))
        (component / "translations").mkdir()
        shutil.copyfile(component / "strings.json", component / "translations/en.json")
        tests = root / "tests/components/advatek_pixlite"
        tests.mkdir(parents=True)
        shutil.copyfile(
            ROOT / "tests/components/conftest.py", tests.parent / "conftest.py"
        )
        for source in (exported / "tests/components/advatek_pixlite").glob("*.py"):
            text = (
                source.read_text()
                .replace(
                    "homeassistant.components.advatek_pixlite",
                    "custom_components.advatek_pixlite",
                )
                .replace(
                    "from tests.common import",
                    "from pytest_homeassistant_custom_component.common import",
                )
            )
            (tests / source.name).write_text(text)
        shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"], cwd=root, check=False
        )
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
