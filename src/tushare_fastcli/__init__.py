"""Tushare 快速调用工具。"""

from .client import TushareCallError, TushareCaller, TushareError
from .news import (
    DEFAULT_NEWS_SOURCES,
    TushareNewsError,
    TushareNewsFetchError,
    TushareNewsParseError,
    build_news_records,
    crawl_tushare_news,
    load_tushare_cookie,
    normalize_news_sources,
    parse_news_page,
)
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
    "DEFAULT_NEWS_SOURCES",
    "InterfaceEntry",
    "InterfaceRegistry",
    "RecipeError",
    "SchemaError",
    "TushareCallError",
    "TushareCaller",
    "TushareError",
    "TushareInterfaceSelectionError",
    "TushareNewsError",
    "TushareNewsFetchError",
    "TushareNewsParseError",
    "TusharePermissionError",
    "TushareProvider",
    "TushareProviderError",
    "TushareUnknownInterfaceError",
    "build_news_records",
    "crawl_tushare_news",
    "default_fields",
    "default_recipe_params",
    "get_api_schema",
    "get_recipe",
    "load_tushare_cookie",
    "load_api_schemas",
    "load_recipes",
    "load_registry",
    "normalize_news_sources",
    "parse_news_page",
]
