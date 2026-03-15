/**
 * Typewriter text effect — reveals text character by character.
 */

import { useState, useEffect, useRef } from "react";

interface AnimatedTextProps {
  text: string;
  /** Characters per second at 1x speed */
  speed?: number;
  /** Current playback speed multiplier */
  playbackSpeed?: number;
  onComplete?: () => void;
  className?: string;
}

export default function AnimatedText({
  text,
  speed = 15,
  playbackSpeed = 1,
  onComplete,
  className = "",
}: AnimatedTextProps) {
  const [displayedCount, setDisplayedCount] = useState(0);
  const completedRef = useRef(false);
  const textRef = useRef(text);

  // When text changes, reset everything synchronously
  if (text !== textRef.current) {
    textRef.current = text;
    completedRef.current = false;
    // This is fine in render — React handles it as initial state for the new text
  }

  // Reset count when text changes
  useEffect(() => {
    setDisplayedCount(0);
    completedRef.current = false;
  }, [text]);

  // Advance one character at a time
  useEffect(() => {
    // Guard: don't run with stale count after text change
    if (displayedCount > text.length) return;

    if (displayedCount >= text.length && text.length > 0) {
      if (!completedRef.current) {
        completedRef.current = true;
        onComplete?.();
      }
      return;
    }

    if (text.length === 0) return;

    const interval = 1000 / (speed * playbackSpeed);
    const timer = setTimeout(() => {
      setDisplayedCount((c) => {
        // Don't exceed current text length
        return c < text.length ? c + 1 : c;
      });
    }, interval);

    return () => clearTimeout(timer);
  }, [displayedCount, text, speed, playbackSpeed, onComplete]);

  const shown = Math.min(displayedCount, text.length);

  return (
    <span className={className}>
      {text.slice(0, shown)}
      {shown < text.length && (
        <span className="animate-pulse">|</span>
      )}
    </span>
  );
}
