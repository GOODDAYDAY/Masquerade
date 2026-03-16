"""Werewolf game engine — state machine implementation.

Phases cycle: Night (guard → wolf discuss → wolf kill → witch → seer → resolve)
              → Day (announce → last words → hunter → discussion → voting → resolve)
              → Night ...
"""

import random
from enum import Enum

from backend.agent.strategy import AgentStrategy
from backend.core.exceptions import IllegalActionError
from backend.core.logging import get_logger
from backend.engine.base import GameEngine
from backend.engine.models import Action, ActionResult, GameResult, PlayerState
from backend.engine.registry import register_game
from backend.engine.werewolf.prompts import get_rules_prompt
from backend.engine.werewolf.strategy import (
    get_guard_day_strategy,
    get_guard_night_strategy,
    get_hunter_day_strategy,
    get_seer_day_strategy,
    get_seer_night_strategy,
    get_villager_day_strategy,
    get_werewolf_day_strategy,
    get_werewolf_night_strategy,
    get_witch_day_strategy,
    get_witch_night_strategy,
)

logger = get_logger("engine.werewolf")

_MIN_PLAYERS = 6
_WOLF_DISCUSS_ROUNDS = 2

# Faction constants
FACTION_WOLF = "wolf"
FACTION_VILLAGE = "village"

# Role to faction mapping
_ROLE_FACTION = {
    "werewolf": FACTION_WOLF,
    "villager": FACTION_VILLAGE,
    "seer": FACTION_VILLAGE,
    "witch": FACTION_VILLAGE,
    "hunter": FACTION_VILLAGE,
    "guard": FACTION_VILLAGE,
}


class WerewolfPhase(str, Enum):
    WAITING = "waiting"
    NIGHT_GUARD = "night_guard"
    NIGHT_WOLF_DISCUSS = "night_wolf_discuss"
    NIGHT_WOLF_KILL = "night_wolf_kill"
    NIGHT_WITCH = "night_witch"
    NIGHT_SEER = "night_seer"
    DAY_ANNOUNCE = "day_announce"
    DAY_LAST_WORDS = "day_last_words"
    DAY_HUNTER = "day_hunter"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTING = "day_voting"
    ENDED = "ended"


@register_game("werewolf")
class WerewolfGame(GameEngine):
    """State machine implementation of the Werewolf (狼人杀) game."""

    def __init__(self) -> None:
        self.phase: WerewolfPhase = WerewolfPhase.WAITING
        self.players: dict[str, PlayerState] = {}
        self.player_order: list[str] = []
        self.round_number: int = 0

        # Role quick-access indices
        self.wolf_ids: list[str] = []
        self.seer_id: str | None = None
        self.witch_id: str | None = None
        self.hunter_id: str | None = None
        self.guard_id: str | None = None

        # Witch resources (persist across rounds)
        self.witch_antidote_used: bool = False
        self.witch_poison_used: bool = False

        # Guard state
        self.guard_last_protected: str | None = None

        # Seer accumulated knowledge
        self.seer_results: dict[str, str] = {}  # player_id -> faction

        # Night state (reset each night)
        self.night_guard_target: str | None = None
        self.night_wolf_target: str | None = None
        self.night_witch_save: bool = False
        self.night_witch_poison_target: str | None = None

        # Wolf discussion tracking
        self.wolf_discuss_round: int = 0
        self.wolf_discuss_idx: int = 0
        self.wolf_discussions: list[dict] = []  # [{player_id, gesture}]

        # Day state
        self.current_player_idx: int = 0
        self.votes: dict[str, str] = {}
        self.vote_history: dict[int, dict[str, str]] = {}
        self.speeches: dict[int, list[dict]] = {}

        # Death tracking
        self.eliminated_order: list[str] = []
        self.night_deaths: list[str] = []
        self.pending_last_words: list[str] = []
        self.pending_hunter_shot: bool = False

    # =========================================================================
    # Setup
    # =========================================================================

    def setup(self, players: list[str], config: dict) -> None:
        if len(players) < _MIN_PLAYERS:
            raise IllegalActionError(
                "Werewolf requires at least %d players, got %d" % (_MIN_PLAYERS, len(players))
            )

        self.player_order = list(players)
        random.shuffle(self.player_order)

        # Parse role counts from config
        werewolf_count = config.get("werewolf_count", 2)
        villager_count = config.get("villager_count", 2)
        has_seer = config.get("seer", True)
        has_witch = config.get("witch", True)
        has_hunter = config.get("hunter", True)
        has_guard = config.get("guard", True)

        special_count = sum([has_seer, has_witch, has_hunter, has_guard])
        total_village = villager_count + special_count
        total_roles = werewolf_count + total_village

        if total_roles != len(players):
            raise IllegalActionError(
                "Total roles (%d) != total players (%d)" % (total_roles, len(players))
            )
        if werewolf_count >= total_village:
            raise IllegalActionError(
                "Werewolf count (%d) must be less than village count (%d)"
                % (werewolf_count, total_village)
            )

        # Build role pool and shuffle
        roles: list[str] = []
        roles.extend(["werewolf"] * werewolf_count)
        roles.extend(["villager"] * villager_count)
        if has_seer:
            roles.append("seer")
        if has_witch:
            roles.append("witch")
        if has_hunter:
            roles.append("hunter")
        if has_guard:
            roles.append("guard")

        random.shuffle(roles)

        # Assign roles
        for i, pid in enumerate(players):
            role = roles[i]
            self.players[pid] = PlayerState(player_id=pid, alive=True, role=role, word="")

            if role == "werewolf":
                self.wolf_ids.append(pid)
            elif role == "seer":
                self.seer_id = pid
            elif role == "witch":
                self.witch_id = pid
            elif role == "hunter":
                self.hunter_id = pid
            elif role == "guard":
                self.guard_id = pid

        logger.info(
            "Game setup: %d players, %d wolves, seer=%s, witch=%s, hunter=%s, guard=%s",
            len(players), werewolf_count,
            self.seer_id or "none", self.witch_id or "none",
            self.hunter_id or "none", self.guard_id or "none",
        )

        # Start first night
        self.round_number = 1
        self._start_night()

    # =========================================================================
    # GameEngine interface — state queries
    # =========================================================================

    def get_player_ids(self) -> list[str]:
        return list(self.player_order)

    def get_public_state(self) -> dict:
        alive = [pid for pid in self.player_order if self.players[pid].alive]
        return {
            "phase": self.phase.value,
            "round_number": self.round_number,
            "alive_players": alive,
            "eliminated_players": self.eliminated_order,
            "speeches": self.speeches,
            "vote_history": self.vote_history,
            "current_player": self.get_current_player(),
            "night_deaths": self.night_deaths if self.phase.value.startswith("day") else [],
        }

    def get_private_info(self, player_id: str) -> dict:
        ps = self.players.get(player_id)
        if not ps:
            return {}

        info: dict = {"role": ps.role, "faction": _ROLE_FACTION.get(ps.role, "")}

        if ps.role == "werewolf":
            # Wolves know each other
            info["wolf_teammates"] = [
                wid for wid in self.wolf_ids if wid != player_id
            ]
            info["wolf_discussions"] = self.wolf_discussions
        elif ps.role == "seer":
            info["check_results"] = dict(self.seer_results)
        elif ps.role == "witch":
            info["antidote_available"] = not self.witch_antidote_used
            info["poison_available"] = not self.witch_poison_used
            # During witch's turn, reveal who was killed tonight
            if self.phase == WerewolfPhase.NIGHT_WITCH:
                info["tonight_killed"] = self.night_wolf_target
        elif ps.role == "guard":
            info["last_protected"] = self.guard_last_protected

        return info

    def get_role_info(self, player_id: str) -> dict:
        ps = self.players.get(player_id)
        if not ps:
            return {}
        return {"role": ps.role, "word": "", "faction": _ROLE_FACTION.get(ps.role, "")}

    def get_available_actions(self, player_id: str) -> list[str]:
        ps = self.players.get(player_id)
        if not ps or not ps.alive:
            # Dead players can only speak last words or shoot
            if player_id in self.pending_last_words:
                return ["last_words"]
            if self.pending_hunter_shot and player_id == self.hunter_id:
                return ["hunter_shoot"]
            return []

        if self.phase == WerewolfPhase.NIGHT_GUARD and player_id == self.guard_id:
            return ["protect"]
        if self.phase == WerewolfPhase.NIGHT_WOLF_DISCUSS and player_id in self.wolf_ids:
            alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
            if self.wolf_discuss_idx < len(alive_wolves) and alive_wolves[self.wolf_discuss_idx] == player_id:
                return ["wolf_discuss"]
        if self.phase == WerewolfPhase.NIGHT_WOLF_KILL:
            alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
            if alive_wolves and alive_wolves[-1] == player_id:
                return ["wolf_kill"]
        if self.phase == WerewolfPhase.NIGHT_WITCH and player_id == self.witch_id:
            return ["witch_action"]
        if self.phase == WerewolfPhase.NIGHT_SEER and player_id == self.seer_id:
            return ["seer_check"]
        if self.phase == WerewolfPhase.DAY_DISCUSSION:
            alive_order = [p for p in self.player_order if self.players[p].alive]
            if self.current_player_idx < len(alive_order) and alive_order[self.current_player_idx] == player_id:
                return ["speak"]
        if self.phase == WerewolfPhase.DAY_VOTING and player_id not in self.votes:
            if self.players[player_id].alive:
                return ["vote"]

        return []

    def get_current_player(self) -> str | None:
        if self.phase == WerewolfPhase.NIGHT_GUARD:
            if self.guard_id and self.players[self.guard_id].alive:
                return self.guard_id
            return None

        if self.phase == WerewolfPhase.NIGHT_WOLF_DISCUSS:
            alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
            if self.wolf_discuss_idx < len(alive_wolves):
                return alive_wolves[self.wolf_discuss_idx]
            return None

        if self.phase == WerewolfPhase.NIGHT_WOLF_KILL:
            alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
            return alive_wolves[-1] if alive_wolves else None

        if self.phase == WerewolfPhase.NIGHT_WITCH:
            if self.witch_id and self.players[self.witch_id].alive:
                return self.witch_id
            return None

        if self.phase == WerewolfPhase.NIGHT_SEER:
            if self.seer_id and self.players[self.seer_id].alive:
                return self.seer_id
            return None

        if self.phase == WerewolfPhase.DAY_LAST_WORDS:
            if self.pending_last_words:
                return self.pending_last_words[0]
            return None

        if self.phase == WerewolfPhase.DAY_HUNTER:
            if self.pending_hunter_shot and self.hunter_id:
                return self.hunter_id
            return None

        if self.phase == WerewolfPhase.DAY_DISCUSSION:
            alive_order = [p for p in self.player_order if self.players[p].alive]
            if self.current_player_idx < len(alive_order):
                return alive_order[self.current_player_idx]
            return None

        if self.phase == WerewolfPhase.DAY_VOTING:
            alive_order = [p for p in self.player_order if self.players[p].alive]
            for pid in alive_order:
                if pid not in self.votes:
                    return pid
            return None

        return None

    def is_ended(self) -> bool:
        return self.phase == WerewolfPhase.ENDED

    def get_result(self) -> GameResult | None:
        if not self.is_ended():
            return None

        winner = self._check_win_condition() or "unknown"
        return GameResult(
            winner=winner,
            eliminated_order=self.eliminated_order,
            total_rounds=self.round_number,
        )

    # =========================================================================
    # GameEngine interface — LLM integration
    # =========================================================================

    def get_game_rules_prompt(self) -> str:
        return get_rules_prompt()

    def get_tools_schema(self) -> list[dict]:
        """Return tool definitions matching the current phase."""
        if self.phase == WerewolfPhase.NIGHT_GUARD:
            return [self._tool("protect", "选择保护一名玩家（动作描述）", {
                "target": {"type": "string", "description": "要保护的玩家ID"},
            })]
        if self.phase == WerewolfPhase.NIGHT_WOLF_DISCUSS:
            return [self._tool("wolf_discuss", "用手势/动作与狼队友交流（不能说话）", {
                "gesture": {"type": "string", "description": "你的动作描述"},
            })]
        if self.phase == WerewolfPhase.NIGHT_WOLF_KILL:
            return [self._tool("wolf_kill", "选择今晚击杀的目标", {
                "target": {"type": "string", "description": "要击杀的玩家ID"},
            })]
        if self.phase == WerewolfPhase.NIGHT_WITCH:
            return [self._tool("witch_action", "决定是否使用药物", {
                "use": {"type": "string", "description": "antidote（解药）/ poison（毒药）/ skip（不用药）"},
                "target": {"type": "string", "description": "毒药目标玩家ID（仅use=poison时需要）"},
            }, required=["use"])]  # target is optional (only needed for poison)
        if self.phase == WerewolfPhase.NIGHT_SEER:
            return [self._tool("seer_check", "选择查验一名玩家的阵营", {
                "target": {"type": "string", "description": "要查验的玩家ID"},
            })]
        if self.phase in (WerewolfPhase.DAY_DISCUSSION,):
            return [self._tool("speak", "发表你的看法和推理", {
                "content": {"type": "string", "description": "你的发言内容"},
            })]
        if self.phase == WerewolfPhase.DAY_VOTING:
            return [self._tool("vote", "投票放逐你认为是狼人的玩家", {
                "target_player_id": {"type": "string", "description": "你要投票的玩家ID"},
            })]
        if self.phase == WerewolfPhase.DAY_LAST_WORDS:
            return [self._tool("last_words", "发表遗言", {
                "content": {"type": "string", "description": "你的遗言内容"},
            })]
        if self.phase == WerewolfPhase.DAY_HUNTER:
            return [self._tool("hunter_shoot", "选择是否开枪带走一名玩家", {
                "target": {"type": "string", "description": "目标玩家ID，或 'skip' 不开枪"},
            })]
        return []

    def get_agent_strategy(self, player_id: str) -> AgentStrategy:
        ps = self.players.get(player_id)
        if not ps:
            return get_villager_day_strategy()

        is_night = self.phase.value.startswith("night")

        if ps.role == "werewolf":
            return get_werewolf_night_strategy() if is_night else get_werewolf_day_strategy()
        if ps.role == "seer":
            return get_seer_night_strategy() if is_night else get_seer_day_strategy()
        if ps.role == "witch":
            return get_witch_night_strategy() if is_night else get_witch_day_strategy()
        if ps.role == "guard":
            return get_guard_night_strategy() if is_night else get_guard_day_strategy()
        if ps.role == "hunter":
            is_shooting = self.phase == WerewolfPhase.DAY_HUNTER
            return get_hunter_day_strategy(is_shooting=is_shooting)
        # villager or unknown
        return get_villager_day_strategy()

    # =========================================================================
    # GameEngine interface — Runner integration methods
    # =========================================================================

    def get_actionable_players(self) -> list[str]:
        if self.phase == WerewolfPhase.DAY_VOTING:
            # All unvoted alive players can think in parallel
            return [pid for pid in self.player_order
                    if self.players[pid].alive and pid not in self.votes]
        current = self.get_current_player()
        return [current] if current else []

    def format_action_log(self, player_id: str, action: Action) -> str:
        phase = self.phase.value
        if action.type == "speak":
            return "[%s] %s says: %s" % (phase, player_id, action.payload.get("content", ""))
        if action.type == "vote":
            return "[%s] %s votes for: %s" % (phase, player_id, action.payload.get("target_player_id", ""))
        if action.type == "wolf_discuss":
            return "[%s] %s gesture: %s" % (phase, player_id, action.payload.get("gesture", ""))
        if action.type == "wolf_kill":
            return "[%s] wolves kill: %s" % (phase, action.payload.get("target", ""))
        if action.type == "protect":
            return "[%s] guard protects: %s" % (phase, action.payload.get("target", ""))
        if action.type == "seer_check":
            return "[%s] seer checks: %s" % (phase, action.payload.get("target", ""))
        if action.type == "witch_action":
            return "[%s] witch: %s" % (phase, action.payload.get("use", "skip"))
        if action.type == "hunter_shoot":
            return "[%s] hunter shoots: %s" % (phase, action.payload.get("target", "skip"))
        if action.type == "last_words":
            return "[%s] %s last words: %s" % (phase, player_id, action.payload.get("content", ""))
        return "[%s] %s: %s" % (phase, player_id, action.type)

    def get_broadcast_targets(self, player_id: str, action: Action) -> list[str] | None:
        # Wolf discussion — only wolves see it
        if action.type in ("wolf_discuss", "wolf_kill"):
            return [w for w in self.wolf_ids if self.players[w].alive]
        # Night actions — nobody else sees
        if action.type in ("protect", "seer_check", "witch_action"):
            return []
        # Day voting — secret ballot
        if action.type == "vote":
            return []
        # Day speech, last words, hunter shoot — everyone sees
        return None

    def format_public_summary(self, player_id: str, action: Action) -> str:
        if action.type == "speak":
            return "%s 说: %s" % (player_id, action.payload.get("content", ""))
        if action.type == "last_words":
            return "%s 的遗言: %s" % (player_id, action.payload.get("content", ""))
        if action.type == "wolf_discuss":
            return "%s 做了一个手势: %s" % (player_id, action.payload.get("gesture", ""))
        if action.type == "hunter_shoot":
            target = action.payload.get("target", "skip")
            if target and target != "skip":
                return "猎人 %s 开枪带走了 %s" % (player_id, target)
            return "猎人 %s 选择不开枪" % player_id
        return "%s 执行了 %s" % (player_id, action.type)

    def get_round_end_summary(self, round_number: int) -> str | None:
        parts = []

        # Night death announcements
        if self.night_deaths:
            dead_names = ", ".join(self.night_deaths)
            parts.append("昨晚死亡: %s" % dead_names)
        elif self.phase.value.startswith("day") or self.phase == WerewolfPhase.ENDED:
            # Only announce "peaceful night" after night has resolved
            if round_number == self.round_number:
                parts.append("昨晚是平安夜，无人死亡")

        # Vote results
        votes = self.vote_history.get(round_number, {})
        if votes:
            vote_lines = ["%s \u2192 %s" % (v, t) for v, t in votes.items()]
            eliminated = self._get_round_vote_eliminated(round_number)
            if eliminated:
                parts.append("投票详情: %s\n结果: %s 被放逐" % (", ".join(vote_lines), eliminated))
            else:
                parts.append("投票详情: %s\n结果: 平票，无人放逐" % ", ".join(vote_lines))

        return "\n".join(parts) if parts else None

    def get_vote_result(self, round_number: int) -> dict | None:
        votes = self.vote_history.get(round_number, {})
        if not votes:
            return None
        eliminated = self._get_round_vote_eliminated(round_number)
        return {"votes": votes, "eliminated": eliminated}

    # =========================================================================
    # Action handling
    # =========================================================================

    def apply_action(self, player_id: str, action: Action) -> ActionResult:
        handlers = {
            "protect": self._handle_protect,
            "wolf_discuss": self._handle_wolf_discuss,
            "wolf_kill": self._handle_wolf_kill,
            "witch_action": self._handle_witch_action,
            "seer_check": self._handle_seer_check,
            "speak": self._handle_speak,
            "vote": self._handle_vote,
            "last_words": self._handle_last_words,
            "hunter_shoot": self._handle_hunter_shoot,
        }

        handler = handlers.get(action.type)
        if not handler:
            raise IllegalActionError("Unknown action type: %s" % action.type)

        return handler(player_id, action)

    def _handle_protect(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.NIGHT_GUARD:
            raise IllegalActionError("Not in guard phase")
        if player_id != self.guard_id:
            raise IllegalActionError("Only guard can protect")

        target = action.payload.get("target", "")
        if target not in self.players or not self.players[target].alive:
            raise IllegalActionError("Invalid protect target: %s" % target)
        if target == self.guard_last_protected:
            raise IllegalActionError("Cannot protect same player two nights in a row")

        self.night_guard_target = target
        self.guard_last_protected = target
        logger.info("Round %d: guard protects %s", self.round_number, target)

        self._advance_to_next_phase()
        return ActionResult(success=True, message="Protection set")

    def _handle_wolf_discuss(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.NIGHT_WOLF_DISCUSS:
            raise IllegalActionError("Not in wolf discussion phase")

        gesture = action.payload.get("gesture", "")
        if not gesture:
            raise IllegalActionError("Gesture description cannot be empty")

        self.wolf_discussions.append({"player_id": player_id, "gesture": gesture})
        logger.info("Round %d: %s gestures: %s", self.round_number, player_id, gesture)

        # Advance wolf discussion index
        alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
        self.wolf_discuss_idx += 1

        # Check if current discussion round is complete
        if self.wolf_discuss_idx >= len(alive_wolves):
            self.wolf_discuss_round += 1
            self.wolf_discuss_idx = 0

            # All discussion rounds done → move to kill phase
            if self.wolf_discuss_round >= _WOLF_DISCUSS_ROUNDS:
                self.phase = WerewolfPhase.NIGHT_WOLF_KILL
                logger.info("Round %d: wolf discussion complete, entering kill phase", self.round_number)

        return ActionResult(success=True, message="Gesture recorded")

    def _handle_wolf_kill(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.NIGHT_WOLF_KILL:
            raise IllegalActionError("Not in wolf kill phase")

        target = action.payload.get("target", "")
        if target not in self.players or not self.players[target].alive:
            raise IllegalActionError("Invalid kill target: %s" % target)
        if target in self.wolf_ids:
            raise IllegalActionError("Wolves cannot kill their own teammates")

        self.night_wolf_target = target
        logger.info("Round %d: wolves choose to kill %s", self.round_number, target)

        self._advance_to_next_phase()
        return ActionResult(success=True, message="Kill target set")

    def _handle_witch_action(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.NIGHT_WITCH:
            raise IllegalActionError("Not in witch phase")
        if player_id != self.witch_id:
            raise IllegalActionError("Only witch can use potions")

        use = action.payload.get("use", "skip")

        if use == "antidote":
            if self.witch_antidote_used:
                raise IllegalActionError("Antidote already used")
            if not self.night_wolf_target:
                raise IllegalActionError("No one to save tonight")
            self.night_witch_save = True
            self.witch_antidote_used = True
            logger.info("Round %d: witch uses antidote to save %s", self.round_number, self.night_wolf_target)
        elif use == "poison":
            if self.witch_poison_used:
                raise IllegalActionError("Poison already used")
            target = action.payload.get("target", "")
            if not target or target not in self.players or not self.players[target].alive:
                raise IllegalActionError("Invalid poison target: %s" % target)
            self.night_witch_poison_target = target
            self.witch_poison_used = True
            logger.info("Round %d: witch uses poison on %s", self.round_number, target)
        elif use == "skip":
            logger.info("Round %d: witch skips", self.round_number)
        else:
            raise IllegalActionError("Unknown witch action: %s" % use)

        self._advance_to_next_phase()
        return ActionResult(success=True, message="Witch action recorded")

    def _handle_seer_check(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.NIGHT_SEER:
            raise IllegalActionError("Not in seer phase")
        if player_id != self.seer_id:
            raise IllegalActionError("Only seer can check")

        target = action.payload.get("target", "")
        if target not in self.players or not self.players[target].alive:
            raise IllegalActionError("Invalid check target: %s" % target)
        if target == player_id:
            raise IllegalActionError("Cannot check yourself")

        faction = _ROLE_FACTION.get(self.players[target].role, FACTION_VILLAGE)
        self.seer_results[target] = faction
        logger.info("Round %d: seer checks %s -> %s", self.round_number, target, faction)

        # Resolve night after seer (last night action)
        self._resolve_night()

        return ActionResult(
            success=True,
            message="Check result: %s is %s" % (target, faction),
            public_info={"target": target, "faction": faction},
        )

    def _handle_speak(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.DAY_DISCUSSION:
            raise IllegalActionError("Not in discussion phase")

        content = action.payload.get("content", "")
        if not content:
            raise IllegalActionError("Speech content cannot be empty")

        if self.round_number not in self.speeches:
            self.speeches[self.round_number] = []
        self.speeches[self.round_number].append({"player_id": player_id, "content": content})

        alive_order = [p for p in self.player_order if self.players[p].alive]
        self.current_player_idx += 1

        # All players have spoken → move to voting
        if self.current_player_idx >= len(alive_order):
            self.phase = WerewolfPhase.DAY_VOTING
            self.votes = {}
            logger.info("Round %d: discussion complete, entering voting", self.round_number)

        return ActionResult(
            success=True,
            message="Speech recorded",
            public_info={"player_id": player_id, "content": content},
        )

    def _handle_vote(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != WerewolfPhase.DAY_VOTING:
            raise IllegalActionError("Not in voting phase")
        if player_id in self.votes:
            raise IllegalActionError("Player %s has already voted" % player_id)

        target = action.payload.get("target_player_id", "")
        if target not in self.players or not self.players[target].alive:
            raise IllegalActionError("Invalid vote target: %s" % target)
        if target == player_id:
            raise IllegalActionError("Cannot vote for yourself")

        self.votes[player_id] = target
        logger.info("Round %d: %s votes for %s", self.round_number, player_id, target)

        # Check if all alive players have voted
        alive = [p for p in self.player_order if self.players[p].alive]
        if len(self.votes) >= len(alive):
            return self._resolve_votes()

        return ActionResult(success=True, message="Vote recorded")

    def _handle_last_words(self, player_id: str, action: Action) -> ActionResult:
        if player_id not in self.pending_last_words:
            raise IllegalActionError("%s has no pending last words" % player_id)

        content = action.payload.get("content", "")
        self.pending_last_words.remove(player_id)
        logger.info("Round %d: %s's last words: %s", self.round_number, player_id, content)

        # Check if hunter should shoot
        if not self.pending_last_words:
            if self.pending_hunter_shot:
                self.phase = WerewolfPhase.DAY_HUNTER
            else:
                self._after_deaths_resolved()

        return ActionResult(
            success=True,
            message="Last words recorded",
            public_info={"player_id": player_id, "content": content},
        )

    def _handle_hunter_shoot(self, player_id: str, action: Action) -> ActionResult:
        if not self.pending_hunter_shot or player_id != self.hunter_id:
            raise IllegalActionError("No pending hunter shot or wrong player")

        target = action.payload.get("target", "skip")
        self.pending_hunter_shot = False

        if target and target != "skip":
            if target not in self.players or not self.players[target].alive:
                raise IllegalActionError("Invalid shoot target: %s" % target)

            self.players[target].alive = False
            self.eliminated_order.append(target)
            logger.info("Round %d: hunter %s shoots %s", self.round_number, player_id, target)

            # Check win after hunter shot
            winner = self._check_win_condition()
            if winner:
                self.phase = WerewolfPhase.ENDED
                logger.info("Game ended after hunter shot")
                return ActionResult(success=True, message="Hunter shot %s, game ended" % target)
        else:
            logger.info("Round %d: hunter %s chooses not to shoot", self.round_number, player_id)

        self._after_deaths_resolved()
        return ActionResult(success=True, message="Hunter action resolved")

    # =========================================================================
    # Phase transitions
    # =========================================================================

    def _start_night(self) -> None:
        """Reset night state and enter the first available night phase."""
        self.night_guard_target = None
        self.night_wolf_target = None
        self.night_witch_save = False
        self.night_witch_poison_target = None
        self.wolf_discuss_round = 0
        self.wolf_discuss_idx = 0
        self.wolf_discussions = []
        self.night_deaths = []

        # Find first available night phase
        if self.guard_id and self.players[self.guard_id].alive:
            self.phase = WerewolfPhase.NIGHT_GUARD
        else:
            self.phase = WerewolfPhase.NIGHT_WOLF_DISCUSS

        # Skip wolf discuss if only one wolf alive
        alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
        if len(alive_wolves) <= 1 and self.phase == WerewolfPhase.NIGHT_WOLF_DISCUSS:
            self.phase = WerewolfPhase.NIGHT_WOLF_KILL

        logger.info("Round %d: night begins at phase %s", self.round_number, self.phase.value)

    def _advance_to_next_phase(self) -> None:
        """Move to the next phase, skipping phases where the role is dead."""
        phase_order = [
            WerewolfPhase.NIGHT_GUARD,
            WerewolfPhase.NIGHT_WOLF_DISCUSS,
            WerewolfPhase.NIGHT_WOLF_KILL,
            WerewolfPhase.NIGHT_WITCH,
            WerewolfPhase.NIGHT_SEER,
        ]

        current_idx = phase_order.index(self.phase) if self.phase in phase_order else -1
        if current_idx < 0:
            return

        for next_phase in phase_order[current_idx + 1:]:
            if self._is_phase_available(next_phase):
                self.phase = next_phase

                # If entering wolf discuss with only 1 wolf, skip to kill
                if next_phase == WerewolfPhase.NIGHT_WOLF_DISCUSS:
                    alive_wolves = [w for w in self.wolf_ids if self.players[w].alive]
                    if len(alive_wolves) <= 1:
                        self.phase = WerewolfPhase.NIGHT_WOLF_KILL

                logger.info("Round %d: advancing to %s", self.round_number, self.phase.value)
                return

        # All night phases done — resolve night (seer was last, handled in seer_check)
        # This path is reached if seer is dead
        self._resolve_night()

    def _is_phase_available(self, phase: WerewolfPhase) -> bool:
        """Check if a night phase can execute (role is alive and has actions)."""
        if phase == WerewolfPhase.NIGHT_GUARD:
            return bool(self.guard_id and self.players[self.guard_id].alive)
        if phase in (WerewolfPhase.NIGHT_WOLF_DISCUSS, WerewolfPhase.NIGHT_WOLF_KILL):
            return any(self.players[w].alive for w in self.wolf_ids)
        if phase == WerewolfPhase.NIGHT_WITCH:
            if not self.witch_id or not self.players[self.witch_id].alive:
                return False
            # Skip if no potions left and no one to save
            can_save = not self.witch_antidote_used and self.night_wolf_target
            can_poison = not self.witch_poison_used
            return can_save or can_poison
        if phase == WerewolfPhase.NIGHT_SEER:
            return bool(self.seer_id and self.players[self.seer_id].alive)
        return True

    def _resolve_night(self) -> None:
        """Calculate night deaths and transition to day phase."""
        deaths: list[str] = []

        # Wolf kill resolution
        if self.night_wolf_target:
            target = self.night_wolf_target
            guarded = (target == self.night_guard_target)
            saved = self.night_witch_save

            if guarded and saved:
                # Double protection = death (per requirement: no stacking)
                deaths.append(target)
                logger.info("Round %d: %s dies (guard + antidote don't stack)", self.round_number, target)
            elif guarded:
                logger.info("Round %d: %s saved by guard", self.round_number, target)
            elif saved:
                logger.info("Round %d: %s saved by witch antidote", self.round_number, target)
            else:
                deaths.append(target)
                logger.info("Round %d: %s killed by wolves", self.round_number, target)

        # Witch poison
        if self.night_witch_poison_target:
            poison_target = self.night_witch_poison_target
            if poison_target not in deaths:
                deaths.append(poison_target)
                logger.info("Round %d: %s killed by witch poison", self.round_number, poison_target)

        # Apply deaths
        for pid in deaths:
            if self.players[pid].alive:
                self.players[pid].alive = False
                self.eliminated_order.append(pid)

        self.night_deaths = deaths

        # Check win condition
        winner = self._check_win_condition()
        if winner:
            self.phase = WerewolfPhase.ENDED
            logger.info("Game ended after night %d: %s wins", self.round_number, winner)
            return

        # Transition to day
        self._start_day()

    def _start_day(self) -> None:
        """Begin day phase — handle death announcements and pending actions."""
        if self.night_deaths:
            # Set up last words for dead players
            self.pending_last_words = list(self.night_deaths)
            # Check if hunter died
            if self.hunter_id in self.night_deaths:
                self.pending_hunter_shot = True
            self.phase = WerewolfPhase.DAY_LAST_WORDS
            logger.info("Round %d: day begins, deaths: %s", self.round_number, ", ".join(self.night_deaths))
        else:
            # Peaceful night — go straight to discussion
            self.phase = WerewolfPhase.DAY_DISCUSSION
            self.current_player_idx = 0
            self.speeches[self.round_number] = []
            logger.info("Round %d: peaceful night, entering discussion", self.round_number)

    def _after_deaths_resolved(self) -> None:
        """Called after last words and hunter shots are resolved."""
        # Check win again (hunter may have changed the balance)
        winner = self._check_win_condition()
        if winner:
            self.phase = WerewolfPhase.ENDED
            logger.info("Game ended after death resolution")
            return

        # Enter discussion
        self.phase = WerewolfPhase.DAY_DISCUSSION
        self.current_player_idx = 0
        self.speeches[self.round_number] = []

    def _resolve_votes(self) -> ActionResult:
        """Count votes and resolve day elimination."""
        self.vote_history[self.round_number] = dict(self.votes)

        vote_counts: dict[str, int] = {}
        for target in self.votes.values():
            vote_counts[target] = vote_counts.get(target, 0) + 1

        max_votes = max(vote_counts.values())
        top_voted = [pid for pid, count in vote_counts.items() if count == max_votes]

        if len(top_voted) == 1:
            eliminated = top_voted[0]
            self.players[eliminated].alive = False
            self.eliminated_order.append(eliminated)
            logger.info("Round %d: %s exiled with %d votes", self.round_number, eliminated, max_votes)

            # Hunter dies from exile — can shoot
            if eliminated == self.hunter_id:
                self.pending_hunter_shot = True
                self.pending_last_words = [eliminated]
                self.phase = WerewolfPhase.DAY_LAST_WORDS
                return ActionResult(
                    success=True,
                    message="%s exiled, last words pending" % eliminated,
                    public_info={"eliminated": eliminated, "vote_counts": vote_counts},
                )

            # Check win after exile
            winner = self._check_win_condition()
            if winner:
                self.phase = WerewolfPhase.ENDED
                logger.info("Game ended after exile: %s wins", winner)
            else:
                # Next night
                self.round_number += 1
                self._start_night()
        else:
            # Tie — no one exiled, next night
            logger.info("Round %d: tie vote, no exile", self.round_number)
            self.round_number += 1
            self._start_night()

        return ActionResult(
            success=True,
            message="Votes resolved",
            public_info={"vote_counts": vote_counts},
        )

    # =========================================================================
    # Win condition
    # =========================================================================

    def _check_win_condition(self) -> str | None:
        """Return winning faction or None if game continues."""
        alive_wolves = sum(1 for w in self.wolf_ids if self.players[w].alive)
        alive_village = sum(
            1 for pid in self.player_order
            if self.players[pid].alive and self.players[pid].role != "werewolf"
        )

        if alive_wolves == 0:
            return FACTION_VILLAGE
        if alive_wolves >= alive_village:
            return FACTION_WOLF
        return None

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _tool(name: str, description: str, properties: dict,
              required: list[str] | None = None) -> dict:
        """Build an OpenAI-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required if required is not None else list(properties.keys()),
                },
            },
        }

    def _get_round_vote_eliminated(self, round_number: int) -> str | None:
        """Find who was vote-eliminated in a specific round."""
        votes = self.vote_history.get(round_number, {})
        if not votes:
            return None
        counts: dict[str, int] = {}
        for t in votes.values():
            counts[t] = counts.get(t, 0) + 1
        max_c = max(counts.values())
        top = [p for p, c in counts.items() if c == max_c]
        if len(top) == 1:
            return top[0]
        return None
