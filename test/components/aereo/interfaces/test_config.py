from pathlib import Path

import pytest
from aereo.interfaces.core import AereoProfile


def test_from_yaml_example_loads_profiles():
    """Verify the checked-in examples/data/profiles.yaml loads correctly."""
    yaml_path = Path(__file__).parents[4] / "examples" / "data" / "profiles.yaml"
    profiles = AereoProfile.from_yaml(yaml_path)
    assert len(profiles) == 5
    names = {p.name for p in profiles}
    assert names == {"goes_c02", "s2_rgb", "viirs_i1", "olci_o08", "geotessera"}
    # Verify ImportString resolution works from YAML too
    assert profiles[2].downloader is not None


def test_from_yaml_string_loads_profiles():
    yaml_text = """
    profiles:
      - name: p1
        resolution: 100.0
      - name: p2
        resolution: 200.0
    """
    profiles = AereoProfile.from_yaml_string(yaml_text)
    assert len(profiles) == 2
    assert profiles[0].name == "p1"
    assert profiles[1].resolution == 200.0


def test_from_yaml_detects_duplicate_names():
    yaml_text = """
    profiles:
      - name: p1
        resolution: 100.0
      - name: p1
        resolution: 200.0
    """
    with pytest.raises(ValueError, match="Duplicate profile name"):
        AereoProfile.from_yaml_string(yaml_text)


def test_from_json_loads_profiles(tmp_path: Path):
    json_file = tmp_path / "profiles.json"
    json_file.write_text('{"profiles": [{"name": "j1", "resolution": 50}]}')
    profiles = AereoProfile.from_json(json_file)
    assert len(profiles) == 1
    assert profiles[0].name == "j1"


def test_from_config_dir_mixed_formats(tmp_path: Path):
    (tmp_path / "a.yaml").write_text("profiles:\n  - name: a\n    resolution: 1\n")
    (tmp_path / "b.json").write_text('{"profiles": [{"name": "b", "resolution": 2}]}')
    profiles = AereoProfile.from_config_dir(tmp_path)
    assert {p.name for p in profiles} == {"a", "b"}


def test_from_yaml_missing_pyyraises_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="YAML support requires PyYAML"):
        AereoProfile.from_yaml_string("profiles: []")


def test_from_raw_missing_profiles_key():
    with pytest.raises(ValueError, match="Config must be a dict with a 'profiles' key"):
        AereoProfile._from_raw({})


def test_from_raw_non_dict():
    with pytest.raises(ValueError, match="Config must be a dict with a 'profiles' key"):
        AereoProfile._from_raw("not a dict")  # pyright: ignore[reportArgumentType]
