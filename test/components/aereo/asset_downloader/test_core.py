import threading
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aereo.asset_downloader import download_assets_safely, extract_asset_safely


def _make_zip(archive: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


# ---------------------------------------------------------------------------
# extract_asset_safely tests (unchanged behaviour)
# ---------------------------------------------------------------------------


def test_extract_asset_safely_basic(tmp_path: Path) -> None:
    archive = tmp_path / "test.zip"
    _make_zip(archive, {"data.txt": "hello", "sub/nested.bin": "world"})

    extract_dir = tmp_path / "extracted"
    extract_asset_safely(archive, extract_dir)

    assert (extract_dir / "data.txt").read_text() == "hello"
    assert (extract_dir / "sub" / "nested.bin").read_text() == "world"
    assert (extract_dir.with_suffix(".extracted")).exists()


def test_extract_asset_safely_idempotent(tmp_path: Path) -> None:
    archive = tmp_path / "test.zip"
    _make_zip(archive, {"data.txt": "hello"})

    extract_dir = tmp_path / "extracted"
    extract_asset_safely(archive, extract_dir)
    # Second call should be a no-op
    extract_asset_safely(archive, extract_dir)

    assert (extract_dir / "data.txt").read_text() == "hello"


def test_extract_asset_safely_single_root_dir(tmp_path: Path) -> None:
    """SEN3-style zip: one root directory inside the archive.

    Without hoisting, the root directory is preserved inside *extract_dir*.
    """
    archive = tmp_path / "product.SEN3.zip"
    _make_zip(
        archive,
        {
            "product.SEN3/data.txt": "hello",
            "product.SEN3/meta.xml": "<xml/>",
        },
    )

    extract_dir = tmp_path / "product.SEN3"
    extract_asset_safely(archive, extract_dir)

    assert (extract_dir / "product.SEN3" / "data.txt").read_text() == "hello"
    assert (extract_dir / "product.SEN3" / "meta.xml").read_text() == "<xml/>"
    # The marker should exist
    assert (extract_dir.with_suffix(".extracted")).exists()


def test_extract_asset_safely_default_extract_dir(tmp_path: Path) -> None:
    archive = tmp_path / "product.SEN3.zip"
    _make_zip(archive, {"product.SEN3/data.txt": "hello"})

    # extract_dir omitted → defaults to archive_path.with_suffix("")
    extract_asset_safely(archive)

    expected = tmp_path / "product.SEN3"
    assert (expected / "product.SEN3" / "data.txt").read_text() == "hello"


def test_extract_asset_safely_concurrent(tmp_path: Path) -> None:
    archive = tmp_path / "test.zip"
    _make_zip(archive, {"data.txt": "hello"})

    extract_dir = tmp_path / "extracted"
    errors: list[Exception] = []

    def worker() -> None:
        try:
            extract_asset_safely(archive, extract_dir)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert (extract_dir / "data.txt").read_text() == "hello"


def test_extract_asset_safely_recovers_from_stale_dir(tmp_path: Path) -> None:
    archive = tmp_path / "test.zip"
    _make_zip(archive, {"data.txt": "hello"})

    extract_dir = tmp_path / "extracted"
    # Simulate a stale partial extraction (no marker)
    extract_dir.mkdir()
    (extract_dir / "partial.tmp").write_text("incomplete")

    extract_asset_safely(archive, extract_dir)

    assert not (extract_dir / "partial.tmp").exists()
    assert (extract_dir / "data.txt").read_text() == "hello"


# ---------------------------------------------------------------------------
# download_assets_safely tests — obstore-backed
# ---------------------------------------------------------------------------


def _mock_get_result(data: bytes) -> MagicMock:
    """Return a mock obstore GetResult that yields *data* as one chunk."""
    mock = MagicMock()
    mock.__iter__ = MagicMock(return_value=iter([data]))
    return mock


def test_download_assets_safely_local_files(tmp_path: Path) -> None:
    """Built-in logic copies local files via obstore LocalStore."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    file1 = src_dir / "file1.txt"
    file2 = src_dir / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    dest1 = dest_dir / "file1_dest.txt"
    dest2 = dest_dir / "file2_dest.txt"

    download_assets_safely(
        hrefs=[str(file1), str(file2)],
        local_paths=[dest1, dest2],
    )

    assert dest1.read_text() == "content1"
    assert dest2.read_text() == "content2"


def test_download_assets_safely_s3(tmp_path: Path) -> None:
    """S3 URLs are resolved to S3Store and streamed via obstore.get."""
    dest = tmp_path / "s3_file.tif"

    with (
        patch("obstore.get") as mock_get,
        patch("obstore.store.S3Store") as mock_store_cls,
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_get.return_value = _mock_get_result(b"s3-payload")

        download_assets_safely(
            hrefs=["s3://my-bucket/path/to/file.tif"],
            local_paths=[dest],
        )

        mock_store_cls.assert_called_once_with("my-bucket", skip_signature=True)
        mock_get.assert_called_once_with(mock_store, "path/to/file.tif")
        assert dest.read_bytes() == b"s3-payload"


def test_download_assets_safely_https(tmp_path: Path) -> None:
    """HTTPS URLs are resolved to HTTPStore and streamed via obstore.get."""
    dest = tmp_path / "http_file.tif"

    with (
        patch("obstore.get") as mock_get,
        patch("obstore.store.HTTPStore") as mock_store_cls,
    ):
        mock_store = MagicMock()
        mock_store_cls.from_url.return_value = mock_store
        mock_get.return_value = _mock_get_result(b"http-payload")

        download_assets_safely(
            hrefs=["https://example.com/data/file.tif"],
            local_paths=[dest],
        )

        mock_store_cls.from_url.assert_called_once_with(
            "https://example.com/data/file.tif"
        )
        mock_get.assert_called_once_with(mock_store, "")
        assert dest.read_bytes() == b"http-payload"


def test_download_assets_safely_custom_downloader(tmp_path: Path) -> None:
    """Custom downloader callable is invoked for each asset (plugin contract)."""
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    dest1 = dest_dir / "file1_dest.txt"
    dest2 = dest_dir / "file2_dest.txt"

    called_args = []

    def custom_downloader(url: str, local_path: Path) -> None:
        called_args.append((url, local_path))
        local_path.write_text(f"downloaded:{url}")

    download_assets_safely(
        hrefs=["mock://file1", "mock://file2"],
        local_paths=[dest1, dest2],
        downloader=custom_downloader,
    )

    assert dest1.read_text() == "downloaded:mock://file1"
    assert dest2.read_text() == "downloaded:mock://file2"
    assert len(called_args) == 2


def test_download_assets_safely_concurrent_locking(tmp_path: Path) -> None:
    """Multiple threads downloading the same file do not corrupt it."""
    dest = tmp_path / "shared.tif"

    with (
        patch("obstore.get") as mock_get,
        patch("obstore.store.S3Store") as mock_store_cls,
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_get.return_value = _mock_get_result(b"concurrent-payload")

        errors: list[Exception] = []

        def worker() -> None:
            try:
                download_assets_safely(
                    hrefs=["s3://bucket/file.tif"],
                    local_paths=[dest],
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert dest.read_bytes() == b"concurrent-payload"


def test_download_assets_safely_length_mismatch(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError, match="hrefs and local_paths must have the same length"
    ):
        download_assets_safely(
            hrefs=["mock://file1"],
            local_paths=[],
        )


def test_download_assets_safely_s3_with_store_options(tmp_path: Path) -> None:
    """store_options are forwarded to the S3Store constructor."""
    dest = tmp_path / "s3_auth_file.tif"

    with (
        patch("obstore.get") as mock_get,
        patch("obstore.store.S3Store") as mock_store_cls,
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_get.return_value = _mock_get_result(b"s3-auth-payload")

        download_assets_safely(
            hrefs=["s3://my-bucket/path/to/file.tif"],
            local_paths=[dest],
            store_options={
                "skip_signature": False,
                "access_key_id": "AKIA...",
                "secret_access_key": "secret...",
            },
        )

        mock_store_cls.assert_called_once_with(
            "my-bucket",
            skip_signature=False,
            access_key_id="AKIA...",
            secret_access_key="secret...",
        )
        assert dest.read_bytes() == b"s3-auth-payload"


def test_download_assets_safely_unsupported_scheme(tmp_path: Path) -> None:
    """Unsupported URL schemes raise ValueError."""
    dest = tmp_path / "bad.txt"
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        download_assets_safely(
            hrefs=["ftp://example.com/file.txt"],
            local_paths=[dest],
        )


def test_download_assets_safely_s3_fallback_to_earthdata_https(
    tmp_path: Path,
) -> None:
    """When S3 fails and fallback is an Earthdata HTTPS URL, use earthaccess."""
    dest = tmp_path / "earthdata_file.tif"

    with (
        patch("obstore.store.S3Store") as mock_s3_cls,
        patch(
            "aereo.asset_downloader.core._download_with_earthaccess"
        ) as mock_earthdata_download,
    ):
        mock_s3_cls.side_effect = RuntimeError("cross-region S3 failure")

        download_assets_safely(
            hrefs=["s3://my-bucket/path/to/file.tif"],
            local_paths=[dest],
            fallback_hrefs=[
                "https://data.lpdaac.earthdatacloud.nasa.gov/some/file.tif"
            ],
        )

        mock_earthdata_download.assert_called_once_with(
            "https://data.lpdaac.earthdatacloud.nasa.gov/some/file.tif",
            dest,
        )


def test_download_assets_safely_s3_fallback_to_non_earthdata_https(
    tmp_path: Path,
) -> None:
    """When S3 fails and fallback is a generic HTTPS URL, use obstore HTTPStore."""
    dest = tmp_path / "http_file.tif"

    with (
        patch("obstore.store.S3Store") as mock_s3_cls,
        patch("obstore.get") as mock_get,
        patch("obstore.store.HTTPStore") as mock_http_cls,
    ):
        mock_s3_cls.side_effect = RuntimeError("cross-region S3 failure")
        mock_http_store = MagicMock()
        mock_http_cls.from_url.return_value = mock_http_store
        mock_get.return_value = _mock_get_result(b"http-fallback-payload")

        download_assets_safely(
            hrefs=["s3://my-bucket/path/to/file.tif"],
            local_paths=[dest],
            fallback_hrefs=["https://example.com/data/file.tif"],
        )

        mock_http_cls.from_url.assert_called_once_with(
            "https://example.com/data/file.tif"
        )
        mock_get.assert_called_once_with(mock_http_store, "")
        assert dest.read_bytes() == b"http-fallback-payload"


def test_download_with_earthaccess(tmp_path: Path) -> None:
    """_download_with_earthaccess streams through an authenticated session."""
    dest = tmp_path / "earthdata.tif"
    url = "https://data.lpdaac.earthdatacloud.nasa.gov/some/file.tif"

    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with (
        patch("earthaccess.login") as mock_login,
        patch("earthaccess.get_requests_https_session", return_value=mock_session),
    ):
        from aereo.asset_downloader.core import _download_with_earthaccess

        _download_with_earthaccess(url, dest)

        mock_login.assert_called_once_with(persist=True)
        mock_session.get.assert_called_once_with(url, stream=True)
        mock_response.raise_for_status.assert_called_once()
        assert dest.read_bytes() == b"chunk1chunk2"
