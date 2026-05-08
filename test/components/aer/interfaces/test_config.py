from pathlib import Path

import pytest
from aer.interfaces.core import AerProfile


def test_from_yaml_string_loads_profiles():
    yaml_text = """
    profiles:
      - name: p1
        resolution: 100.0
      - name: p2
        resolution: 200.0
    """
    profiles = AerProfile.from_yaml_string(yaml_text)
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
        AerProfile.from_yaml_string(yaml_text)


def test_from_json_loads_profiles(tmp_path: Path):
    json_file = tmp_path / "profiles.json"
    json_file.write_text('{"profiles": [{"name": "j1", "resolution": 50}]}')
    profiles = AerProfile.from_json(json_file)
    assert len(profiles) == 1
    assert profiles[0].name == "j1"


def test_from_config_dir_mixed_formats(tmp_path: Path):
    (tmp_path / "a.yaml").write_text("profiles:\n  - name: a\n    resolution: 1\n")
    (tmp_path / "b.json").write_text('{"profiles": [{"name": "b", "resolution": 2}]}')
    profiles = AerProfile.from_config_dir(tmp_path)
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
        AerProfile.from_yaml_string("profiles: []")


def test_from_raw_missing_profiles_key():
    with pytest.raises(ValueError, match="Config must be a dict with a 'profiles' key"):
        AerProfile._from_raw({})


def test_from_raw_non_dict():
    with pytest.raises(ValueError, match="Config must be a dict with a 'profiles' key"):
        AerProfile._from_raw("not a dict")  # pyright: ignore[reportArgumentType]
