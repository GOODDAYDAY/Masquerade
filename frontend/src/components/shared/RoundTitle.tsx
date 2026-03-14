/**
 * Animated round/phase title overlay.
 */

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";

interface RoundTitleProps {
  round: number;
  phase: "speaking" | "voting";
  onComplete?: () => void;
}

const PHASE_LABELS: Record<string, string> = {
  speaking: "发言阶段",
  voting: "投票阶段",
};

export default function RoundTitle({ round, phase, onComplete }: RoundTitleProps) {
  const firedRef = useRef(false);

  // Fire onComplete after display duration, cleanup on unmount
  useEffect(() => {
    firedRef.current = false;
    const timer = setTimeout(() => {
      if (!firedRef.current) {
        firedRef.current = true;
        onComplete?.();
      }
    }, 2100); // 0.6s animation + 1.5s reading time
    return () => clearTimeout(timer);
  }, [round, phase, onComplete]);

  return (
    <motion.div
      className="flex flex-col items-center justify-center h-full"
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6 }}
    >
      <h2 className="text-5xl font-bold text-white mb-4">
        第 {round} 轮
      </h2>
      <p className="text-2xl text-theater-accent">
        {PHASE_LABELS[phase] ?? phase}
      </p>
    </motion.div>
  );
}
