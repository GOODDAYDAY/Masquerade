/**
 * Root component — switches between ScriptLoader and Theater.
 */

import { useState, useCallback } from "react";
import type { GameScript } from "@/types/game-script";
import ScriptLoader from "@/components/ScriptLoader";
import Theater from "@/components/Theater";

export default function App() {
  const [script, setScript] = useState<GameScript | null>(null);
  const [gameId, setGameId] = useState("");

  const handleLoad = useCallback((loadedScript: GameScript, filename: string) => {
    // game_id = filename without .json extension
    const id = filename.replace(/\.json$/, "");
    setGameId(id);
    setScript(loadedScript);
  }, []);

  if (!script) {
    return <ScriptLoader onLoad={handleLoad} />;
  }

  return <Theater script={script} gameId={gameId} />;
}
