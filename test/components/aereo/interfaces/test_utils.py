"""Tests for aereo.interfaces utility helpers."""

from aereo.interfaces.utils import _prepare_config_for_instantiate


def test_prepare_config_for_instantiate_adds_partial_to_functions() -> None:
    """Function targets get _partial_: true when not explicitly set."""
    cfg = {
        "_target_": "aereo.builtins.write.write_geotiff",
        "driver": "GTiff",
    }
    prepared = _prepare_config_for_instantiate(cfg)
    assert prepared["_partial_"] is True


def test_prepare_config_for_instantiate_respects_explicit_false_for_classes() -> None:
    """Class targets keep _partial_: false when explicitly requested."""
    cfg = {
        "_target_": "aereo.executors.LocalExecutor",
        "_partial_": False,
    }
    prepared = _prepare_config_for_instantiate(cfg)
    assert prepared["_partial_"] is False


def test_prepare_config_for_instantiate_forces_partial_for_functions() -> None:
    """Function targets always become partials, even if _partial_ was False."""
    cfg = {
        "_target_": "aereo.asset_downloader.download_asset_safely",
        "_partial_": False,
    }
    prepared = _prepare_config_for_instantiate(cfg)
    assert prepared["_partial_"] is True


def test_prepare_config_for_instantiate_recurses_into_nested_dicts() -> None:
    """Nested function targets are processed independently."""
    cfg = {
        "_partial_": True,
        "_target_": "aereo.builtins.read.read_odc_stac",
        "reader": "sentinel2_l1c",
        "downloader": {
            "_target_": "aereo.asset_downloader.download_asset_safely",
            "_partial_": False,
        },
    }
    prepared = _prepare_config_for_instantiate(cfg)
    assert prepared["_partial_"] is True
    assert prepared["downloader"]["_partial_"] is True


def test_prepare_config_for_instantiate_recurses_into_lists() -> None:
    """Function targets inside lists are processed."""
    cfg = {
        "steps": [
            {"_target_": "aereo.builtins.processor.ndvi"},
            {
                "_target_": "aereo.asset_downloader.download_assets_safely",
                "_partial_": False,
            },
        ]
    }
    prepared = _prepare_config_for_instantiate(cfg)
    assert prepared["steps"][0]["_partial_"] is True
    assert prepared["steps"][1]["_partial_"] is True
