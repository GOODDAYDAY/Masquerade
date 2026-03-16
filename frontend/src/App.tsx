/**
 * Root component — switches between ScriptLoader and Theater.
 * Supports auto-loading script via URL parameter: ?script=game_werewolf_xxx.json
 */

import { useState, useCallback, useEffect } from "react";
import type { GameScript } from "@/types/game-script";
import { isValidGameScript } from "@/types/game-script";
import ScriptLoader from "@/components/ScriptLoader";
import Theater from "@/components/Theater";

export default function App() {
  const [script, setScript] = useState<GameScript | null>(null);
  const [gameId, setGameId] = useState("");

  const handleLoad = useCallback((loadedScript: GameScript, filename: string) => {
    const id = filename.replace(/\.json$/, "");
    setGameId(id);
    setScript(loadedScript);
  }, []);

  // Auto-load script from URL parameter: ?script=game_werewolf_xxx.json
  // Add &autoplay=true to auto-start playback (for headless recording)
  const [autoplay, setAutoplay] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const scriptFile = params.get("script");
    if (params.get("autoplay") === "true") setAutoplay(true);
    if (!scriptFile || script) return;

    fetch(`/output/scripts/${scriptFile}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load ${scriptFile}: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (isValidGameScript(data)) {
          handleLoad(data as GameScript, scriptFile);
        } else {
          console.error("Invalid game script:", scriptFile);
        }
      })
      .catch((err) => console.error("Auto-load failed:", err));
  }, [script, handleLoad]);

  if (!script) {
    return <ScriptLoader onLoad={handleLoad} />;
  }

  return <Theater script={script} gameId={gameId} autoplay={autoplay} />;
}
