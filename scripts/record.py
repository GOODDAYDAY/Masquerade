"""Record a game replay as video with audio.

Usage:
    python scripts/record.py <script_json_filename>

Approach: CDP screencast (non-blocking) + ffmpeg.
  1. Start frontend, open browser, auto-play script
  2. Use Chrome DevTools Protocol screencast to capture frames
     WITHOUT blocking the page's event loop
  3. Wait for #playback-complete DOM marker
  4. ffmpeg stitches frames + merges TTS audio → mp4

Prerequisites:
    pip install playwright
    python -m playwright install chromium
    ffmpeg
"""

import asyncio
import atexit
import base64
import json
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Run:")
    print("  pip install playwright")
    print("  python -m playwright install chromium")
    sys.exit(1)

if not shutil.which("ffmpeg"):
    print("ffmpeg required. Install: https://ffmpeg.org/download.html")
    sys.exit(1)

FRONTEND_URL = "http://localhost:5173"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
OUTPUT_DIR = Path("output/videos")
FRAMES_DIR = OUTPUT_DIR / "_frames"
MAX_WAIT_SECONDS = 7200
TEXT_SPEED = 15
FPS = 5

_frontend_process = None


def _cleanup():
    global _frontend_process
    if _frontend_process and _frontend_process.poll() is None:
        _frontend_process.terminate()
        try:
            _frontend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _frontend_process.kill()
        _frontend_process = None


atexit.register(_cleanup)


def _start_frontend():
    global _frontend_process
    print("Starting frontend dev server...")
    _frontend_process = subprocess.Popen(
        ["npm", "run", "dev"], cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        shell=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print("Waiting for frontend...")
    for _ in range(60):
        try:
            urllib.request.urlopen(FRONTEND_URL, timeout=2)
            print("Frontend ready!")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("Frontend did not start")


def _calculate_audio_timeline(script_path: Path) -> list[dict]:
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)
    DURATIONS = {"opening": 8000, "round-title": 2500, "action": 4000, "voting": 8000}
    GAP = 500
    entries = []
    t = DURATIONS["opening"] + GAP
    for rd in script.get("rounds", []):
        rn = rd.get("round_number", 0)
        t += DURATIONS["round-title"] + GAP
        ei = 0
        for ev in rd.get("events", []):
            at = ev.get("action", {}).get("type", "")
            pay = ev.get("action", {}).get("payload", {})
            tip = ev.get("strategy_tip", "")
            tip_ms = int((len(tip) / TEXT_SPEED) * 1000) + 500 if tip else 0
            if at in ("speak", "last_words"):
                content = pay.get("content", "")
                entries.append({"file": f"{rn}_{ei}_{ev['player_id']}.mp3", "offset_ms": t + tip_ms})
                t += tip_ms + int((len(content) / TEXT_SPEED) * 1000) + 800 + GAP
            elif at == "vote":
                pass
            else:
                gesture = pay.get("gesture", "") or pay.get("content", "")
                if gesture:
                    t += tip_ms + int((len(gesture) / TEXT_SPEED) * 1000) + 800 + GAP
                else:
                    t += DURATIONS["action"] + GAP
            ei += 1
        if rd.get("vote_result"):
            t += DURATIONS["voting"] + GAP
    return entries


def _merge_audio(video_path: Path, script_path: Path, output_path: Path):
    audio_dir = Path("output/audio") / script_path.stem
    if not audio_dir.exists():
        print("No audio — silent video.")
        shutil.copy(video_path, output_path)
        return
    timeline = _calculate_audio_timeline(script_path)
    inputs = ["-i", str(video_path)]
    parts = []
    n = 0
    for e in timeline:
        mp3 = audio_dir / e["file"]
        if mp3.exists():
            inputs.extend(["-i", str(mp3)])
            n += 1
            d = e["offset_ms"]
            parts.append(f"[{n}:a]adelay={d}|{d}[a{n}]")
    if n == 0:
        print("No audio files — silent video.")
        shutil.copy(video_path, output_path)
        return
    mix = "".join(f"[a{i+1}]" for i in range(n))
    fc = ";".join(parts) + f";{mix}amix=inputs={n}:normalize=0[aout]"
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(output_path),
    ]
    print(f"Merging {n} audio files...")
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


async def record_game(script_filename: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    script_path = Path("output/scripts") / script_filename
    raw_video = OUTPUT_DIR / f"_raw_{script_filename.replace('.json', '.mp4')}"
    output_path = OUTPUT_DIR / script_filename.replace(".json", ".mp4")

    if FRAMES_DIR.exists():
        shutil.rmtree(FRAMES_DIR)
    FRAMES_DIR.mkdir(parents=True)

    print(f"\nRecording: {script_filename}")
    print(f"Output: {output_path}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()

        url = f"{FRONTEND_URL}?script={script_filename}&autoplay=true"
        print(f"Loading: {url}")
        await page.goto(url)
        await page.wait_for_selector("text=▶", timeout=30000)
        print("Theater loaded.")
        await asyncio.sleep(3)

        # Use CDP screencast — captures frames WITHOUT blocking the page
        cdp = await context.new_cdp_session(page)
        frame_num = 0

        async def on_frame(params):
            nonlocal frame_num
            # Save frame as PNG
            data = base64.b64decode(params["data"])
            frame_path = FRAMES_DIR / f"frame_{frame_num:06d}.png"
            frame_path.write_bytes(data)
            frame_num += 1
            # Acknowledge frame so Chrome sends the next one
            await cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

        cdp.on("Page.screencastFrame", on_frame)

        # Start screencast — non-blocking, Chrome sends frames as events
        await cdp.send("Page.startScreencast", {
            "format": "png",
            "quality": 100,
            "everyNthFrame": 1,
        })
        print("Screencast started (non-blocking). Waiting for playback...")

        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            if elapsed > MAX_WAIT_SECONDS:
                print(f"Max wait ({MAX_WAIT_SECONDS}s) reached.")
                break

            # Check for completion
            try:
                count = await page.locator("#playback-complete").count()
                if count > 0:
                    print(f"Playback complete! ({int(elapsed)}s, {frame_num} frames)")
                    await asyncio.sleep(10)  # Capture finale
                    break
            except Exception:
                pass  # Ignore, keep waiting

            if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                print(f"  [{int(elapsed)}s] {frame_num} frames captured")

            await asyncio.sleep(1)

        # Stop screencast
        await cdp.send("Page.stopScreencast")
        await asyncio.sleep(1)
        await browser.close()

    if frame_num == 0:
        print("Error: No frames captured.")
        return

    actual_fps = frame_num / max(time.time() - start_time, 1)
    print(f"Captured {frame_num} frames (~{actual_fps:.1f} fps)")

    # Stitch frames into video
    print("Encoding video...")
    pattern = str(FRAMES_DIR / "frame_%06d.png").replace("\\", "/")
    encode_fps = max(2, int(actual_fps))  # Use actual capture rate
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(encode_fps),
        "-i", pattern,
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(raw_video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"Encode error: {r.stderr[-300:]}")
        return

    if not raw_video.exists():
        print("Error: Encoding failed.")
        return

    print(f"Raw video: {raw_video} ({raw_video.stat().st_size / 1024 / 1024:.1f} MB)")

    # Merge audio
    _merge_audio(raw_video, script_path, output_path)

    # Cleanup
    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    if output_path.exists() and raw_video.exists():
        raw_video.unlink()

    if output_path.exists():
        print(f"\nDone! {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/record.py <script_json_filename>")
        scripts_dir = Path("output/scripts")
        if scripts_dir.exists():
            for s in sorted(scripts_dir.glob("game_*.json"))[-10:]:
                print(f"  {s.name}")
        sys.exit(1)
    sf = sys.argv[1]
    if not (Path("output/scripts") / sf).exists():
        print(f"Not found: output/scripts/{sf}")
        sys.exit(1)
    try:
        urllib.request.urlopen(FRONTEND_URL, timeout=2)
        print("Frontend already running.")
    except Exception:
        _start_frontend()
    try:
        asyncio.run(record_game(sf))
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
