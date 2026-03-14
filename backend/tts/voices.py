"""Voice assignment logic for TTS generation.

Provides a pool of Chinese neural voices and assigns them to players
either from explicit configuration or by round-robin rotation.
"""

import logging

logger = logging.getLogger("backend.tts.voices")

# 6 Chinese neural voices: 3 male, 3 female
VOICE_POOL = [
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-YunjianNeural",
    "zh-CN-XiaoyiNeural",
    "zh-CN-YunxiaNeural",
    "zh-CN-XiaohanNeural",
]


def assign_voices(
    player_ids: list[str],
    voice_config: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assign a TTS voice to each player.

    Uses explicit config if provided, otherwise rotates through VOICE_POOL.
    """
    voice_map: dict[str, str] = {}

    for i, player_id in enumerate(player_ids):
        if voice_config and player_id in voice_config:
            voice_map[player_id] = voice_config[player_id]
            logger.info("Player %s assigned configured voice: %s", player_id, voice_config[player_id])
        else:
            voice = VOICE_POOL[i % len(VOICE_POOL)]
            voice_map[player_id] = voice
            logger.info("Player %s assigned voice from pool: %s", player_id, voice)

    return voice_map
