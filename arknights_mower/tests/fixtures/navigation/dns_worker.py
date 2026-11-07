"""Offline resolver that blocks its own process's executor thread."""

import asyncio
import socket
import time


def slow_dns(channel, *args):
    def resolve(*args, **kwargs):
        channel.send_bytes(b"dns-started")
        time.sleep(1.65)
        return []

    socket.getaddrinfo = resolve

    async def request():
        await asyncio.get_running_loop().getaddrinfo("offline.invalid", 443)

    try:
        asyncio.run(request())
    finally:
        channel.close()
