/**
 * Theater container — full viewport layout.
 * Word pair always visible. Plays pre-generated TTS audio.
 */

import { createContext, useContext, useState, useEffect, useCallback, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { GameScript } from "@/types/game-script";
import { TimelineController, type Scene } from "@/core/timeline";
import { AudioManager } from "@/core/audio-manager";
import OpeningScene from "@/components/scenes/OpeningScene";
import SpeakingScene from "@/components/scenes/SpeakingScene";
import VotingScene from "@/components/scenes/VotingScene";
import FinaleScene from "@/components/scenes/FinaleScene";
import RoundTitle from "@/components/shared/RoundTitle";
import PlaybackControls from "@/components/PlaybackControls";

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

// --- Theater component ---

interface TheaterProps {
  script: GameScript;
  gameId: string;
}

export default function Theater({ script, gameId }: TheaterProps) {
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

  const civilianWord = script.players.find((p) => p.role === "civilian")?.word ?? "";
  const spyWord = script.players.find((p) => p.role === "spy")?.word ?? "";

  const contextValue: TheaterContextValue = {
    timeline, audioManager, isPlaying, currentIndex,
    totalScenes: timeline?.totalScenes ?? 0,
    speed, eliminatedIds, setIsPlaying, setSpeed,
  };

  return (
    <TheaterContext.Provider value={contextValue}>
      <div className="h-screen w-screen flex flex-col bg-theater-bg overflow-hidden">
        <div className="shrink-0 bg-theater-surface/80 border-b border-theater-border px-4 py-2 flex items-center justify-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-gray-500">平民词</span>
            <span className="font-bold text-theater-accent">{civilianWord}</span>
          </div>
          <span className="text-gray-700">|</span>
          <div className="flex items-center gap-2">
            <span className="text-gray-500">卧底词</span>
            <span className="font-bold text-theater-danger">{spyWord}</span>
          </div>
        </div>

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

        <PlaybackControls />
      </div>
    </TheaterContext.Provider>
  );
}

function renderScene(scene: Scene, script: GameScript, onComplete: () => void) {
  switch (scene.type) {
    case "opening":
      return <OpeningScene players={scene.players} gameInfo={scene.gameInfo} onComplete={onComplete} />;
    case "round-title":
      return <RoundTitle round={scene.round} phase={scene.phase} onComplete={onComplete} />;
    case "speaking":
      return <SpeakingScene event={scene.event} round={scene.round} eventIndex={scene.eventIndex} players={script.players} onComplete={onComplete} />;
    case "voting":
      return <VotingScene voteResult={scene.voteResult} events={scene.events} players={script.players} onComplete={onComplete} />;
    case "finale":
      return <FinaleScene result={scene.result} players={scene.players} onComplete={onComplete} />;
  }
}
