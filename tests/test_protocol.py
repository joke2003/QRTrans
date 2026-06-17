import json
import pytest
from qrtrans.protocol import (
    Payload, MAGIC, PROTOCOL_VERSION, ProtocolError,
    make_file_payload, make_dir_payload, validate, is_safe_relpath,
)

def _file_payload(**over):
    base = dict(magic=MAGIC, ver=PROTOCOL_VERSION, batch="abc12345",
                type="file", fid="f00", fn="a.txt", path="a.txt",
                ci=0, tc=1, enc="b64", sha256="x"*64, data="SGVsbG8=")
    base.update(over)
    return Payload(**base)

def test_payload_roundtrip_json():
    p = _file_payload()
    s = p.to_json()
    assert isinstance(s, str)
    p2 = Payload.from_json(s)
    assert p2 == p

def test_validate_accepts_good_payload():
    validate(_file_payload())  # no raise

def test_validate_rejects_bad_magic():
    with pytest.raises(ProtocolError):
        validate(_file_payload(magic="XXX"))

def test_validate_rejects_unsupported_version():
    with pytest.raises(ProtocolError):
        validate(_file_payload(ver=999))

def test_validate_rejects_traversal_path():
    with pytest.raises(ProtocolError):
        validate(_file_payload(path="../etc/passwd"))

def test_validate_rejects_absolute_path():
    with pytest.raises(ProtocolError):
        validate(_file_payload(path="/etc/passwd"))

def test_is_safe_relpath():
    assert is_safe_relpath("a/b.txt")
    assert is_safe_relpath("a.txt")
    assert not is_safe_relpath("../a")
    assert not is_safe_relpath("/a")
    assert not is_safe_relpath("a/../../b")

def test_make_file_payload_sets_fields():
    p = make_file_payload(
        batch="abc12345", fid="f00", relpath="docs/a.txt",
        fn="a.txt", ci=0, tc=2, sha256="d"*64, data_b64="SGk=",
    )
    assert p.type == "file"
    assert p.path == "docs/a.txt"
    assert p.enc == "b64"

def test_make_dir_payload_marks_empty_dir():
    p = make_dir_payload(batch="abc12345", fid="d00", relpath="empty/", fn="")
    assert p.type == "dir"
    assert p.tc == 1 and p.ci == 0
    assert p.data == "" and p.sha256 == ""
    assert p.path == "empty/"

def test_validate_rejects_file_with_empty_sha256():
    with pytest.raises(ProtocolError):
        validate(_file_payload(sha256=""))

def test_validate_rejects_file_path_ending_with_slash():
    with pytest.raises(ProtocolError):
        validate(_file_payload(path="adir/"))

def test_validate_accepts_file_with_empty_data_for_empty_file():
    # 空文件的唯一分块 data 为 ""，必须被接受
    validate(_file_payload(data=""))

def test_validate_rejects_dir_with_nonempty_data():
    d = Payload(magic=MAGIC, ver=PROTOCOL_VERSION, batch="abc12345",
                type="dir", fid="d00", fn="", path="empty/",
                ci=0, tc=1, enc="b64", sha256="", data="AAAA")
    with pytest.raises(ProtocolError):
        validate(d)

def test_validate_rejects_bad_ci_tc_boundary():
    with pytest.raises(ProtocolError):
        validate(_file_payload(ci=1, tc=1))   # ci == tc
    with pytest.raises(ProtocolError):
        validate(_file_payload(tc=0))         # tc < 1
    with pytest.raises(ProtocolError):
        validate(_file_payload(ci=-1, tc=2))  # ci < 0

def test_from_json_raises_protocol_error_on_bad_input():
    with pytest.raises(ProtocolError):
        Payload.from_json("{not json")
    with pytest.raises(ProtocolError):
        Payload.from_json('{"magic":"QRT"}')  # 缺字段 -> TypeError 被包裹
