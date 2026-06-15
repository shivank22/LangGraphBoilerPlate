import { useEffect, useRef, useState } from "react";

const TICK_MS = 16;
const GROWTH_BASE = 2;

function charsPerTick(elapsedSec: number): number {
  return Math.max(1, Math.floor(Math.pow(GROWTH_BASE, elapsedSec)));
}

export function useAcceleratingTypewriter(text: string, active: boolean) {
  const [visibleCount, setVisibleCount] = useState(active ? 0 : text.length);
  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      setVisibleCount(text.length);
      startTimeRef.current = null;
      return;
    }
    if (text.length < visibleCount) {
      setVisibleCount(0);
    }
    if (startTimeRef.current === null) {
      startTimeRef.current = Date.now();
    }
  }, [active, text.length, visibleCount]);

  useEffect(() => {
    if (!active || visibleCount >= text.length) return;

    const elapsedSec = (Date.now() - (startTimeRef.current ?? Date.now())) / 1000;
    const batch = charsPerTick(elapsedSec);

    const timer = window.setTimeout(() => {
      setVisibleCount((count) => Math.min(count + batch, text.length));
    }, TICK_MS);

    return () => window.clearTimeout(timer);
  }, [active, text.length, visibleCount]);

  return {
    displayed: text.slice(0, visibleCount),
    isTyping: active && visibleCount < text.length,
  };
}
