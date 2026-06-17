import base64
import hashlib
from qrtrans.chunker import split, reassemble, Chunk

def test_empty_file_single_chunk():
    chunks = split(b"", 1300)
    assert len(chunks) == 1
    assert chunks[0].ci == 0 and chunks[0].tc == 1
    complete, data, sha = reassemble(chunks)
    assert complete and data == b""
    assert sha == hashlib.sha256(b"").hexdigest()

def test_small_file_single_chunk():
    content = b"hello world"
    chunks = split(content, 1300)
    assert len(chunks) == 1
    assert chunks[0].tc == 1
    complete, data, sha = reassemble(chunks)
    assert complete and data == content
    assert sha == hashlib.sha256(content).hexdigest()

def test_long_file_multiple_chunks():
    content = b"x" * 3000
    chunks = split(content, 1300)
    assert len(chunks) == 3   # 1300+1300+400
    assert [c.ci for c in chunks] == [0, 1, 2]
    assert all(c.tc == 3 for c in chunks)
    assert all(c.sha256 == hashlib.sha256(content).hexdigest() for c in chunks)
    complete, data, sha = reassemble(chunks)
    assert complete and data == content

def test_exact_boundary():
    content = b"y" * 2600  # exactly 2 chunks of 1300
    chunks = split(content, 1300)
    assert len(chunks) == 2
    complete, data, _ = reassemble(chunks)
    assert complete and data == content

def test_reassemble_missing_chunk_incomplete():
    content = b"z" * 3000
    chunks = split(content, 1300)
    incomplete = chunks[:2]  # drop last
    complete, data, sha = reassemble(chunks)
    # 先验证完整
    assert complete and data == content
    # 再验证不完整
    complete2, data2, sha2 = reassemble(incomplete)
    assert not complete2
    assert sha2 == hashlib.sha256(content).hexdigest()

def test_chunk_data_is_base64():
    chunks = split(b"abc", 1300)
    assert base64.b64decode(chunks[0].data_b64) == b"abc"

def test_reassemble_out_of_order():
    # QR 扫码顺序不确定，reassemble 必须能处理任意顺序
    content = b"x" * 3000
    chunks = split(content, 1300)   # 3 块
    shuffled = [chunks[2], chunks[0], chunks[1]]
    complete, data, sha = reassemble(shuffled)
    assert complete
    assert data == content
    assert sha == hashlib.sha256(content).hexdigest()
