"""Tushare 快速调用工具。"""

from .client import TushareCallError, TushareCaller, TushareError
from .provider import (
    TushareInterfaceSelectionError,
    TusharePermissionError,
    TushareProvider,
    TushareProviderError,
    TushareUnknownInterfaceError,
)
from .recipes import (
    ApiRecipe,
    RecipeError,
    default_fields,
    default_recipe_params,
    get_recipe,
    load_recipes,
)
from .registry import InterfaceEntry, InterfaceRegistry, load_registry
from .schemas import ApiParameter, ApiSchema, SchemaError, get_api_schema, load_api_schemas

__all__ = [
    "ApiParameter",
    "ApiSchema",
    "ApiRecipe",
    "InterfaceEntry",
    "InterfaceRegistry",
    "RecipeError",
    "SchemaError",
    "TushareCallError",
    "TushareCaller",
    "TushareError",
    "TushareInterfaceSelectionError",
    "TusharePermissionError",
    "TushareProvider",
    "TushareProviderError",
    "TushareUnknownInterfaceError",
    "default_fields",
    "default_recipe_params",
    "get_api_schema",
    "get_recipe",
    "load_api_schemas",
    "load_recipes",
    "load_registry",
]
