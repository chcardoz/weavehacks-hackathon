"use client"

import { useEffect, useState } from "react"

// A clock that ticks every `intervalMs` so countdowns / "Xs ago" stay live.
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}
