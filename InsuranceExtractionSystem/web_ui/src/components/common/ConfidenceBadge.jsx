/**
 * Confidence 레벨 뱃지
 * high (>=95%) = green, medium (>=70%) = yellow, low (<70%) = red
 */
export default function ConfidenceBadge({ value }) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-gray-700 text-xs">-</span>
  }

  const numVal = typeof value === 'number' ? value : parseFloat(value)
  let level = 'low'
  if (numVal >= 95) level = 'high'
  else if (numVal >= 70) level = 'medium'

  const styles = {
    high:   'bg-green-900/50 text-green-300 border-green-800',
    medium: 'bg-yellow-900/50 text-yellow-300 border-yellow-800',
    low:    'bg-red-900/50 text-red-300 border-red-800',
  }

  const label = typeof value === 'string' ? value : `${numVal.toFixed(0)}%`

  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${styles[level]}`}>
      {label}
    </span>
  )
}
