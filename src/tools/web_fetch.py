"""抓取公开网页，禁止访问本机和内网地址。"""
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def check(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("仅支持 HTTP/HTTPS 地址")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("不允许访问本机或非公网地址")


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def run(url):
    check(url)
    opener = build_opener(SafeRedirect())
    with opener.open(Request(url, headers={"User-Agent": "doc-agent/0.1"}), timeout=8) as response:
        raw = response.read(200000)
        html = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    parser = Text()
    parser.feed(html)
    return " ".join(parser.parts)[:12000]
