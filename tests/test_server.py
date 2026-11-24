import json
import threading
import urllib.error
import urllib.request

import pytest
from conftest import write_round

from detcoach.server import serve


@pytest.fixture
def base(root):
    httpd = serve(root, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def request(url, data=None, ctype="application/json", method=None, **headers):
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": ctype, **headers}, method=method
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_app_and_rounds(base):
    status, body = request(base + "/")
    assert status == 200 and b"<main" in body
    status, body = request(base + "/api/rounds")
    assert json.loads(body)[0]["id"] == "round-x"
    status, body = request(base + "/rounds/round-x/photos/p.jpg")
    assert status == 200


def test_full_attempt(base):
    _, body = request(base + "/api/attempts", json.dumps({"round": "round-x"}).encode())
    aid = json.loads(body)["id"]
    step = f"{base}/api/attempts/{aid}/steps"
    assert request(f"{step}/photo-1?final=1&seconds=42.0", b"Hello.", "text/plain")[0] == 200
    assert request(f"{step}/read-speak?final=1&seconds=80", b"\x00", "audio/webm")[0] == 200
    assert request(f"{step}/nope?final=1", b"x", "text/plain")[0] == 400
    assert request(f"{step}/iw-1?final=1", b"x", "image/png")[0] == 400
    assert request(f"{base}/api/attempts/{aid}/finish", b"")[0] == 200

    detail = json.loads(request(f"{base}/api/attempts/{aid}")[1])
    assert detail["status"] == "awaiting_feedback"
    assert detail["answers"] == {"photo-1": "Hello."}
    assert detail["manifest"]["steps"]["photo-1"]["seconds"] == 42.0
    assert request(base + detail["recordings"]["read-speak"])[0] == 200


def test_section_attempt(base):
    data = json.dumps({"round": "round-x", "section": "writing"}).encode()
    aid = json.loads(request(base + "/api/attempts", data)[1])["id"]
    assert json.loads(request(f"{base}/api/attempts/{aid}")[1])["manifest"]["section"] == "writing"
    bad = json.dumps({"round": "round-x", "section": "maths"}).encode()
    assert request(base + "/api/attempts", bad)[0] == 400


def test_delete_attempt(base):
    aid = json.loads(request(base + "/api/attempts", b'{"round": "round-x"}')[1])["id"]
    url = f"{base}/api/attempts/{aid}"
    assert request(url, method="DELETE", Origin="http://evil.example")[0] == 403
    assert request(url)[0] == 200
    assert request(url, method="DELETE")[0] == 200
    assert request(url)[0] == 404
    assert request(url, method="DELETE")[0] == 404
    assert request(f"{base}/api/attempts/..", method="DELETE")[0] in (400, 404)


@pytest.mark.parametrize(
    "path, code",
    [
        ("/static/..%2Fserver.py", 400),
        ("/rounds/round-x/photos/missing.jpg", 404),
        ("/api/rounds/nope", 404),
        ("/api/attempts/nope", 404),
        ("/api/audio/round-x/photo-1.m4a", 404),  # a step without speech
    ],
)
def test_bad_requests(base, path, code):
    assert request(base + path)[0] == code


def test_draft_never_replaces_a_submitted_answer(base):
    _, body = request(base + "/api/attempts", json.dumps({"round": "round-x"}).encode())
    aid = json.loads(body)["id"]
    step = f"{base}/api/attempts/{aid}/steps/photo-1"
    request(f"{step}?final=0", b"draft", "text/plain")
    request(f"{step}?final=1", b"final", "text/plain")
    request(f"{step}?final=0", b"late draft", "text/plain")
    assert json.loads(request(f"{base}/api/attempts/{aid}")[1])["answers"]["photo-1"] == "final"


def test_other_sites_are_refused(base):
    port = base.rsplit(":", 1)[1]
    assert request(base + "/api/attempts", Host="evil.example")[0] == 403
    data = json.dumps({"round": "round-x"}).encode()
    assert request(base + "/api/attempts", data, Origin="https://evil.example")[0] == 403
    assert request(base + "/api/attempts", data, Origin=f"http://localhost:{port}")[0] == 200


def test_byte_ranges(base):
    url = base + "/rounds/round-x/photos/p.jpg"  # 4 bytes
    req = urllib.request.Request(url, headers={"Range": "bytes=1-"})
    with urllib.request.urlopen(req) as r:
        assert r.status == 206
        assert r.headers["Content-Range"] == "bytes 1-3/4"
        assert r.read() == b"\xd8\xff\xd9"
    assert request(url, Range="bytes=9-")[0] == 416


def test_reading_answers_are_saved_as_json_and_scored(tmp_path):
    words = [{"word": "cat", "real": True}, {"word": "blorp", "real": False}]
    write_round(tmp_path, tasks=[{"id": "select", "type": "read_select", "words": words}])
    httpd = serve(tmp_path, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        _, body = request(url + "/api/attempts", json.dumps({"round": "round-x"}).encode())
        aid = json.loads(body)["id"]
        step = f"{url}/api/attempts/{aid}/steps"
        assert request(f"{step}/select-1?final=1&seconds=2", b'{"real": true}')[0] == 200
        assert request(f"{step}/select-2?final=1&seconds=5", b'{"real": true}')[0] == 200
        assert request(f"{step}/select-1?final=1", b"not json")[0] == 400
        detail = json.loads(request(f"{url}/api/attempts/{aid}")[1])
        assert detail["scores"]["select-1"]["credit"] == 1
        assert detail["scores"]["select-2"]["credit"] == 0
        assert detail["skills"]["reading"] == {"credit": 1.0, "points": 2, "share": 0.5}
    finally:
        httpd.shutdown()
