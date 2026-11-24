import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PHOTO = {"title": "t.jpg", "author": "someone", "license": "CC0", "source": "https://example.org"}


def write_round(root: Path, round_id: str = "round-x", tasks: list | None = None) -> Path:
    """A small valid round without spoken steps, so tests never call `say`."""
    folder = root / "rounds" / round_id
    (folder / "photos").mkdir(parents=True)
    (folder / "photos" / "p.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    data = {
        "id": round_id,
        "title": "Test round",
        "tasks": tasks
        if tasks is not None
        else [
            {"id": "photo-1", "type": "write_photo", "photo": "p.jpg"},
            {"id": "iw", "type": "interactive_writing", "prompt": "Q?", "follow_up": "F?"},
            {"id": "read-speak", "type": "read_then_speak", "prompt": "Talk.", "bullets": ["a"]},
        ],
        "photos": {"p.jpg": PHOTO},
    }
    (folder / "round.json").write_text(json.dumps(data))
    return folder


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write_round(tmp_path)
    return tmp_path
