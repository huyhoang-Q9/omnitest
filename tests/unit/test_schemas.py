import pytest
from pydantic import ValidationError

from omnitest_api.schemas import EnvironmentCreate, ProjectCreate, VariableCreate


def test_project_key_normalized() -> None:
    assert ProjectCreate(key=" shop1 ", name="Shop").key == "SHOP1"


@pytest.mark.parametrize("key", ["A", "1ABC", "AB-C", "ABCDEFGHIJKLMNOPQ"])
def test_project_key_invalid(key: str) -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(key=key, name="x")


@pytest.mark.parametrize(
    "url", ["ftp://a.com", "javascript:alert(1)", "http://", "https://user:pass@a.com", "a.com"]
)
def test_environment_base_url_invalid(url: str) -> None:
    with pytest.raises(ValidationError):
        EnvironmentCreate(name="Dev", kind="dev", base_url=url)


def test_environment_hosts_normalized() -> None:
    e = EnvironmentCreate(
        name="Dev",
        kind="dev",
        base_url="https://a.com",
        allowed_hosts=["A.com", " a.com ", "*.b.vn:8443"],
    )
    assert e.allowed_hosts == ["*.b.vn:8443", "a.com"]


@pytest.mark.parametrize("key", ["lower", "1ABC", "A-B", ""])
def test_variable_key_invalid(key: str) -> None:
    with pytest.raises(ValidationError):
        VariableCreate(key=key, value="v")


@pytest.mark.parametrize(
    "email", ["admin@omnitest.local", "QA@Cong-Ty.internal", "a.b+c@sub.example.vn"]
)
def test_internal_domains_accepted_and_lowercased(email: str) -> None:
    from omnitest_api.schemas import MemberIn

    assert MemberIn(email=email, role="viewer").email == email.lower()


@pytest.mark.parametrize("email", ["no-at", "a@b", "a@@b.vn", "a b@c.vn", "a@-x.vn"])
def test_invalid_emails_rejected(email: str) -> None:
    from omnitest_api.schemas import MemberIn

    with pytest.raises(ValidationError):
        MemberIn(email=email, role="viewer")
