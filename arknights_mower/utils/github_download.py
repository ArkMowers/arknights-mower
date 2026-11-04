"""Shared GitHub credentials and file-download routing; no global session changes.

The detached updater passes an explicit proxy, so URL rewriting stays stdlib-only
and does not load the application's configuration or GUI in that process.
"""

import base64
from urllib.parse import urlsplit

DOWNLOAD_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "gist.githubusercontent.com",
}
FALLBACK_PROXIES = (
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://gh-proxy.org/",
    "https://edgeone.gh-proxy.org/",
)


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


def normalize_token(value):
    if not isinstance(value, str):
        raise ValueError("GitHub Token 必须是字符串")
    value = value.strip()
    if len(value) > 255 or any(
        not (c.isascii() and (c.isalnum() or c == "_")) for c in value
    ):
        raise ValueError("GitHub Token 格式不正确，请粘贴生成的 token")
    return value


def get_token():
    from arknights_mower.utils.network_settings import get_effective_settings

    return get_effective_settings().get("github_token", "")


def is_github_url(url):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in DOWNLOAD_HOSTS | {"api.github.com"}
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def request_github(client, method, url, *, token=None, **kwargs):
    """Attach credentials only to exact official HTTPS hosts.

    Requests removes Authorization on redirects to another host. Never put the
    token in a URL or a session default shared with other services.
    """
    if is_github_url(url):
        token = get_token() if token is None else normalize_token(token)
        if token:
            headers = dict(kwargs.get("headers") or {})
            headers = {
                key: value
                for key, value in headers.items()
                if key.lower() != "authorization"
            }
            headers["Authorization"] = "Bearer " + token
            kwargs["headers"] = headers
            # Prevent a local .netrc from replacing the explicitly selected token.
            kwargs["auth"] = lambda request: request
    return getattr(client, method)(url, **kwargs)


def git_environment(environment, token):
    """Scope Git and LFS authentication to official HTTPS remotes only."""
    environment = dict(environment)
    token = normalize_token(token)
    if token:
        index = int(environment.get("GIT_CONFIG_COUNT", "0"))
        environment[f"GIT_CONFIG_KEY_{index}"] = "http.https://github.com/.extraHeader"
        credential = base64.b64encode(
            ("x-access-token:" + token).encode("ascii")
        ).decode("ascii")
        environment[f"GIT_CONFIG_VALUE_{index}"] = "Authorization: Basic " + credential
        environment["GIT_CONFIG_COUNT"] = str(index + 1)
    return environment


def get_proxy():
    from arknights_mower.utils.network_settings import get_effective_settings

    return get_effective_settings()["github_proxy"]


def download_url(url, proxy=None, *, token=None):
    """Prefix GitHub file URLs; API calls and other hosts stay unchanged."""
    token = get_token() if token is None else normalize_token(token)
    if token and is_github_url(url):
        return url
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


def download_urls(url, proxy=None, *, token=None):
    """Try a configured station, or direct GitHub followed by default stations."""
    proxy = get_proxy() if proxy is None else normalize_proxy(proxy)
    token = get_token() if token is None else normalize_token(token)
    primary = download_url(url, proxy, token=token)
    if token:
        return (primary,)
    if proxy or primary != url or urlsplit(url).hostname not in DOWNLOAD_HOSTS:
        return (primary,)
    candidates = (primary, *(download_url(url, p, token="") for p in FALLBACK_PROXIES))
    return tuple(dict.fromkeys(candidates))


def request_download(client, method, url, *, proxy=None, token=None, **kwargs):
    """Open a GitHub file response, retrying failures via default stations.

    The caller owns the response and must close it. A failure while reading the
    body is reported to the caller, which can discard any partial download.
    """
    import requests

    token = get_token() if token is None else normalize_token(token)
    candidates = download_urls(url, proxy, token=token)
    for index, candidate in enumerate(candidates):
        try:
            response = request_github(client, method, candidate, token=token, **kwargs)
            try:
                response.raise_for_status()
            except requests.HTTPError:
                status = response.status_code
                response.close()
                retryable_status = status in (403, 429) or status >= 500
                if index + 1 == len(candidates) or not retryable_status:
                    raise
                continue
            return response, candidate
        except (requests.ConnectionError, requests.Timeout):
            if index + 1 == len(candidates):
                raise
    raise RuntimeError("没有可用的 GitHub 下载地址")
