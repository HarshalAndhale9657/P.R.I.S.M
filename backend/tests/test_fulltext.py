"""Unit tests for the open-access full-text fetcher (no network — the session is faked)."""
import pymupdf
import pytest

from services.fulltext import FullTextFetcher, url_is_fetchable


def _pdf_bytes(text="Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 540, 200), text, fontsize=11)
    return doc.tobytes()


class _Resp:
    def __init__(self, data: bytes, status=200, url=None, headers=None, chunk=64 * 1024):
        self._data, self.status_code, self.headers, self._chunk = data, status, headers or {}, chunk
        self.url = url or "https://example.org/x.pdf"

    def iter_content(self, chunk_size=None):
        for i in range(0, len(self._data), self._chunk):
            yield self._data[i:i + self._chunk]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Session:
    def __init__(self, responses):
        self.responses = responses   # url -> _Resp | Exception
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.responses[url]
        if isinstance(r, Exception):
            raise r
        return r


def _fetcher(responses, **kw):
    return FullTextFetcher(session=_Session(responses), **kw)


def test_fetches_and_parses_a_pdf():
    url = "https://arxiv.org/pdf/1234.5678v1"
    f = _fetcher({url: _Resp(_pdf_bytes())})
    got = f.fetch(url)
    assert got is not None and "Alpha beta gamma" in got.text and got.page_count == 1 and got.byte_size > 100


def test_rejects_non_pdf_content_regardless_of_headers():
    url = "https://example.org/paper"
    f = _fetcher({url: _Resp(b"<html>Not a PDF</html>", headers={"Content-Type": "application/pdf"})})
    assert f.fetch(url) is None


def test_abandons_oversized_downloads():
    url = "https://example.org/huge.pdf"
    big = b"%PDF-1.7 " + b"x" * (300 * 1024)
    f = _fetcher({url: _Resp(big, chunk=32 * 1024)}, max_bytes=100 * 1024)
    assert f.fetch(url) is None


def test_rejects_declared_oversize_before_reading():
    url = "https://example.org/declared.pdf"
    f = _fetcher({url: _Resp(_pdf_bytes(), headers={"Content-Length": str(10**9)})}, max_bytes=10**6)
    assert f.fetch(url) is None


def test_non_200_and_exceptions_are_none():
    import requests
    ok, bad, boom = "https://a.org/ok.pdf", "https://a.org/404.pdf", "https://a.org/boom.pdf"
    f = _fetcher({ok: _Resp(_pdf_bytes()), bad: _Resp(b"", status=404),
                  boom: requests.ConnectionError("down")})
    assert f.fetch(bad) is None and f.fetch(boom) is None and f.fetch(ok) is not None


def test_results_and_misses_are_cached():
    url = "https://a.org/p.pdf"
    miss = "https://a.org/missing.pdf"
    sess = _Session({url: _Resp(_pdf_bytes()), miss: _Resp(b"", status=404)})
    f = FullTextFetcher(session=sess)
    for target in (url, url, miss, miss):
        f.fetch(target)
    assert sess.calls == [url, miss]        # one network call each


def test_refuses_redirects_into_private_space():
    url = "https://a.org/redirect.pdf"
    f = _fetcher({url: _Resp(_pdf_bytes(), url="http://169.254.169.254/latest/meta-data")})
    assert f.fetch(url) is None


@pytest.mark.parametrize("url,ok", [
    ("https://arxiv.org/pdf/2101.00001", True),
    ("http://export.arxiv.org/pdf/2101.00001", True),
    ("ftp://example.org/x.pdf", False),
    ("https://localhost/x.pdf", False),
    ("http://127.0.0.1:8000/health", False),
    ("http://10.0.0.5/x.pdf", False),
    ("http://192.168.1.1/x.pdf", False),
    ("http://[::1]/x.pdf", False),
    ("http://metadata.google.internal/", False),
    ("not a url", False),
])
def test_url_policy(url, ok):
    assert url_is_fetchable(url) is ok
