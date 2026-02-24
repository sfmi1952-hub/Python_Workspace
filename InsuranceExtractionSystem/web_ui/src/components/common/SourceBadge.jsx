/**
 * 추출 소스 뱃지
 */
const SOURCE_MAP = {
  appendix:           { label: '별표',       style: 'bg-blue-900/40 text-blue-300' },
  policy_text:        { label: '약관본문',   style: 'bg-indigo-900/40 text-indigo-300' },
  mapping_table:      { label: '매핑테이블', style: 'bg-purple-900/40 text-purple-300' },
  external_knowledge: { label: '외부지식',   style: 'bg-gray-800 text-gray-400' },
  gemini:             { label: 'Gemini',     style: 'bg-cyan-900/40 text-cyan-300' },
  openai:             { label: 'OpenAI',     style: 'bg-emerald-900/40 text-emerald-300' },
  claude:             { label: 'Claude',     style: 'bg-orange-900/40 text-orange-300' },
  ensemble:           { label: 'Ensemble',   style: 'bg-amber-900/40 text-amber-300' },
}

export default function SourceBadge({ value }) {
  if (!value) return <span className="text-gray-700 text-xs">-</span>

  const entry = SOURCE_MAP[value] || { label: value, style: 'bg-gray-800 text-gray-400' }

  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${entry.style}`}>
      {entry.label}
    </span>
  )
}
