from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


_DEFAULT_ENV_FILE = Path(".env")


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parent


_PROJECT_ROOT = _find_project_root()


@dataclass(frozen=True)
class TushareConfig:
    token: str | None
    proxy_url: str | None
    points: int
    allow_separate_permission: bool


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_int(value: str | None, default: int, name: str) -> int:
    normalized = _normalize(value)
    if normalized is None:
        return default
    try:
        return int(normalized)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数：{normalized}") from exc


def _parse_bool(value: str | None, default: bool) -> bool:
    normalized = _normalize(value)
    if normalized is None:
        return default
    lowered = normalized.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"布尔配置必须是 true/false：{normalized}")


def _default_env_candidates() -> list[Path]:
    cwd = Path.cwd()
    candidates = [cwd / _DEFAULT_ENV_FILE]

    try:
        cwd_resolved = cwd.resolve()
        project_root_resolved = _PROJECT_ROOT.resolve()
    except OSError:
        cwd_resolved = None
        project_root_resolved = None

    if (
        cwd_resolved is not None
        and project_root_resolved is not None
        and cwd_resolved.is_relative_to(project_root_resolved)
    ):
        current = cwd_resolved
        while current != project_root_resolved:
            current = current.parent
            candidates.append(current / _DEFAULT_ENV_FILE)

    candidates.append(_PROJECT_ROOT / _DEFAULT_ENV_FILE)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        unique_candidates.append(candidate)
        seen.add(candidate)
    return unique_candidates


def resolve_env_file(path: str | Path = _DEFAULT_ENV_FILE) -> Path:
    env_path = Path(path).expanduser()
    if env_path.is_absolute() or env_path != _DEFAULT_ENV_FILE:
        return env_path

    candidates = _default_env_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def read_env_file(path: str | Path = ".env") -> dict[str, str]:
    env_path = resolve_env_file(path)
    if not env_path.exists():
        return {}
    if not env_path.is_file():
        raise ConfigError(f"配置路径不是文件：{env_path}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ConfigError(f"{env_path}:{line_number} 不是合法 .env 行，必须是 KEY=VALUE")

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"{env_path}:{line_number} 缺少配置名")
        values[key] = _unquote(value)
    return values


def load_config(
    token: str | None = None,
    proxy_url: str | None = None,
    points: int | None = None,
    allow_separate_permission: bool | None = None,
    env_file: str | Path = ".env",
) -> TushareConfig:
    env_values = read_env_file(env_file)
    if proxy_url is not None and _normalize(proxy_url) is None:
        resolved_proxy_url = None
    else:
        resolved_proxy_url = (
            _normalize(proxy_url)
            or _normalize(os.getenv("TUSHARE_PROXY_URL"))
            or _normalize(env_values.get("TUSHARE_PROXY_URL"))
        )

    env_points = _parse_int(os.getenv("TUSHARE_POINTS") or env_values.get("TUSHARE_POINTS"), 15000, "TUSHARE_POINTS")
    env_allow_separate_permission = _parse_bool(
        os.getenv("TUSHARE_ALLOW_SEPARATE_PERMISSION") or env_values.get("TUSHARE_ALLOW_SEPARATE_PERMISSION"),
        False,
    )

    return TushareConfig(
        token=_normalize(token) or _normalize(os.getenv("TUSHARE_TOKEN")) or _normalize(env_values.get("TUSHARE_TOKEN")),
        proxy_url=resolved_proxy_url,
        points=points if points is not None else env_points,
        allow_separate_permission=(
            allow_separate_permission
            if allow_separate_permission is not None
            else env_allow_separate_permission
        ),
    )
