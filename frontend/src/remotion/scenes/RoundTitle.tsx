/**
 * Remotion round/phase title overlay — fade in, hold, fade out.
 */

import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import type { RoundTitleData } from "../timeline";

const PHASE_LABELS: Record<string, string> = {
  "round-start": "开始",
  speaking: "发言阶段",
  voting: "投票阶段",
};

interface RoundTitleProps {
  data: RoundTitleData;
  durationInFrames: number;
}

export default function RoundTitle({ data, durationInFrames }: RoundTitleProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Fade in 0-9, hold, fade out last 9 frames
  const opacity = interpolate(
    frame,
    [0, 9, durationInFrames - 9, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Scale spring for the round number
  const scale = spring({ frame, fps, config: { damping: 12, stiffness: 100 } });

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      height: "100%", opacity,
    }}>
      <h2 style={{
        fontSize: 88, fontWeight: "bold", color: "white",
        marginBottom: 30, transform: `scale(${scale})`,
      }}>
        第 {data.round} 轮
      </h2>
      <p style={{ fontSize: 44, color: "#6366f1" }}>
        {PHASE_LABELS[data.phase] ?? data.phase}
      </p>
    </div>
  );
}
