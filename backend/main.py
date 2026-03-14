"""CLI entry point — select a game, load its config, run it, output the script."""

import argparse
import asyncio
import sys

import backend.engine  # noqa: F401 — trigger game engine registration

from backend.core.config import load_app_settings, load_yaml
from backend.core.logging import get_logger, setup_logging
from backend.engine.registry import list_games
from backend.orchestrator.runner import GameRunner


def main() -> None:
    available = list_games()
    parser = argparse.ArgumentParser(description="Masquerade — AI Board Game Arena")
    parser.add_argument(
        "game",
        nargs="?",
        default=None,
        help="Game to play (available: %s)" % ", ".join(available),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to game config YAML (default: config/games/<game>.yaml)",
    )
    parser.add_argument(
        "--app-config",
        default="config/app_config.yaml",
        help="Path to app config YAML (default: config/app_config.yaml)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available games and exit",
    )
    args = parser.parse_args()

    if args.list:
        print("Available games: %s" % ", ".join(available))
        sys.exit(0)

    if not args.game:
        parser.error("Please specify a game to play. Available: %s" % ", ".join(available))

    game_type = args.game
    if game_type not in available:
        parser.error("Unknown game '%s'. Available: %s" % (game_type, ", ".join(available)))

    # Load configs
    app_settings = load_app_settings(args.app_config)
    setup_logging(level=app_settings.log_level, log_dir=app_settings.log_dir)
    logger = get_logger("main")

    config_path = args.config or "config/games/%s.yaml" % game_type
    try:
        game_config = load_yaml(config_path)
    except Exception as e:
        print("Error loading game config: %s" % e, file=sys.stderr)
        sys.exit(1)

    logger.info("Starting game: type=%s, config=%s", game_type, config_path)

    # Run the game
    runner = GameRunner(game_type, game_config, app_settings)
    script = asyncio.run(runner.run())

    # Output result
    if script.result:
        print("\n=== Game Complete ===")
        print("Winner: %s" % script.result.winner)
        print("Rounds: %d" % script.result.total_rounds)
        print("Eliminated: %s" % ", ".join(script.result.eliminated_order))
    else:
        print("\nGame ended without result")


if __name__ == "__main__":
    main()
