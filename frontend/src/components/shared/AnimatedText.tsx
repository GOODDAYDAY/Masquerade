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

  useEffect(() => {
    setDisplayedCount(0);
    completedRef.current = false;
  }, [text]);

  useEffect(() => {
    if (displayedCount >= text.length) {
      if (!completedRef.current) {
        completedRef.current = true;
        onComplete?.();
      }
      return;
    }

    const interval = 1000 / (speed * playbackSpeed);
    const timer = setTimeout(() => {
      setDisplayedCount((c) => c + 1);
    }, interval);

    return () => clearTimeout(timer);
  }, [displayedCount, text, speed, playbackSpeed, onComplete]);

  return (
    <span className={className}>
      {text.slice(0, displayedCount)}
      {displayedCount < text.length && (
        <span className="animate-pulse">|</span>
      )}
    </span>
  );
}
