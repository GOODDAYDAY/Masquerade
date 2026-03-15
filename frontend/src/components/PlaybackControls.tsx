/**
 * F-06: Playback controls — play/pause, speed, progress.
 */

import { useTheater } from "@/components/Theater";
import type { Scene } from "@/core/timeline";

const SPEED_OPTIONS = [0.5, 1, 1.5, 2] as const;

function getSceneLabel(scene: Scene): string {
  switch (scene.type) {
    case "opening": return "开场";
    case "round-title": return `第${scene.round}轮 ${scene.phase === "speaking" ? "发言" : "投票"}`;
    case "speaking": return `第${scene.round}轮 发言`;
    case "voting": return `第${scene.round}轮 投票`;
    case "finale": return "结局";
  }
}

export default function PlaybackControls() {
  const {
    timeline, audioManager, isPlaying, currentIndex, totalScenes, speed,
    setIsPlaying, setSpeed,
  } = useTheater();

  const progress = totalScenes > 1 ? currentIndex / (totalScenes - 1) : 0;
  const handlePlayPause = () => {
    if (isPlaying) {
      timeline?.pause();
      audioManager?.pause();
    } else {
      timeline?.play();
      audioManager?.resume();
    }
    setIsPlaying(!isPlaying);
  };

  const handleProgressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const targetIndex = Math.round(Number(e.target.value) * (totalScenes - 1));
    timeline?.seekToScene(targetIndex);
  };

  const scenes = timeline?.getScenes() ?? [];
  const jumpTargets: { label: string; index: number }[] = [];
  scenes.forEach((scene, i) => {
    if (scene.type === "round-title" && scene.phase === "speaking") {
      jumpTargets.push({ label: `第 ${scene.round} 轮`, index: i });
    }
    if (scene.type === "finale") {
      jumpTargets.push({ label: "结局", index: i });
    }
  });

  const currentScene = timeline?.currentScene;

  return (
    <div className="shrink-0 bg-theater-surface border-t border-theater-border px-4 py-2.5">
      <div className="flex items-center gap-3">
        <button onClick={handlePlayPause} className="text-xl text-white hover:text-theater-accent transition-colors w-8 text-center">
          {isPlaying ? "⏸" : "▶"}
        </button>

        <div className="flex-1 flex items-center gap-2 min-w-0">
          <input type="range" min={0} max={1} step={0.001} value={progress} onChange={handleProgressChange}
            className="flex-1 h-1 accent-theater-accent cursor-pointer" />
          <span className="text-[11px] text-gray-500 w-14 text-right shrink-0">{currentIndex + 1}/{totalScenes}</span>
        </div>

        {currentScene && (
          <span className="text-[11px] text-gray-400 w-20 truncate shrink-0 hidden lg:block">{getSceneLabel(currentScene)}</span>
        )}

        <div className="flex gap-0.5 shrink-0">
          {SPEED_OPTIONS.map((s) => (
            <button key={s} onClick={() => { timeline?.setSpeed(s); setSpeed(s); }}
              className={`text-[11px] px-1.5 py-0.5 rounded ${speed === s ? "bg-theater-accent text-white" : "text-gray-500 hover:text-white"}`}>
              {s}x
            </button>
          ))}
        </div>

        <select className="bg-theater-bg text-[11px] text-gray-400 border border-theater-border rounded px-1.5 py-0.5 shrink-0"
          value="" onChange={(e) => { const idx = Number(e.target.value); if (!isNaN(idx)) timeline?.seekToScene(idx); }}>
          <option value="" disabled>跳转</option>
          {jumpTargets.map((t) => (<option key={t.index} value={t.index}>{t.label}</option>))}
        </select>
      </div>
    </div>
  );
}
