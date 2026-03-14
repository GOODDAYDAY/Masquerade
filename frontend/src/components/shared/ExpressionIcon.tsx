/**
 * Maps expression field values to visual emoji/text indicators.
 */

const EXPRESSION_MAP: Record<string, string> = {
  neutral: "😐",
  thinking: "🤔",
  surprised: "😮",
  smile: "😊",
  confident: "😎",
  serious: "😑",
  angry: "😠",
};

interface ExpressionIconProps {
  expression: string;
  size?: number;
}

export default function ExpressionIcon({
  expression,
  size = 24,
}: ExpressionIconProps) {
  const emoji = EXPRESSION_MAP[expression] ?? EXPRESSION_MAP["neutral"]!;
  return (
    <span style={{ fontSize: size }} role="img" aria-label={expression}>
      {emoji}
    </span>
  );
}
