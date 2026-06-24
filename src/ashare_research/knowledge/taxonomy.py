from __future__ import annotations


ENTITY_TYPES = {
    "company",
    "concept",
    "evidence_source_group",
    "industry",
    "industry_chain_node",
    "product",
    "security",
    "theme",
}


PREDICATES = {
    "alias_of",
    "belongs_to",
    "has_component",
    "has_product_exposure",
    "maps_to_concept",
    "preferred_source_for",
    "supplies_to",
}


def is_known_entity_type(value: str) -> bool:
    return value in ENTITY_TYPES


def is_known_predicate(value: str) -> bool:
    return value in PREDICATES
