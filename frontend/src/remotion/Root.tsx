/**
 * Remotion Root — defines the MasqueradeVideo composition.
 * calculateMetadata dynamically computes duration from the script.
 */

import React from "react";
import { Composition, staticFile } from "remotion";
import { getAudioDurationInSeconds } from "@remotion/media-utils";
import Video from "./Video";
import type { VideoProps } from "./Video";
import { buildFrameTimeline } from "./timeline";
import type { GameScript } from "@/types/game-script";

const FPS = 60;
const WIDTH = 2560;
const HEIGHT = 1440;

interface AudioManifestEntry {
  file: string;
  round: number;
  event_index: number;
  player_id: string;
}

interface AudioManifest {
  game_id: string;
  files: AudioManifestEntry[];
}

/**
 * Dynamically compute composition duration and build timeline.
 * Runs at bundle time before rendering starts.
 */
async function calculateMetadata({
  props,
}: {
  props: { scriptFile: string } & Partial<VideoProps>;
}): Promise<{
  durationInFrames: number;
  props: { scriptFile: string } & Partial<VideoProps>;
}> {
  const { scriptFile } = props;

  // Load GameScript
  const scriptUrl = staticFile(`scripts/${scriptFile}`);
  const scriptResp = await fetch(scriptUrl);
  if (!scriptResp.ok) {
    throw new Error(`Failed to load script: ${scriptFile} (${scriptResp.status})`);
  }
  const script = (await scriptResp.json()) as GameScript;

  // Derive gameId from filename
  const gameId = scriptFile.replace(/\.json$/, "");

  // Load audio manifest and get durations
  const audioDurations = new Map<string, number>();
  try {
    const manifestUrl = staticFile(`audio/${gameId}/manifest.json`);
    const manifestResp = await fetch(manifestUrl);
    if (manifestResp.ok) {
      const manifest = (await manifestResp.json()) as AudioManifest;
      // Get actual MP3 durations
      const durationPromises = manifest.files.map(async (entry) => {
        const key = `${entry.round}_${entry.event_index}_${entry.player_id}`;
        try {
          const audioUrl = staticFile(`audio/${gameId}/${entry.file}`);
          const duration = await getAudioDurationInSeconds(audioUrl);
          audioDurations.set(key, duration * 1000); // Convert to ms
        } catch {
          // Audio file missing or unreadable — skip
          console.warn(`Could not get duration for ${entry.file}`);
        }
      });
      await Promise.all(durationPromises);
      console.log(`Loaded ${audioDurations.size} audio durations`);
    }
  } catch {
    console.warn("No audio manifest found, rendering silent video");
  }

  // Build frame timeline
  const { scenes, totalFrames } = buildFrameTimeline(script, audioDurations, FPS, gameId);
  console.log(`Timeline: ${scenes.length} scenes, ${totalFrames} frames (${(totalFrames / FPS).toFixed(1)}s)`);

  return {
    durationInFrames: Math.max(totalFrames, 1),
    props: {
      ...props,
      script,
      scenes,
      gameId,
    },
  };
}

export const Root: React.FC = () => {
  return (
    <Composition
      id="MasqueradeVideo"
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      component={Video as any}
      width={WIDTH}
      height={HEIGHT}
      fps={FPS}
      durationInFrames={1}
      defaultProps={{ scriptFile: "" } as Record<string, unknown>}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      calculateMetadata={calculateMetadata as any}
    />
  );
};
