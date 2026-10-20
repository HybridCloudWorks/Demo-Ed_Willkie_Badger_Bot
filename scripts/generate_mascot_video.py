"""Generate the animated Badger AI mascot with Google's Veo video model.

This is how frontend/badger.mp4 was made. Run it again to get a new take:

    python scripts/generate_mascot_video.py                 # writes frontend/badger.mp4 + badger.jpg
    python scripts/generate_mascot_video.py --prompt "..."  # your own description
    python scripts/generate_mascot_video.py --out /tmp/take2.mp4

Needs Google Cloud credentials with Vertex AI access (`gcloud auth
application-default login` or `gcloud auth login`) and the project in
GOOGLE_CLOUD_PROJECT or --project. One 8-second clip without audio on Veo 3.1
Fast costs well under a dollar at the time of writing; check the pricing page.

The mascot is an original cartoon badger in the school colors. It is not the
school's official logo and no trademark is used.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "veo-3.1-fast-generate-001"
REGION = "us-central1"

DEFAULT_PROMPT = (
    "A friendly cartoon badger mascot for a middle school, 2D animated style with "
    "clean bold outlines. The badger has a black and white striped face, wears a "
    "bright cardinal red hoodie with a white letter W, and stands centered on a "
    "plain solid white background. It waves happily at the camera, then gives an "
    "enthusiastic thumbs up and a big confident smile. Smooth looping animation, "
    "bright even lighting, no text other than the W, no watermark, no people."
)


def access_token() -> str:
    """Use the signed-in gcloud identity; no key file needed."""
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Could not get a Google Cloud access token from gcloud: {exc}")


def call(url: str, body: dict, token: str) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def generate(project: str, prompt: str, seconds: int) -> bytes:
    base = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{REGION}/publishers/google/models/{MODEL}"
    token = access_token()
    op = call(
        f"{base}:predictLongRunning",
        {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "aspectRatio": "16:9",
                "sampleCount": 1,
                "durationSeconds": seconds,
                "generateAudio": False,
                "resolution": "720p",
                "personGeneration": "dont_allow",
            },
        },
        token,
    )
    name = op["name"]
    print("Veo job started:", name.rsplit("/", 1)[-1])
    for _ in range(60):
        time.sleep(15)
        result = call(f"{base}:fetchPredictOperation", {"operationName": name}, access_token())
        if result.get("done"):
            break
        print("  still rendering...")
    else:
        sys.exit("Timed out waiting for Veo.")
    if "error" in result:
        sys.exit(f"Veo error: {result['error']}")
    response = result.get("response", {})
    videos = response.get("videos") or []
    if not videos:
        sys.exit(f"No video returned (filtered: {response.get('raiMediaFilteredCount')}, {response.get('raiMediaFilteredReasons')})")
    return base64.b64decode(videos[0]["bytesBase64Encoded"])


def poster_frame(video: Path, poster: Path) -> None:
    """First frame as JPEG for the <video poster>; skipped quietly if ffmpeg is missing."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(poster)],
            check=True,
        )
        print("wrote", poster)
    except (OSError, subprocess.CalledProcessError):
        print("ffmpeg not available; poster image not written (the page still works).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="Google Cloud project ID")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--seconds", type=int, default=8, choices=(4, 6, 8))
    ap.add_argument("--out", type=Path, default=ROOT / "frontend" / "badger.mp4")
    args = ap.parse_args()
    if not args.project:
        sys.exit("Set GOOGLE_CLOUD_PROJECT or pass --project.")
    data = generate(args.project, args.prompt, args.seconds)
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data) / 1e6:.1f} MB)")
    poster_frame(args.out, args.out.with_suffix(".jpg"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
