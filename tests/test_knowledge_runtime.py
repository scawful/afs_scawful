from __future__ import annotations

from afs_scawful.knowledge import AddressCategory, EntityExtractor
from afs_scawful.knowledge.adapters import ALTTPKnowledgeGraph


def test_knowledge_runtime_exports_move_to_extension() -> None:
    assert AddressCategory is not None
    assert ALTTPKnowledgeGraph is not None


def test_entity_extractor_constructs() -> None:
    extractor = EntityExtractor()
    assert extractor is not None
