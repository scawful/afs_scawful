"""Zelda/ALTTP knowledge modules for afs-scawful."""

from .alttp_addresses import (
    ALTTP_ADDRESSES,
    INVENTORY_ADDRESSES,
    LINK_STATE_ADDRESSES,
    SPRITE_TABLES,
    WRAM_ADDRESSES,
    AddressCategory,
    AddressInfo,
    format_address_reference,
    get_address_info,
    get_addresses_by_category,
    lookup_by_address,
)
from .entity_extractor import (
    EntityExtractor,
    ExtractedEntity,
    ExtractionResult,
    extract_entities,
    extract_with_stats,
)

__all__ = [
    "ALTTP_ADDRESSES",
    "SPRITE_TABLES",
    "LINK_STATE_ADDRESSES",
    "INVENTORY_ADDRESSES",
    "WRAM_ADDRESSES",
    "AddressCategory",
    "AddressInfo",
    "get_address_info",
    "get_addresses_by_category",
    "format_address_reference",
    "lookup_by_address",
    "EntityExtractor",
    "ExtractedEntity",
    "ExtractionResult",
    "extract_entities",
    "extract_with_stats",
]
