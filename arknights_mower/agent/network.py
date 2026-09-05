"""Resolve the current proxy for every AI request, including existing models.

LangChain caches default HTTPX clients, whose environment proxies are fixed at
construction. Explicit transports avoid that cache. Each response owns its
connection, so a settings change never closes another request's active stream.
"""

import httpx
from langchain_openai import ChatOpenAI as _ChatOpenAI

from arknights_mower.utils.network_settings import proxy_for_url


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream, transport):
        self.stream, self.transport = stream, transport

    def __iter__(self):
        yield from self.stream

    def close(self):
        try:
            self.stream.close()
        finally:
            self.transport.close()


class _AsyncResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream, transport):
        self.stream, self.transport = stream, transport

    async def __aiter__(self):
        async for chunk in self.stream:
            yield chunk

    async def aclose(self):
        try:
            await self.stream.aclose()
        finally:
            await self.transport.aclose()


class _ProxyTransport(httpx.BaseTransport):
    def handle_request(self, request):
        transport = httpx.HTTPTransport(proxy=proxy_for_url(str(request.url), ai=True))
        try:
            response = transport.handle_request(request)
        except BaseException:
            transport.close()
            raise
        response.stream = _ResponseStream(response.stream, transport)
        return response


class _AsyncProxyTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        transport = httpx.AsyncHTTPTransport(
            proxy=proxy_for_url(str(request.url), ai=True)
        )
        try:
            response = await transport.handle_async_request(request)
        except BaseException:
            await transport.aclose()
            raise
        response.stream = _AsyncResponseStream(response.stream, transport)
        return response


def ChatOpenAI(**kwargs):
    return _ChatOpenAI(
        **kwargs,
        openai_proxy="",
        http_client=httpx.Client(transport=_ProxyTransport()),
        http_async_client=httpx.AsyncClient(transport=_AsyncProxyTransport()),
    )
