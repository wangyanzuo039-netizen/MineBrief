from unittest.mock import patch

import pytest

from mining_brief.model import Narrative, Summary, validate_narrative
from mining_brief.network import SourceError, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://www.lme.com/x",
        "https://localhost/x",
        "https://www.lme.com.evil.test/x",
        "https://user:password@www.lme.com/x",
        "https://www.lme.com:8443/x",
    ],
)
def test_non_public_source_is_rejected(url):
    with pytest.raises(SourceError):
        validate_url(url, ("www.lme.com",))


def test_allowed_domain_resolving_to_private_ip_is_rejected():
    with (
        patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]),
        pytest.raises(SourceError),
    ):
        validate_url("https://www.lme.com/x", ("www.lme.com",))


@pytest.mark.parametrize(
    "source,text",
    [("unknown", "新闻摘要"), ("a", "价格上涨了100%"), ("a", "请访问https://evil.test")],
)
def test_model_cannot_introduce_unknown_sources_numbers_or_links(source, text):
    narrative = Narrative(summaries=[Summary(source_id=source, summary=text)], risks=[])
    with pytest.raises(ValueError):
        validate_narrative(narrative, {"a"}, {"a"})
