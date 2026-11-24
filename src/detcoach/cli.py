"""Practice the writing and speaking tasks of the Duolingo English Test, with feedback."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import feedback, photos, speech, transcribe
from .attempts import Attempts
from .rounds import RoundError, list_rounds, load_round
from .server import serve

ATTEMPT_HELP = "attempt id, or 'latest' for the attempt that finished last (default)"


def find_root(start: Path | None = None) -> Path:
    """The project root is the nearest folder upward that holds rounds/."""
    here = (start or Path.cwd()).resolve()
    for p in (here, *here.parents):
        if (p / "rounds").is_dir():
            return p
    return here


def cmd_practice(args, root: Path) -> int:
    rounds = list_rounds(root / "rounds")
    httpd = serve(root, args.port)
    url = f"http://127.0.0.1:{args.port}/" + (f"#/exam/{args.round}" if args.round else "")
    print(f"det-coach: {len(rounds)} rounds. Practice at {url}")
    print("Answers save to attempts/. Press Ctrl+C to stop.")
    if not speech.available():
        print("Note: no `say` command, so the browser's own voice reads the spoken questions.")
    elif not speech.has_natural_voice():
        print(f"Tip: {speech.VOICE_HELP}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _attempt(root: Path, ref: str):
    attempts = Attempts(root / "attempts")
    aid = attempts.resolve(ref)
    manifest = attempts.manifest(aid)
    rnd = load_round(root / "rounds" / manifest["round"])
    return attempts.path(aid), manifest, rnd


def cmd_transcribe(args, root: Path) -> int:
    base, manifest, rnd = _attempt(root, args.attempt)
    slots = {s.id: s.answer for s in rnd.steps}
    try:
        done = transcribe.transcribe_attempt(base, slots, args.model, args.force)
    except transcribe.NoBackend as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{len(done)} recordings transcribed: {base / 'transcripts.json'}")
    return 0


def cmd_packet(args, root: Path) -> int:
    base, manifest, rnd = _attempt(root, args.attempt)
    if any((base / "recordings").glob("*")):
        slots = {s.id: s.answer for s in rnd.steps}
        try:
            transcribe.transcribe_attempt(
                base, slots, args.model, log=lambda m: print(m, file=sys.stderr)
            )
        except transcribe.NoBackend as e:
            print(f"{e}\nThe packet has the writing answers only.", file=sys.stderr)
    tfile = base / "transcripts.json"
    transcripts = json.loads(tfile.read_text()) if tfile.is_file() else {}
    out = base / "packet.md"
    out.write_text(feedback.build_packet(rnd, base, manifest, transcripts), encoding="utf-8")
    print(out)
    return 0


def cmd_check_feedback(args, root: Path) -> int:
    base, manifest, rnd = _attempt(root, args.attempt)
    fb = feedback.load_feedback(base)
    if fb is None:
        print(f"No feedback.json in {base}", file=sys.stderr)
        return 1
    problems = feedback.check(fb, rnd, manifest)
    for p in problems:
        print(f"- {p}")
    print("feedback.json is valid." if not problems else f"{len(problems)} problems.")
    return 1 if problems else 0


def cmd_check(args, root: Path) -> int:
    bad = 0
    for p in sorted((root / "rounds").iterdir()):
        if not (p / "round.json").is_file():
            continue
        try:
            r = load_round(p)
            print(f"ok   {r.id}: {len(r.steps)} steps, about {r.minutes} min")
        except RoundError as e:
            bad += 1
            print(f"FAIL {p.name}")
            for problem in e.problems:
                print(f"     - {problem}")
    return 1 if bad else 0


def cmd_attempts(args, root: Path) -> int:
    rows = Attempts(root / "attempts").all()
    if not rows:
        print("No attempts yet. Run: det-coach practice")
    for a in rows:
        print(f"{a['id']:40} {a['status']:18} {a['steps']} steps")
    return 0


def cmd_fetch_photo(args, root: Path) -> int:
    folder = root / "rounds" / args.round
    if not folder.is_dir():
        print(f"No round folder {folder}", file=sys.stderr)
        return 1
    name, meta = photos.fetch(args.title, folder / "photos", args.name)
    print(json.dumps({name: meta}, indent=2))
    print(f"Saved photos/{name}. Add the entry above to 'photos' in round.json.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="det-coach", description=__doc__)
    ap.add_argument("--root", type=Path, help="project folder (default: found from cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("practice", help="open the practice app in the browser")
    p.add_argument("--round", help="go straight to this round")
    p.add_argument("--port", type=int, default=8765, help="port to serve on (default: 8765)")
    p.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    p.set_defaults(fn=cmd_practice)

    for name, fn, text in [
        ("transcribe", cmd_transcribe, "transcribe the recordings of an attempt"),
        ("packet", cmd_packet, "transcribe, then write packet.md for the grader"),
    ]:
        p = sub.add_parser(name, help=text)
        p.add_argument("attempt", nargs="?", default="latest", help=ATTEMPT_HELP)
        p.add_argument("--model", help="Whisper model name or path")
        if name == "transcribe":
            p.add_argument("--force", action="store_true", help="transcribe again")
        p.set_defaults(fn=fn)

    p = sub.add_parser("check-feedback", help="validate an attempt's feedback.json")
    p.add_argument("attempt", nargs="?", default="latest", help=ATTEMPT_HELP)
    p.set_defaults(fn=cmd_check_feedback)

    sub.add_parser("check", help="validate every round").set_defaults(fn=cmd_check)
    sub.add_parser("attempts", help="list attempts").set_defaults(fn=cmd_attempts)

    p = sub.add_parser("fetch-photo", help="download a Wikimedia Commons photo into a round")
    p.add_argument("round")
    p.add_argument("title", help='Commons file title, e.g. "File:Bicycle repair.jpg"')
    p.add_argument("--name", help="file name to save as (default: from the title)")
    p.set_defaults(fn=cmd_fetch_photo)

    args = ap.parse_args(argv)
    root = args.root.resolve() if args.root else find_root()
    try:
        return args.fn(args, root)
    except FileNotFoundError as e:
        print(f"Not found: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
