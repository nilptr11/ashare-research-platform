from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class ApiParameter:
    name: str
    type: str
    required: str
    raw_required: str
    description: str

    @property
    def is_required(self) -> bool:
        return self.required.upper() == "Y"


@dataclass(frozen=True)
class ApiSchema:
    key: str
    api_name: str
    doc_id: str
    title: str
    category: str
    doc_url: str
    fetch_status: str
    parse_status: str
    input_params: tuple[ApiParameter, ...]
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    example_params: tuple[dict[str, Any], ...]
    default_params: dict[str, Any]
    default_params_source: str
    error_message: str

    @property
    def params_by_name(self) -> dict[str, ApiParameter]:
        return {param.name: param for param in self.input_params}


def _parameter_from_dict(item: dict[str, Any]) -> ApiParameter:
    return ApiParameter(
        name=str(item.get("name", "")),
        type=str(item.get("type", "")),
        required=str(item.get("required", "")),
        raw_required=str(item.get("raw_required", "")),
        description=str(item.get("description", "")),
    )


def _schema_from_dict(item: dict[str, Any]) -> ApiSchema:
    return ApiSchema(
        key=str(item["key"]),
        api_name=str(item["api_name"]),
        doc_id=str(item.get("doc_id", "")),
        title=str(item.get("title", "")),
        category=str(item.get("category", "")),
        doc_url=str(item.get("doc_url", "")),
        fetch_status=str(item.get("fetch_status", "")),
        parse_status=str(item.get("parse_status", "")),
        input_params=tuple(_parameter_from_dict(param) for param in item.get("input_params", [])),
        required_params=tuple(str(param) for param in item.get("required_params", [])),
        optional_params=tuple(str(param) for param in item.get("optional_params", [])),
        example_params=tuple(dict(params) for params in item.get("example_params", [])),
        default_params=dict(item.get("default_params", {})),
        default_params_source=str(item.get("default_params_source", "")),
        error_message=str(item.get("error_message", "")),
    )


def load_api_schemas(path: str | Path | None = None) -> dict[str, ApiSchema]:
    if path is None:
        data_path = files("ashare_data_provider").joinpath("api_schemas.json")
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        key: _schema_from_dict(item)
        for key, item in payload.get("schemas", {}).items()
    }


def get_api_schema(
    api_name: str,
    doc_id: str | None = None,
    key: str | None = None,
) -> ApiSchema:
    schemas = load_api_schemas()
    if key is not None:
        try:
            return schemas[key]
        except KeyError as exc:
            raise SchemaError(f"未找到接口 schema：{key}") from exc

    matches = [
        schema
        for schema in schemas.values()
        if schema.api_name == api_name and (doc_id is None or schema.doc_id == doc_id)
    ]
    if not matches:
        detail = f"{api_name}:{doc_id}" if doc_id else api_name
        raise SchemaError(f"未找到接口 schema：{detail}")
    if len(matches) > 1:
        keys = ", ".join(schema.key for schema in matches)
        raise SchemaError(f"接口 schema 不唯一，请指定 doc_id 或 key：{keys}")
    return matches[0]
