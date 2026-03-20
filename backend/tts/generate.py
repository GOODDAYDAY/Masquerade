"""TTS audio generation — converts GameScript speech events to MP3 files.

Entry point: python -m backend.tts.generate <script_json_path>
Output: MP3 files + manifest.json in output/audio/<game_id>/
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from backend.tts.voices import assign_voices

logger = logging.getLogger("backend.tts.generate")


async def generate_audio(
    script_path: str,
    output_dir: str | None = None,
    voice_config: dict[str, str] | None = None,
) -> dict:
    """Generate TTS audio for all speech events in a GameScript JSON."""
    # 1. Load and parse the script JSON file
    script_file, script_data = _load_script(script_path)
    game_id = script_file.stem
    # 2. Determine and create output directory
    audio_dir = _resolve_audio_dir(output_dir, game_id)
    # 3. Extract all speech events from script
    speech_events = _collect_speech_events(script_data)
    if not speech_events:
        logger.warning("No speech events found in script")
        return {"game_id": game_id, "voice_map": {}, "files": []}
    # 4. Assign TTS voices to each player
    player_ids = [p["id"] for p in script_data.get("players", [])]
    voice_map = assign_voices(player_ids, voice_config=voice_config)
    # 5. Generate MP3 files for all speech events
    manifest_files = await _generate_all_audio(speech_events, voice_map, audio_dir)
    # 6. Write manifest.json and return
    manifest = _write_manifest(game_id, voice_map, manifest_files, audio_dir)
    return manifest


# ══════════════════════════════════════════════
#  Private step methods
# ══════════════════════════════════════════════

def _load_script(script_path: str) -> tuple[Path, dict]:
    """Load and parse the script JSON file."""
    script_file = Path(script_path).resolve()
    if not script_file.exists():
        raise FileNotFoundError("Script not found: %s" % script_file)
    script_data = json.loads(script_file.read_text(encoding="utf-8"))
    return script_file, script_data


def _resolve_audio_dir(output_dir: str | None, game_id: str) -> Path:
    """Determine and create the output audio directory."""
    if output_dir:
        audio_dir = Path(output_dir).resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        audio_dir = project_root / "output" / "audio" / game_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", audio_dir)
    return audio_dir


def _collect_speech_events(script_data: dict) -> list[dict]:
    """Extract all events with text content from the script for TTS generation."""
    events = []
    for round_data in script_data.get("rounds", []):
        round_num = round_data["round_number"]
        event_index = 0
        for event in round_data.get("events", []):
            action = event.get("action", {})
            content = _extract_speech_content(action)
            if content and content.strip():
                events.append({
                    "round": round_num,
                    "event_index": event_index,
                    "player_id": event["player_id"],
                    "content": content,
                })
            event_index += 1
    return events


def _extract_speech_content(action: dict) -> str:
    """Extract text content from an action based on its type."""
    action_type = action.get("type", "")
    payload = action.get("payload", {})
    if action_type in ("speak", "last_words"):
        return payload.get("content", "")
    if action_type == "wolf_discuss":
        return payload.get("gesture", "")
    return ""


async def _generate_all_audio(
    speech_events: list[dict],
    voice_map: dict[str, str],
    audio_dir: Path,
) -> list[dict]:
    """Generate MP3 for each speech event, return manifest file list."""
    manifest_files = []
    success_count = 0
    fail_count = 0

    for event in speech_events:
        ok, file_entry = await _generate_single_event(event, voice_map, audio_dir)
        if ok and file_entry:
            manifest_files.append(file_entry)
            success_count += 1
        else:
            fail_count += 1

    logger.info("TTS generation complete: %d success, %d failed", success_count, fail_count)
    return manifest_files


async def _generate_single_event(
    event: dict, voice_map: dict[str, str], audio_dir: Path,
) -> tuple[bool, dict | None]:
    """Generate one MP3 file for a speech event."""
    player_id = event["player_id"]
    content = event["content"]
    filename = "%d_%d_%s.mp3" % (event["round"], event["event_index"], player_id)

    if not content.strip():
        logger.warning("Empty content for %s, skipping", filename)
        return False, None

    voice = voice_map.get(player_id, "zh-CN-YunxiNeural")
    output_path = audio_dir / filename
    ok = await _tts_to_file(content, voice, output_path)

    if ok:
        return True, {
            "file": filename,
            "round": event["round"],
            "event_index": event["event_index"],
            "player_id": player_id,
        }
    return False, None


async def _tts_to_file(text: str, voice: str, output_path: Path) -> bool:
    """Generate a single MP3 file using edge-tts."""
    try:
        import edge_tts
    except ImportError:
        logger.error("edge-tts not installed. Run: pip install edge-tts")
        return False

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        logger.info("Generated: %s", output_path.name)
        return True
    except Exception:
        logger.exception("Failed to generate TTS for %s", output_path.name)
        return False


def _write_manifest(
    game_id: str, voice_map: dict, manifest_files: list[dict], audio_dir: Path,
) -> dict:
    """Write manifest.json and return the manifest dict."""
    manifest = {
        "game_id": game_id,
        "voice_map": voice_map,
        "files": manifest_files,
    }
    manifest_path = audio_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Manifest written: %s", manifest_path)
    return manifest


# ══════════════════════════════════════════════
#  CLI entry point
# ══════════════════════════════════════════════

def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m backend.tts.generate <script_json_path>")
        sys.exit(1)

    script_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    manifest = asyncio.run(generate_audio(script_path, output_dir))

    print("\nAudio directory: output/audio/%s/" % manifest["game_id"])
    print("Files generated: %d" % len(manifest["files"]))
    for f in manifest["files"]:
        print("  %s" % f["file"])


if __name__ == "__main__":
    main()
