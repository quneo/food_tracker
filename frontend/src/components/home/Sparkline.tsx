/** A small line of values, oldest first; the last point is marked. */
export function Sparkline({
  values,
  width = 140,
  height = 48,
  label,
}: {
  values: number[]
  width?: number
  height?: number
  label: string
}) {
  if (values.length < 2) return null
  const low = Math.min(...values)
  const high = Math.max(...values)
  const span = high - low || 1
  const pad = 5
  const points = values.map((value, index) => [
    pad + (index / (values.length - 1)) * (width - pad * 2),
    pad + (1 - (value - low) / span) * (height - pad * 2),
  ])
  const line = points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
  const [lastX, lastY] = points[points.length - 1]
  const area = `${line.join(' ')} L${lastX.toFixed(1)},${height} L${points[0][0].toFixed(1)},${height} Z`
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className="sparkline shrink-0"
      role="img"
      aria-label={label}
    >
      <path className="area" d={area} />
      <path className="line" d={line.join(' ')} />
      <circle cx={lastX} cy={lastY} r="3.5" />
    </svg>
  )
}
