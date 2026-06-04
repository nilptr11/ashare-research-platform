from __future__ import annotations

from typing import Any

from .config import TushareConfig, load_config


_TUSHARE_DEFAULT_HTTP_URL: str | None = None


class TushareError(RuntimeError):
    pass


class TushareCallError(TushareError):
    def __init__(self, api_name: str, message: str) -> None:
        self.api_name = api_name
        super().__init__(f"{api_name}: {message}")


def configure_tushare_proxy(proxy_url: str | None) -> None:
    global _TUSHARE_DEFAULT_HTTP_URL
    try:
        from tushare.pro import client as ts_client
    except ImportError as exc:
        raise TushareError("无法导入 tushare.pro.client，请确认 tushare 已安装") from exc
    if _TUSHARE_DEFAULT_HTTP_URL is None:
        _TUSHARE_DEFAULT_HTTP_URL = ts_client.DataApi._DataApi__http_url
    ts_client.DataApi._DataApi__http_url = proxy_url or _TUSHARE_DEFAULT_HTTP_URL


class TushareCaller:
    def __init__(
        self,
        token: str | None = None,
        proxy_url: str | None = None,
        env_file: str = ".env",
        config: TushareConfig | None = None,
    ) -> None:
        self._config = config or load_config(token=token, proxy_url=proxy_url, env_file=env_file)

    @property
    def token(self) -> str | None:
        return self._config.token

    @staticmethod
    def _select_fields(result: Any, fields: str | None) -> Any:
        if not fields or not hasattr(result, "__getitem__"):
            return result
        columns = [field.strip() for field in fields.split(",") if field.strip()]
        if not columns:
            return result
        return result[columns]

    @staticmethod
    def _raise_for_error_frame(api_name: str, result: Any) -> None:
        if not hasattr(result, "columns") or not hasattr(result, "__len__"):
            return
        columns = [str(column) for column in result.columns]
        if columns != ["error"] or len(result) == 0 or not hasattr(result, "iloc"):
            return
        raise TushareCallError(api_name, str(result.iloc[0]["error"]))

    def _pro_api(self, ts: Any) -> Any:
        configure_tushare_proxy(self._config.proxy_url)
        return ts.pro_api(self._config.token) if self._config.token else ts.pro_api()

    def call(
        self,
        api_name: str,
        params: dict[str, Any] | None = None,
        fields: str | None = None,
    ) -> Any:
        params = dict(params or {})

        try:
            import tushare as ts
        except ImportError as exc:
            raise TushareError("未安装 tushare，请先执行：python3 -m pip install -e .") from exc

        configure_tushare_proxy(self._config.proxy_url)
        if self._config.token:
            ts.set_token(self._config.token)

        if api_name == "pro_bar":
            params.setdefault("api", self._pro_api(ts))
            try:
                result = ts.pro_bar(**params)
                self._raise_for_error_frame(api_name, result)
                return self._select_fields(result, fields)
            except TushareCallError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise TushareCallError(api_name, str(exc)) from exc

        pro = self._pro_api(ts)
        method = getattr(pro, api_name, None)
        try:
            if callable(method):
                if fields:
                    params["fields"] = fields
                result = method(**params)
                self._raise_for_error_frame(api_name, result)
                return result

            if fields:
                result = pro.query(api_name, fields=fields, **params)
            else:
                result = pro.query(api_name, **params)
            self._raise_for_error_frame(api_name, result)
            return result
        except TushareCallError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TushareCallError(api_name, str(exc)) from exc
