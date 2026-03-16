/**
 * Frame-driven fade in/out wrapper for Remotion.
 * Applies opacity transitions at the start and end of a scene.
 */

import type { ReactNode } from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

interface FadeTransitionProps {
  children: ReactNode;
  /** Total duration of the sequence this wraps (in frames) */
  durationInFrames: number;
  /** Fade in duration in frames (default 9 = ~300ms at 30fps) */
  fadeInFrames?: number;
  /** Fade out duration in frames (default 9) */
  fadeOutFrames?: number;
}

export default function FadeTransition({
  children,
  durationInFrames,
  fadeInFrames = 9,
  fadeOutFrames = 9,
}: FadeTransitionProps) {
  const frame = useCurrentFrame();
  const { fps: _fps } = useVideoConfig();

  const opacity = interpolate(
    frame,
    [0, fadeInFrames, durationInFrames - fadeOutFrames, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return <div style={{ opacity, width: "100%", height: "100%" }}>{children}</div>;
}
