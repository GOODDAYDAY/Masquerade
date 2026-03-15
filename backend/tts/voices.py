"""Voice assignment logic for TTS generation.

Provides all available Chinese neural voices (edge-tts) separated by gender,
and assigns them to players by round-robin within each gender pool.

edge-tts Chinese voices (14 total):
  Male   (6): YunxiNeural, YunjianNeural, YunyangNeural, YunxiaNeural, WanLungNeural(HK), YunJheNeural(TW)
  Female (8): XiaoxiaoNeural, XiaoyiNeural, XiaobeiNeural(东北), XiaoniNeural(陕西),
              HiuGaaiNeural(HK), HiuMaanNeural(HK), HsiaoChenNeural(TW), HsiaoYuNeural(TW)
"""

import logging

logger = logging.getLogger("backend.tts.voices")

MALE_VOICES = [
    "zh-CN-YunxiNeural",       # 温和青年
    "zh-CN-YunjianNeural",     # 沉稳成熟
    "zh-CN-YunyangNeural",     # 新闻播报
    "zh-CN-YunxiaNeural",      # 少年
    "zh-HK-WanLungNeural",     # 粤语男声
    "zh-TW-YunJheNeural",      # 台湾男声
]

FEMALE_VOICES = [
    "zh-CN-XiaoxiaoNeural",            # 活泼
    "zh-CN-XiaoyiNeural",              # 温柔
    "zh-CN-liaoning-XiaobeiNeural",    # 东北口音
    "zh-CN-shaanxi-XiaoniNeural",      # 陕西口音
    "zh-HK-HiuGaaiNeural",            # 粤语女声1
    "zh-HK-HiuMaanNeural",            # 粤语女声2
    "zh-TW-HsiaoChenNeural",          # 台湾女声1
    "zh-TW-HsiaoYuNeural",            # 台湾女声2
]

# Flat pool for fallback (alternating male/female)
VOICE_POOL = []
for i in range(max(len(MALE_VOICES), len(FEMALE_VOICES))):
    if i < len(MALE_VOICES):
        VOICE_POOL.append(MALE_VOICES[i])
    if i < len(FEMALE_VOICES):
        VOICE_POOL.append(FEMALE_VOICES[i])


def assign_voices(
    player_ids: list[str],
    voice_config: dict[str, str] | None = None,
    player_genders: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assign a TTS voice to each player.

    Priority:
    1. Explicit voice_config mapping (player_id -> voice name)
    2. Gender-aware rotation if player_genders provided (player_id -> "male"/"female")
    3. Fallback: rotate through VOICE_POOL
    """
    voice_map: dict[str, str] = {}
    male_idx = 0
    female_idx = 0
    pool_idx = 0

    for player_id in player_ids:
        if voice_config and player_id in voice_config:
            voice_map[player_id] = voice_config[player_id]
            logger.info("Player %s: configured voice %s", player_id, voice_config[player_id])
            continue

        if player_genders and player_id in player_genders:
            gender = player_genders[player_id].lower()
            if gender == "male":
                voice = MALE_VOICES[male_idx % len(MALE_VOICES)]
                male_idx += 1
            else:
                voice = FEMALE_VOICES[female_idx % len(FEMALE_VOICES)]
                female_idx += 1
            voice_map[player_id] = voice
            logger.info("Player %s: %s voice %s", player_id, gender, voice)
            continue

        voice = VOICE_POOL[pool_idx % len(VOICE_POOL)]
        pool_idx += 1
        voice_map[player_id] = voice
        logger.info("Player %s: pool voice %s", player_id, voice)

    return voice_map
