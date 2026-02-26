# from typing import Generic, TypeVar
# import attrs

# Spectrum = TypeVar("Spectrum")
# Modifier = TypeVar("Modifier")

# @attrs.frozen
# class Band(Generic[Spectrum, Modifier]):
#     pass

# class Visible:
#     pass

# class TOA:
#     pass


class Band: ...


class Visible(Band): ...


class TOA(Band): ...
