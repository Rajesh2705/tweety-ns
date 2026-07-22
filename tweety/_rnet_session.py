"""
httpx.AsyncClient-compatible facade backed by rnet, so tweety's Request class
(http.py) can use rnet's TLS/HTTP2 fingerprinting instead of httpx's default one.

Only implements the subset of the httpx.AsyncClient surface that tweety's
Request/download_media code paths actually touch: .headers, .cookies,
.request(...), .stream(...) as an async context manager.
"""
import json as _json
from contextlib import asynccontextmanager

import rnet
from rnet import Impersonate, Method, Proxy

_METHOD_MAP = {
    "GET": Method.GET,
    "POST": Method.POST,
    "PUT": Method.PUT,
    "DELETE": Method.DELETE,
    "HEAD": Method.HEAD,
    "OPTIONS": Method.OPTIONS,
    "PATCH": Method.PATCH,
    "TRACE": Method.TRACE,
}


def _headers_to_dict(header_map) -> dict:
    out = {}
    if header_map is None:
        return out
    try:
        for k, v in header_map.items():
            key = k.decode("latin-1") if isinstance(k, bytes) else str(k)
            val = v.decode("latin-1") if isinstance(v, bytes) else str(v)
            out[key.lower()] = val
    except Exception:
        pass
    return out


def _cookies_to_dict(cookie_list) -> dict:
    out = {}
    for cookie in cookie_list or []:
        try:
            out[cookie.name] = cookie.value
        except Exception:
            continue
    return out


class RnetResponse:
    """Adapts rnet.Response to the subset of httpx.Response tweety relies on."""

    def __init__(self, raw, status_code, headers, cookies, text, content, url):
        self._raw = raw
        self.status_code = status_code
        self.headers = headers
        self.cookies = cookies
        self.text = text
        self.content = content
        self.url = url

    @classmethod
    async def build(cls, raw):
        status_code = getattr(raw, "status", None)
        if status_code is None:
            status_code = raw.status_code.as_int()
        headers = _headers_to_dict(raw.headers)
        cookies = _cookies_to_dict(raw.cookies)
        content = await raw.bytes()
        encoding = getattr(raw, "encoding", None) or "utf-8"
        try:
            text = content.decode(encoding, "replace")
        except LookupError:
            text = content.decode("utf-8", "replace")
        return cls(raw, status_code, headers, cookies, text, content, str(raw.url))

    def json(self):
        if not self.text:
            return None
        return _json.loads(self.text)

    def raise_for_status(self):
        if not (200 <= self.status_code < 400):
            raise rnet.exceptions.StatusError(f"HTTP {self.status_code} for url {self.url}")


class RnetStreamResponse:
    """Adapts a streaming rnet.Response for the download_media() code path."""

    def __init__(self, raw):
        self._raw = raw
        self.status_code = getattr(raw, "status", None) or raw.status_code.as_int()
        self.headers = _headers_to_dict(raw.headers)

    def raise_for_status(self):
        if not (200 <= self.status_code < 400):
            raise rnet.exceptions.StatusError(f"HTTP {self.status_code}")

    async def aiter_bytes(self, chunk_size=8192):
        async with self._raw.stream() as streamer:
            async for chunk in streamer:
                yield bytes(chunk)


class RnetAsyncSession:
    """
    Drop-in replacement for httpx.AsyncClient covering only what tweety's
    Request class (http.py) actually calls: headers/cookies attributes,
    .request(), and .stream() as an async context manager.
    """

    def __init__(self, headers=None, http2=True, proxy=None, timeout=60,
                 follow_redirects=True, impersonate=None, **kwargs):
        self.headers = dict(headers or {})
        self.cookies = None

        client_kwargs = {
            "impersonate": impersonate or Impersonate.Chrome137,
            "allow_redirects": follow_redirects,
            "timeout": int(timeout) if timeout else None,
            "cookie_store": False,
        }
        if proxy:
            client_kwargs["proxies"] = [Proxy.all(proxy)]

        self._client = rnet.Client(**client_kwargs)

    def _build_kwargs(self, headers=None, cookies=None, params=None, json=None, data=None):
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)

        merged_cookies = dict(self.cookies or {})
        if cookies:
            merged_cookies.update(cookies)

        kwargs = {}
        if merged_headers:
            kwargs["headers"] = merged_headers
        if merged_cookies:
            kwargs["cookies"] = merged_cookies
        # some builder methods (search(), radar_search()) pre-encode params into a
        # raw "a=1&b=2" query string via urlencode() instead of a dict — httpx accepts
        # that natively for params=, rnet's typed `query` kwarg does not, so that case
        # is handled separately in request()/stream() by appending it straight to the URL.
        if params and not isinstance(params, str):
            items = params.items() if isinstance(params, dict) else params
            kwargs["query"] = [(str(k), str(v)) for k, v in items]
        if json is not None:
            kwargs["json"] = json
        if data is not None:
            if isinstance(data, dict):
                kwargs["form"] = [(str(k), str(v)) for k, v in data.items()]
            else:
                kwargs["body"] = data
        return kwargs

    @staticmethod
    def _apply_raw_query_string(url, params):
        if not (params and isinstance(params, str)):
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{params}"

    async def request(self, method, url, headers=None, cookies=None, params=None,
                       json=None, data=None, timeout=None, **_ignored):
        method_enum = _METHOD_MAP[method.upper()]
        url = self._apply_raw_query_string(url, params)
        req_kwargs = self._build_kwargs(headers, cookies, params, json, data)
        if timeout is not None:
            try:
                req_kwargs["timeout"] = int(timeout)
            except (TypeError, ValueError):
                pass
        raw = await self._client.request(method_enum, url, **req_kwargs)
        return await RnetResponse.build(raw)

    @asynccontextmanager
    async def stream(self, method, url, headers=None, follow_redirects=True, timeout=None, **_ignored):
        method_enum = _METHOD_MAP[method.upper()]
        req_kwargs = self._build_kwargs(headers)
        if timeout is not None:
            try:
                req_kwargs["timeout"] = int(timeout)
            except (TypeError, ValueError):
                pass
        raw = await self._client.request(method_enum, url, **req_kwargs)
        try:
            yield RnetStreamResponse(raw)
        finally:
            await raw.close()

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def put(self, url, **kwargs):
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await self.request("DELETE", url, **kwargs)

    async def head(self, url, **kwargs):
        return await self.request("HEAD", url, **kwargs)

    async def options(self, url, **kwargs):
        return await self.request("OPTIONS", url, **kwargs)

    async def patch(self, url, **kwargs):
        return await self.request("PATCH", url, **kwargs)

    async def aclose(self):
        pass
