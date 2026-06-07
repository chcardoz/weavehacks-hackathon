import { type LossPoint, sparklinePoints } from "@/lib/observability-types"

export function Sparkline({
  points,
  width = 120,
  height = 32,
  className,
}: {
  points: LossPoint[]
  width?: number
  height?: number
  className?: string
}) {
  const path = sparklinePoints(points, width, height)
  if (!path) {
    return (
      <svg
        width={width}
        height={height}
        className={className}
        aria-hidden="true"
      />
    )
  }
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role="img"
      aria-label="loss curve"
    >
      <polyline
        points={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
