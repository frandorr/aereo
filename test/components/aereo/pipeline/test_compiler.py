"""Tests for the processor compiler."""

from __future__ import annotations

import pytest

from aereo.pipeline.compiler import (
    _make_merge_wrapper,
    _make_parallel_wrapper,
    _make_sequential_wrapper,
    compile_processors,
)


def mask_clouds(ds: str) -> str:
    """Fake mask_clouds processor."""
    return f"masked({ds})"


def normalize(ds: str) -> str:
    """Fake normalize processor."""
    return f"normalized({ds})"


def compute_ndvi(ds: str) -> str:
    """Fake ndvi processor."""
    return f"ndvi({ds})"


def compute_ndwi(ds: str) -> str:
    """Fake ndwi processor."""
    return f"ndwi({ds})"


# ---------------------------------------------------------------------------
# Internal wrappers
# ---------------------------------------------------------------------------


def test_make_sequential_wrapper() -> None:
    """Sequential wrappers have the right name and parameter."""
    wrapper = _make_sequential_wrapper(mask_clouds, "step_0_mask", "read_scenes")
    assert wrapper.__name__ == "step_0_mask"
    result = wrapper("input_ds")
    assert result == "masked(input_ds)"


def test_make_parallel_wrapper() -> None:
    """Parallel wrappers have the right name and parameter."""
    wrapper = _make_parallel_wrapper(compute_ndvi, "parallel_0_ndvi", "read_scenes")
    assert wrapper.__name__ == "parallel_0_ndvi"
    result = wrapper("input_ds")
    assert result == "ndvi(input_ds)"


def test_make_merge_wrapper() -> None:
    """Merge wrappers collect branch outputs into a tuple."""
    wrapper = _make_merge_wrapper(
        ["parallel_0_ndvi", "parallel_0_ndwi"],
        "read_scenes",
        "merge_0",
    )
    assert wrapper.__name__ == "merge_0"
    result = wrapper("a", "b")
    assert result == ("a", "b")


# ---------------------------------------------------------------------------
# compile_processors
# ---------------------------------------------------------------------------


def test_compile_sequential_processors() -> None:
    """Sequential config produces step_N_name functions."""
    config = ["mask_clouds", "normalize"]
    plugin_functions = {
        "mask_clouds": mask_clouds,
        "normalize": normalize,
    }
    compiled = compile_processors(config, plugin_functions)

    assert "step_0_mask_clouds" in compiled
    assert "step_1_normalize" in compiled
    assert len(compiled) == 2

    # Verify chaining: step_1 depends on step_0's output name
    assert compiled["step_1_normalize"].__code__.co_varnames[0] == "step_0_mask_clouds"


def test_compile_parallel_processors() -> None:
    """Parallel config produces parallel_N_name + merge_N functions."""
    config = [{"parallel": ["compute_ndvi", "compute_ndwi"]}]
    plugin_functions = {
        "compute_ndvi": compute_ndvi,
        "compute_ndwi": compute_ndwi,
    }
    compiled = compile_processors(config, plugin_functions)

    assert "parallel_0_compute_ndvi" in compiled
    assert "parallel_0_compute_ndwi" in compiled
    assert "merge_0" in compiled
    assert len(compiled) == 3

    # Both parallel branches depend on the initial input
    assert compiled["parallel_0_compute_ndvi"].__code__.co_varnames[0] == "read_scenes"
    assert compiled["parallel_0_compute_ndwi"].__code__.co_varnames[0] == "read_scenes"

    # Merge depends on both parallel branches
    merge_params = compiled["merge_0"].__code__.co_varnames[
        : compiled["merge_0"].__code__.co_argcount
    ]
    assert list(merge_params) == ["parallel_0_compute_ndvi", "parallel_0_compute_ndwi"]


def test_compile_mixed_sequential_and_parallel() -> None:
    """A pipeline with both sequential and parallel steps."""
    config = [
        "mask_clouds",
        {"parallel": ["compute_ndvi", "compute_ndwi"]},
        "normalize",
    ]
    plugin_functions = {
        "mask_clouds": mask_clouds,
        "compute_ndvi": compute_ndvi,
        "compute_ndwi": compute_ndwi,
        "normalize": normalize,
    }
    compiled = compile_processors(config, plugin_functions)

    assert "step_0_mask_clouds" in compiled
    assert "parallel_1_compute_ndvi" in compiled
    assert "parallel_1_compute_ndwi" in compiled
    assert "merge_1" in compiled
    assert "step_2_normalize" in compiled

    # step_2_normalize should depend on merge_1
    assert compiled["step_2_normalize"].__code__.co_varnames[0] == "merge_1"


def test_compile_with_dict_params() -> None:
    """Processor config as dict extracts the processor name correctly."""
    config = [{"mask_clouds": {"threshold": 0.5}}]
    plugin_functions = {"mask_clouds": mask_clouds}
    compiled = compile_processors(config, plugin_functions)

    assert "step_0_mask_clouds" in compiled


def test_compile_empty_config() -> None:
    """Empty config returns an empty dict."""
    compiled = compile_processors([], {})
    assert compiled == {}


def test_compile_unknown_processor_raises() -> None:
    """Referencing an unknown processor raises ValueError."""
    config = ["unknown_processor"]
    plugin_functions = {"mask_clouds": mask_clouds}

    with pytest.raises(ValueError, match="Processor 'unknown_processor' not found"):
        compile_processors(config, plugin_functions)


def test_compile_unknown_in_parallel_raises() -> None:
    """Referencing an unknown processor inside a parallel block raises ValueError."""
    config = [{"parallel": ["compute_ndvi", "missing"]}]
    plugin_functions = {"compute_ndvi": compute_ndvi}

    with pytest.raises(ValueError, match="Processor 'missing' not found"):
        compile_processors(config, plugin_functions)


def test_compile_functions_are_callable() -> None:
    """Compiled functions can be invoked with the expected inputs."""
    config = ["mask_clouds", {"parallel": ["compute_ndvi", "compute_ndwi"]}]
    plugin_functions = {
        "mask_clouds": mask_clouds,
        "compute_ndvi": compute_ndvi,
        "compute_ndwi": compute_ndwi,
    }
    compiled = compile_processors(config, plugin_functions)

    # Run the sequential step
    masked = compiled["step_0_mask_clouds"]("raw_ds")
    assert masked == "masked(raw_ds)"

    # Run parallel branches
    ndvi = compiled["parallel_1_compute_ndvi"](masked)
    ndwi = compiled["parallel_1_compute_ndwi"](masked)
    assert ndvi == "ndvi(masked(raw_ds))"
    assert ndwi == "ndwi(masked(raw_ds))"

    # Run merge
    merged = compiled["merge_1"](ndvi, ndwi)
    assert merged == ("ndvi(masked(raw_ds))", "ndwi(masked(raw_ds))")
