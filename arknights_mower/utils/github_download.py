"""Shared GitHub file-download proxy settings; no global HTTP/session changes.

The detached updater passes an explicit proxy, so URL rewriting stays stdlib-only
and does not load the application's configuration or GUI in that process.
"""

from urllib.parse import urlsplit

DOWNLOAD_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "gist.githubusercontent.com",
}


def normalize_proxy(value):
    if not isinstance(value, str):
        raise ValueError("GitHub 下载代理地址必须是字符串")
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and parsed.port != 0
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and not any(c.isspace() or ord(c) < 32 for c in value)
            and "\\" not in value
            and "https:" not in parsed.path.lower()
            and "http:" not in parsed.path.lower()
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "请填写代理站点地址，例如 https://ghfast.top/，不要填写完整下载链接"
        )
    return value.rstrip("/") + "/"


def get_proxy():
    from arknights_mower.utils.network_settings import get_effective_settings

    return get_effective_settings()["github_proxy"]


def download_url(url, proxy=None):
    """Prefix GitHub file URLs; API calls and other hosts stay unchanged."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in DOWNLOAD_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        return url
    proxy = get_proxy() if proxy is None else normalize_proxy(proxy)
    return proxy + url if proxy else url
