"""Tests for the downloader domain model (registry, value objects, URI utilities)."""

import pytest
from pathlib import Path

from aer.downloader import (
    DownloadMethod,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    s3_uri_to_https,
)


# ---------------------------------------------------------------------------
# DownloadRequest
# ---------------------------------------------------------------------------


class TestDownloadRequest:
    def test_minimal_request(self):
        req = DownloadRequest(uri="https://example.com/file.hdf", dest_dir="/tmp/dl")
        assert req.uri == "https://example.com/file.hdf"
        assert req.dest_dir == Path("/tmp/dl")
        assert req.filename is None
        assert req.headers == {}
        assert req.options == {}

    def test_full_request(self):
        req = DownloadRequest(
            uri="s3://bucket/key/file.nc",
            dest_dir="/data/out",
            filename="custom.nc",
            headers={"Authorization": "Bearer tok123"},
            options={"max-tries": "5"},
        )
        assert req.filename == "custom.nc"
        assert req.headers["Authorization"] == "Bearer tok123"
        assert req.options["max-tries"] == "5"

    def test_dest_dir_converted_to_path(self):
        req = DownloadRequest(uri="https://x.com/f", dest_dir="/tmp/x")
        assert isinstance(req.dest_dir, Path)

    def test_request_is_frozen(self):
        req = DownloadRequest(uri="https://x.com/f", dest_dir="/tmp/x")
        with pytest.raises(AttributeError):
            req.uri = "new"


# ---------------------------------------------------------------------------
# DownloadResult
# ---------------------------------------------------------------------------


class TestDownloadResult:
    def test_complete_result(self):
        req = DownloadRequest(uri="https://x.com/f", dest_dir="/tmp/x")
        res = DownloadResult(
            request=req,
            status=DownloadStatus.COMPLETE,
            path=Path("/tmp/x/f"),
            bytes_downloaded=1024,
        )
        assert res.status == DownloadStatus.COMPLETE
        assert res.path == Path("/tmp/x/f")
        assert res.error is None
        assert res.bytes_downloaded == 1024

    def test_failed_result(self):
        req = DownloadRequest(uri="https://x.com/f", dest_dir="/tmp/x")
        res = DownloadResult(
            request=req,
            status=DownloadStatus.FAILED,
            error="Connection refused",
        )
        assert res.status == DownloadStatus.FAILED
        assert res.path is None
        assert res.error == "Connection refused"
        assert res.bytes_downloaded == 0

    def test_skipped_result(self):
        req = DownloadRequest(uri="https://x.com/f", dest_dir="/tmp/x")
        res = DownloadResult(request=req, status=DownloadStatus.SKIPPED)
        assert res.status == DownloadStatus.SKIPPED


# ---------------------------------------------------------------------------
# s3_uri_to_https
# ---------------------------------------------------------------------------


class TestS3UriToHttps:
    def test_passthrough_https(self):
        url = "https://example.com/data/file.hdf"
        assert s3_uri_to_https(url) == url

    def test_passthrough_http(self):
        url = "http://example.com/data/file.hdf"
        assert s3_uri_to_https(url) == url

    def test_s3_with_custom_endpoint(self):
        endpoints = {"prod-lads": "https://ladsweb.example.com/data"}
        result = s3_uri_to_https(
            "s3://prod-lads/MOD021KM/file.hdf", endpoint_map=endpoints
        )
        assert result == "https://ladsweb.example.com/data/MOD021KM/file.hdf"

    def test_s3_fallback_aws_virtual_hosted(self):
        result = s3_uri_to_https("s3://my-public-bucket/path/to/file.nc")
        assert result == "https://my-public-bucket.s3.amazonaws.com/path/to/file.nc"

    def test_s3_no_endpoints_provided(self):
        result = s3_uri_to_https("s3://bucket/key.hdf")
        assert result == "https://bucket.s3.amazonaws.com/key.hdf"

    def test_s3_url_encodes_special_chars(self):
        result = s3_uri_to_https("s3://bucket/path/file name (1).hdf")
        assert "file%20name%20%281%29.hdf" in result

    def test_s3_preserves_path_separators(self):
        result = s3_uri_to_https("s3://bucket/a/b/c/file.hdf")
        assert result == "https://bucket.s3.amazonaws.com/a/b/c/file.hdf"

    def test_custom_endpoint_strips_trailing_slash(self):
        endpoints = {"mybucket": "https://cdn.example.com/"}
        result = s3_uri_to_https("s3://mybucket/file.hdf", endpoint_map=endpoints)
        assert result == "https://cdn.example.com/file.hdf"


# ---------------------------------------------------------------------------
# DownloadMethod registry
# ---------------------------------------------------------------------------


class TestDownloadMethod:
    def setup_method(self):
        """Clear the registry before each test to isolate state."""
        DownloadMethod._registry.clear()
        DownloadMethod._plugins_loaded = False

    def test_register_and_get(self):
        def dummy_fn(requests, *, max_concurrent=5, **kw):
            return []

        method = DownloadMethod.register("test_backend", dummy_fn)
        assert method.name == "test_backend"

        # Force plugins_loaded so get() doesn't try entry points
        DownloadMethod._plugins_loaded = True
        retrieved = DownloadMethod.get("test_backend")
        assert retrieved is method

    def test_register_decorator_form(self):
        @DownloadMethod.register("decorator_test")
        def my_fn(requests, *, max_concurrent=5, **kw):
            return []

        DownloadMethod._plugins_loaded = True
        assert DownloadMethod.get("decorator_test") is my_fn

    def test_register_duplicate_same_fn_is_idempotent(self):
        def my_fn(requests, *, max_concurrent=5, **kw):
            return []

        first = DownloadMethod.register("dup_ok", my_fn)
        second = DownloadMethod.register("dup_ok", my_fn)
        assert first is second

    def test_register_duplicate_different_fn_raises(self):
        def fn_a(requests, *, max_concurrent=5, **kw):
            return []

        def fn_b(requests, *, max_concurrent=5, **kw):
            return []

        DownloadMethod.register("conflict", fn_a)
        with pytest.raises(ValueError, match="already registered"):
            DownloadMethod.register("conflict", fn_b)

    def test_get_unknown_raises(self):
        DownloadMethod._plugins_loaded = True
        with pytest.raises(KeyError, match="not registered"):
            DownloadMethod.get("nonexistent")

    def test_all_returns_registered(self):
        def fn_a(requests, *, max_concurrent=5, **kw):
            return []

        def fn_b(requests, *, max_concurrent=5, **kw):
            return []

        DownloadMethod.register("a", fn_a)
        DownloadMethod.register("b", fn_b)
        DownloadMethod._plugins_loaded = True

        all_methods = DownloadMethod.all()
        names = {m.name for m in all_methods}
        assert names == {"a", "b"}

    def test_call_dispatches_to_fn(self):
        sentinel = object()

        def fn(requests, *, max_concurrent=5, **kw):
            return [sentinel]

        method = DownloadMethod.register("callable_test", fn)
        req = DownloadRequest(uri="https://x.com/f", dest_dir="/tmp/x")
        result = method([req])
        assert result == [sentinel]
