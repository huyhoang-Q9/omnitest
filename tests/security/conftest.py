import pytest


@pytest.fixture(autouse=True)
def _use_db(clean_db: None) -> None:
    """Mọi test trong thư mục này chạy trên DB thật, được làm sạch sau mỗi test."""
