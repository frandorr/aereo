from aer.downloader import DownloadMethod
from aer.search import SearchMethod


def bootstrap() -> None:
    """Initialize the aer plugin system by loading all predefined groups."""
    SearchMethod.all()
    DownloadMethod.all()
