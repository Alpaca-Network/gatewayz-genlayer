"""Does gatewayz-backend's pinned copy of fixtures/usage-v2.json still match ours?

The backend replays tests/fixtures/genlayer_usage_v2.json in CI. If this repo
regenerates the fixture (a hashing or line-format change) and the backend copy is
not updated, the backend's tests keep passing while every proof it serves fails
here. Reads both files through `gh api` (the backend repo is private), so it
needs a logged-in gh. Prints one JSON line; exit 1 on drift.
"""

import hashlib
import json
import subprocess
import sys

OURS = ("Alpaca-Network/gatewayz-genlayer", "fixtures/usage-v2.json", ["main", "feat/cost-dispute-p1"])
THEIRS = (
    "Alpaca-Network/gatewayz-backend",
    "tests/fixtures/genlayer_usage_v2.json",
    ["main", "feat/genlayer-inference-escrow", "feat/cost-dispute-usage-v2"],
)


def _fetch(repo: str, path: str, refs: list[str]) -> tuple[str | None, bytes | None]:
    for ref in refs:
        p = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}?ref={ref}"],
            capture_output=True,
            timeout=30,
        )
        if p.returncode == 0 and p.stdout:
            return ref, p.stdout
    return None, None


def main() -> int:
    try:
        our_ref, ours = _fetch(*OURS)
        their_ref, theirs = _fetch(*THEIRS)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"gh failed: {e}"}))
        return 2
    out = {"ours_ref": our_ref, "theirs_ref": their_ref}
    if ours is None or theirs is None:
        print(json.dumps({**out, "ok": False, "error": "fixture not found on any ref"}))
        return 2
    a, b = hashlib.sha256(ours).hexdigest(), hashlib.sha256(theirs).hexdigest()
    same = a == b
    print(json.dumps({**out, "ok": True, "same": same, "ours": a[:12], "theirs": b[:12]}))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
