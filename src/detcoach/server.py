"""Local web server for the practice app. Binds to 127.0.0.1 only and uses the stdlib.

Routes
    GET  /                                  the app (static/index.html)
    GET  /static/<file>                     app assets
    GET  /rounds/<round>/photos/<file>      round photos
    GET  /api/rounds                        round summaries
    GET  /api/rounds/<round>                one round, expanded into steps
    GET  /api/audio/<round>/<step>.m4a      spoken question or conversation (404: use Web Speech)
    GET  /api/attempts                      attempt summaries
    GET  /api/attempts/<id>                 manifest, answers, transcripts and feedback
    GET  /attempts/<id>/recordings/<file>   a recording, for playback on the results page
    POST /api/attempts                      {"round": id, "section"?: name} -> {"id": attempt id}
    POST /api/attempts/<id>/steps/<step>    body = text/plain answer or audio/* recording
    POST /api/attempts/<id>/finish
"""

from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import feedback, score, speech
from .attempts import Attempts
from .rounds import FILE_NAME, Round, RoundError, list_rounds, load_round
from .tasks import SECTIONS

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 50 * 1024 * 1024
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class App:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.rounds_dir = self.root / "rounds"
        self.attempts = Attempts(self.root / "attempts")
        self.cache = self.root / ".cache" / "audio"

    def round(self, round_id: str) -> Round:
        if not FILE_NAME.match(round_id) or not (self.rounds_dir / round_id).is_dir():
            raise FileNotFoundError(round_id)
        return load_round(self.rounds_dir / round_id)

    def attempt_detail(self, attempt_id: str) -> dict:
        base = self.attempts.path(attempt_id)
        manifest = self.attempts.manifest(attempt_id)
        answers = {
            p.stem: p.read_text(encoding="utf-8")
            for p in (base / "answers").glob("*")
            if p.suffix in (".txt", ".json")
        }
        recordings = {
            p.stem: f"/attempts/{attempt_id}/recordings/{p.name}"
            for p in (base / "recordings").glob("*")
        }
        tfile = base / "transcripts.json"
        transcripts = json.loads(tfile.read_text()) if tfile.is_file() else {}
        rnd = self.round(manifest["round"])
        scores = score.score_attempt(rnd, base, manifest)
        status = self.attempts.status(attempt_id)
        fb = feedback.load_feedback(base)
        if fb is not None and feedback.check(fb, rnd, manifest):
            # The grader is still writing or fixing feedback.json. Keep the page waiting.
            fb, status = None, "awaiting_feedback"
        return {
            "manifest": manifest,
            "status": status,
            "round": rnd.public(),
            "answers": answers,
            "recordings": recordings,
            "transcripts": {
                k: {
                    "text": v["text"],
                    "metrics": v["metrics"],
                    "marked": feedback.marked_transcript(v["words"]),
                }
                for k, v in transcripts.items()
            },
            "feedback": fb,
            "scores": scores,
            "skills": score.summary(scores, {s.id: s for s in rnd.steps}),
        }


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "det-coach"

        def log_message(self, *args) -> None:  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, crange: str = "") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            if crange:
                self.send_header("Content-Range", crange)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def _file(self, path: Path) -> None:
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            data = path.read_bytes()
            # Safari only plays audio from servers that answer byte range requests.
            m = RANGE.match(self.headers.get("Range", ""))
            if not m or not data:
                return self._send(200, data, ctype)
            start, end = m.groups()
            if start:
                first, last = int(start), min(int(end or len(data) - 1), len(data) - 1)
            else:
                first, last = max(len(data) - int(end or 0), 0), len(data) - 1
            if first > last:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            self._send(206, data[first : last + 1], ctype, f"bytes {first}-{last}/{len(data)}")

        def _error(self, code: int, message: str) -> None:
            self._json({"error": message}, code)

        def _parts(self) -> list[str] | None:
            """Path segments, or None after an error response.

            Only pages that this server serves may use it. The Host check stops DNS
            rebinding, and the Origin check stops other sites that post to localhost.
            """
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in hosts or (
                origin is not None and origin.removeprefix("http://") not in hosts
            ):
                self._error(403, "forbidden")
                return None
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if not all(FILE_NAME.match(p) for p in parts):
                self._error(400, "bad path")
                return None
            return parts

        def do_GET(self) -> None:  # noqa: N802
            if (parts := self._parts()) is None:
                return
            try:
                self._route_get(parts)
            except (FileNotFoundError, KeyError):
                self._error(404, "not found")
            except RoundError as e:
                self._error(500, str(e))

        def _route_get(self, parts: list[str]) -> None:
            match parts:
                case []:
                    self._file(STATIC / "index.html")
                case ["static", name] if (STATIC / name).is_file():
                    self._file(STATIC / name)
                case ["rounds", rid, "photos", name] if (
                    app.rounds_dir / rid / "photos" / name
                ).is_file():
                    self._file(app.rounds_dir / rid / "photos" / name)
                case ["api", "rounds"]:
                    self._json([r.summary() for r in list_rounds(app.rounds_dir)])
                case ["api", "rounds", rid]:
                    self._json(app.round(rid).public())
                case ["api", "audio", rid, name] if name.endswith(".m4a"):
                    path = speech.audio_path(app.cache, app.round(rid), name[:-4])
                    if path is None:
                        raise FileNotFoundError(name)
                    self._file(path)
                case ["api", "attempts"]:
                    self._json(app.attempts.all())
                case ["api", "attempts", aid]:
                    self._json(app.attempt_detail(aid))
                case ["attempts", aid, "recordings", name]:
                    path = app.attempts.path(aid) / "recordings" / name
                    if not path.is_file():
                        raise FileNotFoundError(name)
                    self._file(path)
                case _:
                    raise FileNotFoundError(self.path)

        def do_POST(self) -> None:  # noqa: N802
            if (parts := self._parts()) is None:
                return
            url = urlparse(self.path)
            length = self.headers.get("Content-Length", "0")
            if not length.isdigit():
                return self._error(411, "length required")
            size = int(length)
            if size > MAX_UPLOAD:
                return self._error(413, "too large")
            body = self.rfile.read(size)
            try:
                match parts:
                    case ["api", "attempts"]:
                        req = json.loads(body or b"{}")
                        rnd = app.round(req.get("round", ""))
                        section = req.get("section", "")
                        if section and section not in SECTIONS:
                            return self._error(400, "unknown section")
                        speech.prerender(app.cache, rnd)
                        self._json({"id": app.attempts.create(rnd.id, section)})
                    case ["api", "attempts", aid, "steps", sid]:
                        rnd = app.round(app.attempts.manifest(aid)["round"])
                        if sid not in {s.id for s in rnd.steps}:
                            return self._error(400, f"unknown step {sid}")
                        q = parse_qs(url.query)
                        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
                        seconds = float(q["seconds"][0]) if "seconds" in q else None
                        final = q.get("final", ["0"])[0] == "1"
                        out = app.attempts.save(aid, sid, body, ctype, final, seconds)
                        if final:
                            print(f"  saved {aid}/{out.parent.name}/{out.name}", flush=True)
                        self._json({"saved": out.name})
                    case ["api", "attempts", aid, "finish"]:
                        app.attempts.finish(aid)
                        print(f"Attempt {aid} finished. Ask your agent to grade it.", flush=True)
                        self._json({"ok": True})
                    case _:
                        self._error(404, "not found")
            except FileNotFoundError:
                self._error(404, "not found")
            except (ValueError, json.JSONDecodeError) as e:
                self._error(400, str(e))

    return Handler


def serve(root: Path, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(App(root)))
