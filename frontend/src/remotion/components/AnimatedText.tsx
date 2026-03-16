/**
 * Frame-driven typewriter text effect for Remotion.
 * Reveals text character by character based on current frame.
 */

import { useCurrentFrame, useVideoConfig } from "remotion";

interface AnimatedTextProps {
  text: string;
  /** Frame offset (relative to parent Sequence) when typing starts */
  startFrame?: number;
  /** Characters per second (default 15) */
  charsPerSecond?: number;
  className?: string;
  style?: React.CSSProperties;
  /** Show blinking cursor while typing */
  showCursor?: boolean;
}

export default function AnimatedText({
  text,
  startFrame = 0,
  charsPerSecond = 15,
  className = "",
  style,
  showCursor = true,
}: AnimatedTextProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const elapsed = Math.max(0, frame - startFrame);
  const visibleChars = Math.min(
    text.length,
    Math.floor((elapsed / fps) * charsPerSecond),
  );

  const isTyping = visibleChars < text.length;

  return (
    <span className={className} style={style}>
      {text.slice(0, visibleChars)}
      {showCursor && isTyping && (
        <span style={{ opacity: frame % 20 < 10 ? 1 : 0 }}>|</span>
      )}
    </span>
  );
}
