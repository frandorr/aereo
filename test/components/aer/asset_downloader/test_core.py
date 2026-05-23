import threading
import zipfile
from pathlib import Path


from aer.asset_downloader import download_assets_safely, extract_asset_safely


def _make_zip(archive: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


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


def test_download_assets_safely_basic(tmp_path: Path) -> None:
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


def test_download_assets_safely_downloader(tmp_path: Path) -> None:
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


def test_download_assets_safely_length_mismatch(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(
        ValueError, match="hrefs and local_paths must have the same length"
    ):
        download_assets_safely(
            hrefs=["mock://file1"],
            local_paths=[],
        )
