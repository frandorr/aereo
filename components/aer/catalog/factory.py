"""
This module defines the ProductFactory, which is responsible
for creating Product aggregates by resolving dependencies
from the AerSpectralRepository.
The factory abstracts away the complexity of assembling a Product,
allowing clients to simply request a Product by providing
necessary identifiers.

"""

from aer.catalog.core import Product
from aer.repository.core import AerSpectralRepository


class ProductFactory:
    """Creates Product aggregates by resolving dependencies."""

    def __init__(self, spectral_repo: AerSpectralRepository):
        self.repo = spectral_repo

    def create_product(
        self,
        product_id: str,
        satellite_acronyms: list[str],
        instrument_acronyms: list[str],
    ) -> Product:
        # 1. Resolve domain objects using the repository
        satellites = [self.repo.get_satellite(acro) for acro in satellite_acronyms]
        instruments = [self.repo.get_instrument(acro) for acro in instrument_acronyms]

        # 2. Assemble and return the Product aggregate
        return Product(
            product_id=product_id,
            processing_level="L1b",  # or pass as arg
            satellites=satellites,
            instruments=instruments,
        )
