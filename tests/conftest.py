import pytest

@pytest.fixture
def sample_text():
    return "Hello, QRTrans!\n"

@pytest.fixture
def long_text():
    return "Q" * 5000  # > 1300 字节，需要多块
