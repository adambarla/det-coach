"""Compare blind grades with the official subscores.

Usage: python tools/calibration/compare.py <dir> <grades.json> [<grades.json> ...]

Each grades file is a list of {"id", "estimate", "band"} written by one blind grader.
"""

import json
import statistics as st
import sys
from pathlib import Path


def main() -> None:
    d = Path(sys.argv[1])
    key = {x["id"]: x for x in json.loads((d / "key.json").read_text())}
    graders = {
        Path(p).stem: {x["id"]: x for x in json.loads(Path(p).read_text())} for p in sys.argv[2:]
    }
    for name, g in graders.items():
        print(name)
        for label, ids in (
            ("all", list(key)),
            ("held out", [i for i in key if key[i]["held_out"]]),
            ("anchored", [i for i in key if not key[i]["held_out"]]),
        ):
            err = [g[i]["estimate"] - key[i]["score"] for i in ids]
            inside = sum(g[i]["band"][0] <= key[i]["score"] <= g[i]["band"][1] for i in ids)
            print(
                f"  {label:9} n={len(ids):2}  mean error {st.mean(err):+5.1f}"
                f"  mean absolute error {st.mean(map(abs, err)):4.1f}"
                f"  within 10 points {sum(abs(e) <= 10 for e in err)}/{len(ids)}"
                f"  official score in band {inside}/{len(ids)}"
            )
        official = [key[i]["score"] for i in key]
        print(f"  correlation {st.correlation(official, [g[i]['estimate'] for i in key]):.2f}")


if __name__ == "__main__":
    main()
