/**
 * Theater container — full viewport layout.
 * Game-agnostic: header adapts to game type, renders all scene types.
 */

import { createContext, useContext, useState, useEffect, useCallback, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { GameScript, PlayerInfo } from "@/types/game-script";
import { TimelineController, type Scene } from "@/core/timeline";
import { AudioManager } from "@/core/audio-manager";
import OpeningScene from "@/components/scenes/OpeningScene";
import SpeakingScene from "@/components/scenes/SpeakingScene";
import ActionScene from "@/components/scenes/ActionScene";
import VotingScene from "@/components/scenes/VotingScene";
import FinaleScene from "@/components/scenes/FinaleScene";
import RoundTitle from "@/components/shared/RoundTitle";
import PlaybackControls from "@/components/PlaybackControls";
import SpeechHistory from "@/components/panels/SpeechHistory";
import ActionHistory from "@/components/panels/ActionHistory";

// --- Theater context ---

interface TheaterContextValue {
  timeline: TimelineController | null;
  audioManager: AudioManager | null;
  isPlaying: boolean;
  currentIndex: number;
  totalScenes: number;
  speed: number;
  eliminatedIds: string[];
  setIsPlaying: (v: boolean) => void;
  setSpeed: (v: number) => void;
}

const TheaterContext = createContext<TheaterContextValue | null>(null);

export function useTheater(): TheaterContextValue {
  const ctx = useContext(TheaterContext);
  if (!ctx) throw new Error("useTheater must be used within Theater");
  return ctx;
}

// --- Game type labels ---

const GAME_LABELS: Record<string, string> = {
  spy: "谁是卧底",
  werewolf: "狼人杀",
};

// --- Theater component ---

interface TheaterProps {
  script: GameScript;
  gameId: string;
  autoplay?: boolean;
}

export default function Theater({ script, gameId, autoplay = false }: TheaterProps) {
  const [timeline, setTimeline] = useState<TimelineController | null>(null);
  const [audioManager, setAudioManager] = useState<AudioManager | null>(null);
  const [currentScene, setCurrentScene] = useState<Scene | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    const tl = new TimelineController(script);
    const am = new AudioManager();

    if (tl.currentScene) {
      setCurrentScene(tl.currentScene);
      setCurrentIndex(tl.currentIndex);
    }

    tl.addListener({
      onSceneChange: (scene, index) => { setCurrentScene(scene); setCurrentIndex(index); },
      onPlayStateChange: (playing) => setIsPlaying(playing),
      onComplete: () => setIsPlaying(false),
    });

    setTimeline(tl);

    // Preload all audio files, then set audioManager so children see it ready
    am.loadAndPreload(`/output/audio/${gameId}`).then(() => {
      setAudioManager(am);
    });

    return () => { tl.destroy(); am.destroy(); };
  }, [script, gameId]);

  // Track playback completion for automated recording
  const [playbackComplete, setPlaybackComplete] = useState(false);

  // Auto-start playback when autoplay is enabled (for headless recording)
  useEffect(() => {
    if (!autoplay || !timeline) return;
    timeline.addListener({
      onComplete: () => setPlaybackComplete(true),
    });
    const timer = setTimeout(() => {
      timeline.play();
      setIsPlaying(true);
    }, 2000);
    return () => clearTimeout(timer);
  }, [autoplay, timeline]);

  const handleSceneComplete = useCallback(() => {
    timeline?.markSceneComplete();
  }, [timeline]);

  const eliminatedIds = useMemo(() => {
    const ids: string[] = [];
    const allScenes = timeline?.getScenes() ?? [];
    for (let i = 0; i <= currentIndex; i++) {
      const s = allScenes[i];
      if (s?.type === "voting" && s.voteResult.eliminated) {
        ids.push(s.voteResult.eliminated);
      }
    }
    return ids;
  }, [currentIndex, timeline]);

  // Collect events for side panels — only show PREVIOUS rounds (not current)
  const { speechEvents, actionEvents } = useMemo(() => {
    const speech: { event: import("@/types/game-script").GameEvent; round: number }[] = [];
    const action: { event: import("@/types/game-script").GameEvent; round: number }[] = [];
    const allScenes = timeline?.getScenes() ?? [];

    // Find current round number
    const currentSceneObj = allScenes[currentIndex];
    const currentRound = currentSceneObj && "round" in currentSceneObj ? currentSceneObj.round : 0;

    for (let i = 0; i <= currentIndex; i++) {
      const s = allScenes[i];
      if (!s) continue;
      // Only include events from previous rounds
      const sceneRound = "round" in s ? s.round : 0;
      if (sceneRound >= currentRound) continue;

      if (s.type === "speaking") {
        speech.push({ event: s.event, round: s.round });
      } else if (s.type === "action") {
        action.push({ event: s.event, round: s.round });
      } else if (s.type === "voting") {
        for (const ve of s.events) {
          action.push({ event: ve, round: s.round });
        }
      }
    }
    return { speechEvents: speech, actionEvents: action };
  }, [currentIndex, timeline]);

  const contextValue: TheaterContextValue = {
    timeline, audioManager, isPlaying, currentIndex,
    totalScenes: timeline?.totalScenes ?? 0,
    speed, eliminatedIds, setIsPlaying, setSpeed,
  };

  return (
    <TheaterContext.Provider value={contextValue}>
      <div className="h-screen w-screen flex flex-col bg-theater-bg overflow-hidden">
        {/* Header — adapts to game type */}
        <div className="shrink-0 bg-theater-surface/80 border-b border-theater-border px-4 py-2 flex items-center justify-center gap-6 text-sm">
          {renderHeader(script)}
        </div>

        <div className="flex-1 min-h-0 flex">
          {/* Left panel — action history (hidden below xl:1280px) */}
          <aside className="hidden xl:flex w-[280px] shrink-0 border-r border-theater-border bg-theater-bg/90 flex-col">
            <div className="px-3 py-1.5 border-b border-theater-border">
              <span className="text-sm text-gray-500 font-bold">🎬 行动记录</span>
            </div>
            <div className="flex-1 min-h-0">
              <ActionHistory events={actionEvents} players={script.players} currentEventIndex={currentIndex} />
            </div>
          </aside>

          {/* Main scene area */}
          <main className="flex-1 min-h-0 overflow-y-auto">
            <AnimatePresence mode="wait">
              {currentScene && (
                <motion.div
                  key={`${currentScene.type}-${currentIndex}`}
                  className="h-full w-full"
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }} transition={{ duration: 0.3 }}
                >
                  {renderScene(currentScene, script, handleSceneComplete)}
                </motion.div>
              )}
            </AnimatePresence>
          </main>

          {/* Right panel — speech history (hidden below lg:1024px) */}
          <aside className="hidden lg:flex w-[280px] shrink-0 border-l border-theater-border bg-theater-bg/90 flex-col">
            <div className="px-3 py-1.5 border-b border-theater-border">
              <span className="text-sm text-gray-500 font-bold">💬 发言记录</span>
            </div>
            <div className="flex-1 min-h-0">
              <SpeechHistory events={speechEvents} players={script.players} currentEventIndex={currentIndex} />
            </div>
          </aside>
        </div>

        <PlaybackControls />

        {/* Hidden marker for Playwright to detect playback completion */}
        {playbackComplete && <div id="playback-complete" data-complete="true" style={{ display: "none" }} />}
      </div>
    </TheaterContext.Provider>
  );
}

// --- Header rendering by game type ---

function renderHeader(script: GameScript) {
  const gameType = script.game.type;

  if (gameType === "spy") {
    return <SpyHeader players={script.players} />;
  }

  // Generic header: game label + player count
  const label = GAME_LABELS[gameType] ?? gameType;
  return <span className="text-gray-400 font-bold">{label} · {script.players.length}人局</span>;
}

function SpyHeader({ players }: { players: PlayerInfo[] }) {
  const isAllBlank = players.every((p) => p.role === "blank");
  const hasBlank = players.some((p) => p.role === "blank");
  const civilianWord = players.find((p) => p.role === "civilian")?.word ?? "";
  const spyWord = players.find((p) => p.role === "spy")?.word ?? "";

  if (isAllBlank) {
    return <span className="text-gray-400 font-bold">全员白板模式（无词）</span>;
  }

  return (
    <>
      <div className="flex items-center gap-2">
        <span className="text-gray-500">平民词</span>
        <span className="font-bold text-theater-accent">{civilianWord}</span>
      </div>
      <span className="text-gray-700">|</span>
      <div className="flex items-center gap-2">
        <span className="text-gray-500">卧底词</span>
        <span className="font-bold text-theater-danger">{spyWord}</span>
      </div>
      {hasBlank && (
        <>
          <span className="text-gray-700">|</span>
          <div className="flex items-center gap-2">
            <span className="text-gray-500">白板</span>
            <span className="font-bold text-gray-400">无词</span>
          </div>
        </>
      )}
    </>
  );
}

// --- Scene rendering ---

function renderScene(scene: Scene, script: GameScript, onComplete: () => void) {
  switch (scene.type) {
    case "opening":
      return <OpeningScene players={scene.players} gameInfo={scene.gameInfo} onComplete={onComplete} />;
    case "round-title":
      return <RoundTitle round={scene.round} phase={scene.phase} onComplete={onComplete} />;
    case "speaking":
      return <SpeakingScene event={scene.event} round={scene.round} eventIndex={scene.eventIndex} players={script.players} onComplete={onComplete} />;
    case "action":
      return <ActionScene event={scene.event} round={scene.round} eventIndex={scene.eventIndex} players={script.players} onComplete={onComplete} />;
    case "voting":
      return <VotingScene voteResult={scene.voteResult} events={scene.events} players={script.players} onComplete={onComplete} />;
    case "finale":
      return <FinaleScene result={scene.result} players={scene.players} onComplete={onComplete} />;
  }
}
