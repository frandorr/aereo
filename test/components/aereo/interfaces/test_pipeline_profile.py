from pathlib import Path

import pytest
from aereo.interfaces import PipelineProfile
from pydantic import ValidationError


def test_pipeline_profile_construction():
    """Basic construction with all expected fields."""
    profile = PipelineProfile(
        name="s3_olci",
        resolution=300.0,
        collections={"S3OLCI": ["Oa01", "Oa02"]},
        plugin_hints={"search": "earthaccess", "read": "satpy"},
        search_params={"cloud_cover": 20},
        download_params={"timeout": 30},
        read_params={"reader": "olci"},
        reproject_params={"resampling": "bilinear"},
        write_params={"driver": "COG"},
        pre_processors=["mask_clouds"],
        post_processors=[{"parallel": ["compute_ndvi", "compute_ndwi"]}, "normalize"],
    )
    assert profile.name == "s3_olci"
    assert profile.resolution == 300.0
    assert profile.collections == {"S3OLCI": ["Oa01", "Oa02"]}
    assert profile.plugin_hints == {"search": "earthaccess", "read": "satpy"}
    assert profile.search_params == {"cloud_cover": 20}
    assert profile.download_params == {"timeout": 30}
    assert profile.read_params == {"reader": "olci"}
    assert profile.reproject_params == {"resampling": "bilinear"}
    assert profile.write_params == {"driver": "COG"}
    assert profile.pre_processors == ["mask_clouds"]
    assert profile.post_processors == [
        {"parallel": ["compute_ndvi", "compute_ndwi"]},
        "normalize",
    ]


def test_pipeline_profile_defaults():
    """Defaults are empty containers when omitted."""
    profile = PipelineProfile(name="minimal", resolution=100.0)
    assert profile.collections == {}
    assert profile.plugin_hints == {}
    assert profile.search_params == {}
    assert profile.download_params == {}
    assert profile.read_params == {}
    assert profile.reproject_params == {}
    assert profile.write_params == {}
    assert profile.pre_processors == []
    assert profile.post_processors == []


def test_pipeline_profile_frozen():
    """Frozen model rejects mutation."""
    profile = PipelineProfile(name="test", resolution=100.0)
    with pytest.raises(ValidationError):
        profile.name = "other"  # type: ignore[misc]


def test_pipeline_profile_extra_forbidden():
    """Extra fields are rejected."""
    with pytest.raises(ValidationError):
        PipelineProfile(name="test", resolution=100.0, unknown_field=42)  # type: ignore[call-arg]


def test_pipeline_profile_from_yaml_string():
    """Load multiple profiles from a YAML string."""
    yaml_text = """
    profiles:
      - name: test
        resolution: 100
        collections:
          S3OLCI: [Oa01]
        pre_processors:
          - mask_clouds
        post_processors:
          - parallel:
              - ndvi
    """
    profiles = PipelineProfile.from_yaml_string(yaml_text)
    assert len(profiles) == 1
    assert profiles[0].name == "test"
    assert profiles[0].resolution == 100.0
    assert profiles[0].pre_processors == ["mask_clouds"]
    assert profiles[0].post_processors == [{"parallel": ["ndvi"]}]


def test_pipeline_profile_from_yaml_string_multiple():
    """Load multiple profiles from a YAML string."""
    yaml_text = """
    profiles:
      - name: p1
        resolution: 100.0
      - name: p2
        resolution: 200.0
        plugin_hints:
          search: earthaccess
    """
    profiles = PipelineProfile.from_yaml_string(yaml_text)
    assert len(profiles) == 2
    assert profiles[0].name == "p1"
    assert profiles[1].resolution == 200.0
    assert profiles[1].plugin_hints == {"search": "earthaccess"}


def test_pipeline_profile_from_yaml_detects_duplicates():
    """Duplicate names raise ValueError."""
    yaml_text = """
    profiles:
      - name: p1
        resolution: 100.0
      - name: p1
        resolution: 200.0
    """
    with pytest.raises(ValueError, match="Duplicate profile name"):
        PipelineProfile.from_yaml_string(yaml_text)


def test_pipeline_profile_from_json(tmp_path: Path) -> None:
    """Load profiles from a JSON file."""
    json_file = tmp_path / "profiles.json"
    json_file.write_text(
        '{"profiles": [{"name": "j1", "resolution": 50, "pre_processors": ["norm"]}]}'
    )
    profiles = PipelineProfile.from_json(json_file)
    assert len(profiles) == 1
    assert profiles[0].name == "j1"
    assert profiles[0].pre_processors == ["norm"]


def test_pipeline_profile_from_config_dir_mixed_formats(tmp_path: Path) -> None:
    """Load from a directory with mixed YAML and JSON files."""
    (tmp_path / "a.yaml").write_text("profiles:\n  - name: a\n    resolution: 1\n")
    (tmp_path / "b.json").write_text('{"profiles": [{"name": "b", "resolution": 2}]}')
    profiles = PipelineProfile.from_config_dir(tmp_path)
    assert {p.name for p in profiles} == {"a", "b"}


def test_pipeline_profile_from_raw_missing_profiles_key():
    """_from_raw requires a 'profiles' key."""
    with pytest.raises(ValueError, match="Config must be a dict with a 'profiles' key"):
        PipelineProfile._from_raw({})


def test_pipeline_profile_from_raw_non_dict():
    """_from_raw rejects non-dict input."""
    with pytest.raises(ValueError, match="Config must be a dict with a 'profiles' key"):
        PipelineProfile._from_raw("not a dict")  # type: ignore[arg-type]


def test_pipeline_profile_from_yaml_missing_pyyaml(monkeypatch) -> None:
    """ImportError when PyYAML is missing."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="YAML support requires PyYAML"):
        PipelineProfile.from_yaml_string("profiles: []")


def test_pipeline_profile_pickle_roundtrip():
    """PipelineProfile round-trips through pickle."""
    import pickle

    profile = PipelineProfile(
        name="pickle_test",
        resolution=250.0,
        collections={"S2": ["B04", "B08"]},
        pre_processors=["mask_clouds"],
        post_processors=[{"parallel": ["ndvi", "ndwi"]}, "normalize"],
    )
    serialized = pickle.dumps(profile)
    restored = pickle.loads(serialized)
    assert restored == profile
    assert restored.name == "pickle_test"
    assert restored.post_processors == [{"parallel": ["ndvi", "ndwi"]}, "normalize"]


def test_pipeline_profile_repr():
    """String representation is helpful."""
    profile = PipelineProfile(name="repr_test", resolution=10.0)
    assert "repr_test" in repr(profile)
    assert "10.0" in repr(profile)
