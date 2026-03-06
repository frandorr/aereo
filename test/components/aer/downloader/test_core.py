"""Tests for the downloader domain model (registry, value objects, URI utilities)."""

import pytest
from pathlib import Path

from aer.downloader import (
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
