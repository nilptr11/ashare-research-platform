from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .schemas import DatasetContract, IngestionRecipe, PipelineSpec, SourceSpec


class RegistryError(ValueError):
    """Raised when registry entries are missing or inconsistent."""


@dataclass
class FoundationRegistry:
    sources: dict[str, SourceSpec] = field(default_factory=dict)
    datasets: dict[str, DatasetContract] = field(default_factory=dict)
    recipes: dict[str, IngestionRecipe] = field(default_factory=dict)
    pipelines: dict[str, PipelineSpec] = field(default_factory=dict)

    @classmethod
    def from_entries(
        cls,
        *,
        sources: Iterable[SourceSpec] = (),
        datasets: Iterable[DatasetContract] = (),
        recipes: Iterable[IngestionRecipe] = (),
        pipelines: Iterable[PipelineSpec] = (),
    ) -> "FoundationRegistry":
        registry = cls()
        for source in sources:
            registry.add_source(source)
        for dataset in datasets:
            registry.add_dataset(dataset)
        for recipe in recipes:
            registry.add_recipe(recipe)
        for pipeline in pipelines:
            registry.add_pipeline(pipeline)
        registry.assert_integrity()
        return registry

    def add_source(self, source: SourceSpec) -> None:
        _add_unique(self.sources, source.id, source, "source")

    def add_dataset(self, dataset: DatasetContract) -> None:
        _add_unique(self.datasets, dataset.id, dataset, "dataset")

    def add_recipe(self, recipe: IngestionRecipe) -> None:
        _add_unique(self.recipes, recipe.id, recipe, "recipe")

    def add_pipeline(self, pipeline: PipelineSpec) -> None:
        _add_unique(self.pipelines, pipeline.id, pipeline, "pipeline")

    def require_source(self, source_id: str) -> SourceSpec:
        return _require(self.sources, source_id, "source")

    def require_dataset(self, dataset_id: str) -> DatasetContract:
        return _require(self.datasets, dataset_id, "dataset")

    def require_recipe(self, recipe_id: str) -> IngestionRecipe:
        return _require(self.recipes, recipe_id, "recipe")

    def require_pipeline(self, pipeline_id: str) -> PipelineSpec:
        return _require(self.pipelines, pipeline_id, "pipeline")

    def recipes_for_dataset(self, dataset_id: str) -> list[IngestionRecipe]:
        return sorted(
            (recipe for recipe in self.recipes.values() if recipe.target_dataset_id == dataset_id),
            key=lambda recipe: (recipe.selection_priority, recipe.id),
        )

    def datasets_for_domain(self, domain: str) -> list[DatasetContract]:
        return sorted((dataset for dataset in self.datasets.values() if dataset.domain == domain), key=lambda item: item.id)

    def validate_integrity(self) -> list[str]:
        errors: list[str] = []
        for recipe in self.recipes.values():
            if recipe.source_id not in self.sources:
                errors.append(f"{recipe.id}: source not registered: {recipe.source_id}")
            if recipe.target_dataset_id not in self.datasets:
                errors.append(f"{recipe.id}: target dataset not registered: {recipe.target_dataset_id}")
        for pipeline in self.pipelines.values():
            for step in pipeline.steps:
                if step.recipe_id not in self.recipes:
                    errors.append(f"{pipeline.id}: recipe not registered: {step.recipe_id}")
        return errors

    def assert_integrity(self) -> None:
        errors = self.validate_integrity()
        if errors:
            raise RegistryError("; ".join(errors))


def _add_unique(mapping: dict[str, object], key: str, value: object, label: str) -> None:
    if key in mapping:
        raise RegistryError(f"duplicate {label}: {key}")
    mapping[key] = value


def _require(mapping: dict[str, object], key: str, label: str):
    try:
        return mapping[key]
    except KeyError as error:
        raise RegistryError(f"{label} not registered: {key}") from error
