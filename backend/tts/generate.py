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


def _extract_game_id(script_path: Path) -> str:
    """Derive game_id from script filename (e.g. game_spy_20260314_155258)."""
    return script_path.stem


def _collect_speech_events(script_data: dict) -> list[dict]:
    """Extract all speaking events from the script, preserving round and index info."""
    events = []
    for round_data in script_data.get("rounds", []):
        round_num = round_data["round_number"]
        event_index = 0
        for event in round_data.get("events", []):
            action = event.get("action", {})
            if action.get("type") == "speak":
                events.append({
                    "round": round_num,
                    "event_index": event_index,
                    "player_id": event["player_id"],
                    "content": action.get("payload", {}).get("content", ""),
                })
                event_index += 1
    return events


async def _generate_single(
    text: str,
    voice: str,
    output_path: Path,
) -> bool:
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


async def generate_audio(
    script_path: str,
    output_dir: str | None = None,
    voice_config: dict[str, str] | None = None,
) -> dict:
    """Generate TTS audio for all speech events in a GameScript JSON.

    Returns the manifest dict with file list and voice mapping.
    """
    script_file = Path(script_path).resolve()
    if not script_file.exists():
        raise FileNotFoundError(f"Script not found: {script_file}")

    script_data = json.loads(script_file.read_text(encoding="utf-8"))
    game_id = _extract_game_id(script_file)

    # Determine output directory
    if output_dir:
        audio_dir = Path(output_dir).resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        audio_dir = project_root / "output" / "audio" / game_id

    audio_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", audio_dir)

    # Collect speech events
    speech_events = _collect_speech_events(script_data)
    if not speech_events:
        logger.warning("No speech events found in script")
        return {"game_id": game_id, "voice_map": {}, "files": []}

    # Assign voices to players
    player_ids = [p["id"] for p in script_data.get("players", [])]
    voice_map = assign_voices(player_ids, voice_config=voice_config)

    # Generate MP3 for each speech event
    manifest_files = []
    success_count = 0
    fail_count = 0

    for event in speech_events:
        player_id = event["player_id"]
        voice = voice_map.get(player_id, "zh-CN-YunxiNeural")
        filename = f"{event['round']}_{event['event_index']}_{player_id}.mp3"
        output_path = audio_dir / filename

        content = event["content"]
        if not content.strip():
            logger.warning("Empty content for %s, skipping", filename)
            fail_count += 1
            continue

        ok = await _generate_single(content, voice, output_path)
        if ok:
            manifest_files.append({
                "file": filename,
                "round": event["round"],
                "event_index": event["event_index"],
                "player_id": player_id,
            })
            success_count += 1
        else:
            fail_count += 1

    # Write manifest
    manifest = {
        "game_id": game_id,
        "voice_map": voice_map,
        "files": manifest_files,
    }
    manifest_path = audio_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Manifest written: %s", manifest_path)
    logger.info("TTS generation complete: %d success, %d failed", success_count, fail_count)

    return manifest


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

    print(f"\nAudio directory: output/audio/{manifest['game_id']}/")
    print(f"Files generated: {len(manifest['files'])}")
    for f in manifest["files"]:
        print(f"  {f['file']}")


if __name__ == "__main__":
    main()
