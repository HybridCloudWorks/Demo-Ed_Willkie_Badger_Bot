"""Generate the animated Badger AI mascot clips with Google's Veo video model.

The chat page shows a different short clip depending on what the bot is doing
(frontend/mascot/<state>.mp4). This script made them. Every state clip starts
from the same still of the badger (docs/mascot-originals/reference.png) so the
character stays identical from clip to clip; Veo animates it from that frame.

    python scripts/generate_mascot_video.py --all            # every state, in parallel
    python scripts/generate_mascot_video.py --state thinking # one state again
    python scripts/generate_mascot_video.py --prompt "..." --out take.mp4   # free-form

Needs Google Cloud credentials with Vertex AI access (`gcloud auth login`) and
the project in GOOGLE_CLOUD_PROJECT or --project. One 8-second clip without
audio on Veo 3.1 Fast costs well under a dollar at the time of writing.

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
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "mascot"
REFERENCE = ROOT / "docs" / "mascot-originals" / "reference.png"
MODEL = "veo-3.1-fast-generate-001"
REGION = "us-central1"

CHARACTER = (
    "The same friendly cartoon badger mascot as in the picture: black and white "
    "striped face, bright cardinal red hoodie with a white letter W, centered on a "
    "plain solid white background, 2D-animation look with clean bold outlines, "
    "bright even lighting, no text other than the W, no watermark, no people. "
)
END = " At the end it returns to the exact starting pose so the clip loops cleanly."

# What the badger does in each state the chat page can be in.
STATES: dict[str, str] = {
    "wave": CHARACTER + "It waves happily at the camera, then gives an enthusiastic thumbs up and a big confident smile." + END,
    "idle": CHARACTER + "It stands relaxed, breathing gently, blinks, glances left and right with curiosity, and gives a small friendly smile. Calm, subtle motion." + END,
    "listening": CHARACTER + "It leans toward the camera, cups one paw behind its ear and raises its eyebrows, listening carefully and nodding slightly." + END,
    "thinking": CHARACTER + "It taps its chin with one paw, looks up and to the side as if thinking hard, then taps its foot, then looks back at the camera." + END,
    "found": CHARACTER + "It lights up with excitement, pumps a fist, claps its paws together and gives two big thumbs up with a huge grin." + END,
    "notfound": CHARACTER + "It shrugs with both palms up, tilts its head and gives an apologetic smile, then shakes its head gently." + END,
    "talking": CHARACTER + "It talks to the camera, mouth moving, gesturing with its paws like a friendly presenter explaining something." + END,
}


def access_token() -> str:
    """Use the signed-in gcloud identity; no key file needed."""
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True, shell=os.name == "nt").strip()
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


def generate(project: str, prompt: str, seconds: int, first_frame: Path | None, label: str = "") -> bytes:
    base = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{REGION}/publishers/google/models/{MODEL}"
    instance: dict = {"prompt": prompt}
    if first_frame:
        instance["image"] = {"bytesBase64Encoded": base64.b64encode(first_frame.read_bytes()).decode(), "mimeType": "image/png"}
    op = call(
        f"{base}:predictLongRunning",
        {
            "instances": [instance],
            "parameters": {
                "aspectRatio": "16:9",
                "sampleCount": 1,
                "durationSeconds": seconds,
                "generateAudio": False,
                "resolution": "720p",
                "personGeneration": "dont_allow",
            },
        },
        access_token(),
    )
    name = op["name"]
    print(f"[{label}] Veo job started: {name.rsplit('/', 1)[-1]}")
    for _ in range(60):
        time.sleep(15)
        result = call(f"{base}:fetchPredictOperation", {"operationName": name}, access_token())
        if result.get("done"):
            break
    else:
        raise RuntimeError(f"[{label}] timed out waiting for Veo")
    if "error" in result:
        raise RuntimeError(f"[{label}] Veo error: {result['error']}")
    response = result.get("response", {})
    videos = response.get("videos") or []
    if not videos:
        raise RuntimeError(f"[{label}] no video returned (filtered: {response.get('raiMediaFilteredCount')}, {response.get('raiMediaFilteredReasons')})")
    return base64.b64decode(videos[0]["bytesBase64Encoded"])


def ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg  # optional: pip install imageio-ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def web_copy(src: Path, dst: Path) -> None:
    """Square crop around the badger, 480x480, small file, plus a poster frame."""
    ff = ffmpeg()
    try:
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-vf", "crop=720:720:280:0,scale=480:480",
                        "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p", "-crf", "27", "-preset", "slow",
                        "-movflags", "+faststart", "-an", str(dst)], check=True)
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(dst), "-frames:v", "1", "-q:v", "4", str(dst.with_suffix(".jpg"))], check=True)
        print("wrote", dst, f"({dst.stat().st_size / 1e3:.0f} KB)")
    except (OSError, subprocess.CalledProcessError) as exc:
        dst.write_bytes(src.read_bytes())
        print(f"ffmpeg unavailable ({exc}); copied the full-size clip to {dst}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="Google Cloud project ID")
    ap.add_argument("--all", action="store_true", help="generate every state clip")
    ap.add_argument("--state", choices=sorted(STATES), action="append", help="generate this state (repeatable)")
    ap.add_argument("--prompt", help="free-form prompt instead of a state")
    ap.add_argument("--no-reference", action="store_true", help="text-to-video without the reference frame")
    ap.add_argument("--seconds", type=int, default=8, choices=(4, 6, 8))
    ap.add_argument("--out", type=Path, help="output file for --prompt")
    args = ap.parse_args()
    if not args.project:
        sys.exit("Set GOOGLE_CLOUD_PROJECT or pass --project.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "mascot-originals").mkdir(parents=True, exist_ok=True)
    reference = None if args.no_reference else (REFERENCE if REFERENCE.exists() else None)
    if reference is None and not args.no_reference:
        print("No docs/mascot-originals/reference.png yet: the first clip is text-only; its first frame becomes the reference.")

    jobs: list[tuple[str, str, Path]] = []
    if args.prompt:
        jobs.append(("custom", args.prompt, args.out or OUT_DIR / "custom.mp4"))
    for state in (sorted(STATES) if args.all else (args.state or [])):
        jobs.append((state, STATES[state], OUT_DIR / f"{state}.mp4"))
    if not jobs:
        ap.error("nothing to do: pass --all, --state NAME or --prompt TEXT")

    errors: list[str] = []

    def run(label: str, prompt: str, out: Path) -> None:
        try:
            data = generate(args.project, prompt, args.seconds, reference, label)
            original = ROOT / "docs" / "mascot-originals" / f"{label}.mp4"
            original.write_bytes(data)
            web_copy(original, out)
        except Exception as exc:  # noqa: BLE001 - report every failure, keep the others going
            errors.append(f"{label}: {exc}")

    threads = [threading.Thread(target=run, args=j, daemon=True) for j in jobs]
    for t in threads:
        t.start()
        time.sleep(2)  # stagger the submissions a little
    for t in threads:
        t.join()
    for e in errors:
        print("FAILED", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
