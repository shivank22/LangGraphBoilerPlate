import { useEffect, useState } from "react";

interface Props {
  text: string;
  active: boolean;
  speed?: number;
}

export function TypewriterText({ text, active, speed = 16 }: Props) {
  const [visibleCount, setVisibleCount] = useState(active ? 0 : text.length);

  useEffect(() => {
    if (!active) {
      setVisibleCount(text.length);
      return;
    }
    if (text.length < visibleCount) {
      setVisibleCount(0);
    }
  }, [active, text.length, visibleCount]);

  useEffect(() => {
    if (!active || visibleCount >= text.length) return;
    const timer = window.setTimeout(() => {
      setVisibleCount((count) => Math.min(count + 1, text.length));
    }, speed);
    return () => window.clearTimeout(timer);
  }, [active, text, visibleCount, speed]);

  const displayed = text.slice(0, visibleCount);
  const isTyping = active && visibleCount < text.length;

  return (
    <span className="typewriter-text">
      {displayed}
      {isTyping && <span className="typewriter-cursor" aria-hidden="true" />}
    </span>
  );
}
