"""Export the sensor integration and its tests into Home Assistant's tree layout."""

import argparse
import json
from pathlib import Path
import shutil
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def prepare(output: Path, client_version: str, *, draft: bool) -> None:
    """Write a new contribution tree without changing an existing checkout."""
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    if not draft:
        url = f"https://pypi.org/pypi/advatek-pixlite-client/{client_version}/json"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                release = json.load(response)
        except (urllib.error.URLError, ValueError) as err:
            raise ValueError(
                "The pinned client release could not be verified on PyPI"
            ) from err
        if not any(file["packagetype"] == "sdist" for file in release["urls"]):
            raise ValueError("The client release must include a source distribution")
    component = output / "homeassistant/components/advatek_pixlite"
    component.mkdir(parents=True)
    for source in (ROOT / "core/advatek_pixlite").iterdir():
        if source.suffix in {".py", ".yaml"}:
            shutil.copyfile(source, component / source.name)
    custom = ROOT / "custom_components/advatek_pixlite"
    for filename in ("sensor.py", "entity.py"):
        shutil.copyfile(custom / filename, component / filename)
    manifest = (ROOT / "core/advatek_pixlite/manifest.json.in").read_text()
    (component / "manifest.json").write_text(
        manifest.replace("@CLIENT_VERSION@", client_version)
    )
    strings = json.loads((custom / "strings.json").read_text())
    strings["config"]["step"] = {"user": strings["config"]["step"]["user"]}
    strings["config"]["abort"] = {
        "already_configured": strings["config"]["abort"]["already_configured"]
    }
    strings["entity"] = {"sensor": strings["entity"]["sensor"]}
    strings["selector"] = {
        "user_type": {"options": {"admin": "Administrator", "oper": "Operator"}}
    }
    (component / "strings.json").write_text(json.dumps(strings, indent=2) + "\n")
    tests = output / "tests/components/advatek_pixlite"
    tests.mkdir(parents=True)
    (tests / "__init__.py").write_text('"""Tests for the PixLite integration."""\n')
    for source in (ROOT / "core/tests").glob("*.py"):
        (tests / source.name).write_text(
            source.read_text().replace(
                "custom_components.advatek_pixlite",
                "homeassistant.components.advatek_pixlite",
            )
        )
    (output / "READINESS.md").write_text(
        "# Contribution preparation\n\n"
        "This tree is a draft for human review. It does not assert Bronze compliance, "
        "hardware verification, license approval, branding approval, or upstream acceptance. "
        "Run the target Core checkout's setup, translation generation, hassfest, tests and "
        "full hooks. Complete every Bronze rule and review the actual dependency release "
        "before submitting. Do not copy this file into Home Assistant Core.\n"
    )


def main() -> None:
    """Read the destination and proposed dependency release from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--client-version", required=True)
    parser.add_argument("--draft", action="store_true")
    arguments = parser.parse_args()
    try:
        prepare(arguments.output, arguments.client_version, draft=arguments.draft)
    except ValueError as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()
