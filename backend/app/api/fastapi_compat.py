from __future__ import annotations

import inspect
import json
import re
from contextvars import ContextVar
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response as StarletteResponse


_current_request: ContextVar["_CompatRequest"] = ContextVar("current_request")


class _RequestProxy:
    def _get(self) -> "_CompatRequest":
        current = _current_request.get(None)
        if current is None:
            raise RuntimeError("Request context is not available")
        return current

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)


class _CompatRequest:
    def __init__(
        self,
        request: Request,
        json_payload: Any,
        json_error: Exception | None,
    ) -> None:
        self._request = request
        self._json_payload = json_payload
        self._json_error = json_error

    @property
    def args(self):
        return self._request.query_params

    @property
    def headers(self):
        return self._request.headers

    def get_json(self, silent: bool = False):
        if self._json_error is not None:
            if silent:
                return None
            raise ValueError("Invalid JSON request body") from self._json_error
        return self._json_payload


request = _RequestProxy()


class Response(StarletteResponse):
    def __init__(
        self,
        response: Any = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
        mimetype: str | None = None,
        content_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        resolved_media_type = media_type or mimetype or content_type
        super().__init__(
            content=response,
            status_code=status,
            headers=headers,
            media_type=resolved_media_type,
        )


def jsonify(*args, **kwargs) -> JSONResponse:
    if args and kwargs:
        raise TypeError("jsonify accepts either args or kwargs, not both")
    if len(args) == 1:
        payload = args[0]
    elif len(args) > 1:
        payload = list(args)
    else:
        payload = kwargs
    return JSONResponse(content=payload)


_ROUTE_PARAM_RE = re.compile(r"<(?:(?P<converter>\w+):)?(?P<name>\w+)>")
_CONVERTER_MAP = {
    "int": "int",
    "float": "float",
    "path": "path",
    "uuid": "uuid",
}


def _convert_route_path(path: str) -> str:
    if path == "":
        return path
    if not path.startswith("/"):
        path = f"/{path}"

    def _replace(match: re.Match[str]) -> str:
        converter = (match.group("converter") or "").lower()
        name = match.group("name")
        mapped = _CONVERTER_MAP.get(converter)
        if mapped:
            return f"{{{name}:{mapped}}}"
        return f"{{{name}}}"

    return _ROUTE_PARAM_RE.sub(_replace, path)


def _response_from_tuple(result: tuple[Any, ...]) -> StarletteResponse:
    if len(result) not in (2, 3):
        raise ValueError("Unsupported tuple response shape")

    body = result[0]
    status_code = int(result[1])
    headers = result[2] if len(result) == 3 else None

    if isinstance(body, StarletteResponse):
        response = body
    elif isinstance(body, (dict, list)) or body is None:
        response = JSONResponse(content=body)
    else:
        response = Response(body)

    response.status_code = status_code
    if headers:
        response.headers.update(headers)
    return response


def _normalize_response(result: Any) -> Any:
    if isinstance(result, StarletteResponse):
        return result
    if isinstance(result, tuple):
        return _response_from_tuple(result)
    if isinstance(result, (dict, list)) or result is None:
        return JSONResponse(content=result)
    return result


async def _build_compat_request(raw_request: Request) -> _CompatRequest:
    json_payload = None
    json_error = None
    try:
        body = await raw_request.body()
        if body:
            json_payload = json.loads(body)
    except Exception as exc:
        json_error = exc
    return _CompatRequest(raw_request, json_payload=json_payload, json_error=json_error)


def _wrap_endpoint(func: Callable[..., Any]) -> Callable[..., Any]:
    async def endpoint(request: Request):
        compat_request = await _build_compat_request(request)
        token = _current_request.set(compat_request)
        try:
            path_params = dict(request.path_params)
            if inspect.iscoroutinefunction(func):
                result = await func(**path_params)
            else:
                result = await run_in_threadpool(func, **path_params)
        finally:
            _current_request.reset(token)
        return _normalize_response(result)

    endpoint.__name__ = func.__name__
    endpoint.__doc__ = func.__doc__
    return endpoint


class Blueprint:
    def __init__(self, name: str, import_name: str, url_prefix: str = "") -> None:
        self.name = name
        self.import_name = import_name
        self.url_prefix = url_prefix
        self.router = APIRouter(prefix=url_prefix)

    def route(self, path: str, methods: list[str] | tuple[str, ...] | None = None):
        resolved_methods = list(methods) if methods else ["GET"]
        return self._register(path, resolved_methods)

    def get(self, path: str):
        return self._register(path, ["GET"])

    def post(self, path: str):
        return self._register(path, ["POST"])

    def put(self, path: str):
        return self._register(path, ["PUT"])

    def delete(self, path: str):
        return self._register(path, ["DELETE"])

    def patch(self, path: str):
        return self._register(path, ["PATCH"])

    def _register(self, path: str, methods: list[str]):
        converted_path = _convert_route_path(path)

        def decorator(func: Callable[..., Any]):
            self.router.add_api_route(
                converted_path,
                _wrap_endpoint(func),
                methods=[method.upper() for method in methods],
                name=func.__name__,
            )
            return func

        return decorator
