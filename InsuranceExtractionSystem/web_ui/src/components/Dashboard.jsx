import { useState, useEffect } from 'react'
import axios from 'axios'
import {
  FileSearch, ClipboardCheck, Activity, Database,
  Server, AlertCircle, CheckCircle2, Clock, BarChart3
} from 'lucide-react'

export default function Dashboard({ onNavigate }) {
  const [status, setStatus] = useState(null)
  const [reviewStats, setReviewStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [statusRes, reviewRes] = await Promise.all([
          axios.get('/api/admin/status'),
          axios.get('/api/review/stats'),
        ])
        setStatus(statusRes.data)
        setReviewStats(reviewRes.data)
      } catch (e) {
        console.error('Dashboard fetch error:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <Clock className="animate-pulse mr-2" size={20} /> Loading...
      </div>
    )
  }

  const cards = [
    {
      title: '등록 약관',
      value: status?.total_policies ?? 0,
      icon: Database,
      color: 'blue',
      desc: 'Stored Policies',
    },
    {
      title: '추출 결과',
      value: status?.total_extractions ?? 0,
      icon: BarChart3,
      color: 'indigo',
      desc: 'Extraction Results',
    },
    {
      title: '리뷰 대기',
      value: status?.pending_reviews ?? 0,
      icon: ClipboardCheck,
      color: reviewStats?.pending > 0 ? 'amber' : 'green',
      desc: 'Pending Reviews',
      onClick: () => onNavigate('review'),
    },
    {
      title: 'Providers',
      value: status?.providers?.filter(p => p.configured).length ?? 0,
      icon: Server,
      color: 'emerald',
      desc: `/ ${status?.providers?.length ?? 0} configured`,
    },
  ]

  const colorClasses = {
    blue:    { bg: 'bg-blue-900/30',    border: 'border-blue-800/50',    icon: 'text-blue-400',    text: 'text-blue-300' },
    indigo:  { bg: 'bg-indigo-900/30',  border: 'border-indigo-800/50',  icon: 'text-indigo-400',  text: 'text-indigo-300' },
    amber:   { bg: 'bg-amber-900/30',   border: 'border-amber-800/50',   icon: 'text-amber-400',   text: 'text-amber-300' },
    green:   { bg: 'bg-green-900/30',   border: 'border-green-800/50',   icon: 'text-green-400',   text: 'text-green-300' },
    emerald: { bg: 'bg-emerald-900/30', border: 'border-emerald-800/50', icon: 'text-emerald-400', text: 'text-emerald-300' },
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        {cards.map(card => {
          const Icon = card.icon
          const cls = colorClasses[card.color]
          return (
            <div
              key={card.title}
              onClick={card.onClick}
              className={`${cls.bg} border ${cls.border} rounded-xl p-5 ${card.onClick ? 'cursor-pointer hover:brightness-110' : ''} transition-all`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-gray-400">{card.title}</span>
                <Icon size={18} className={cls.icon} />
              </div>
              <div className={`text-3xl font-bold ${cls.text}`}>{card.value}</div>
              <p className="text-[10px] text-gray-500 mt-1">{card.desc}</p>
            </div>
          )
        })}
      </div>

      {/* Provider Status */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <Server size={16} className="text-blue-400" />
          LLM Provider Status
        </h2>
        <div className="grid grid-cols-3 gap-3">
          {(status?.providers ?? []).map(p => (
            <div key={p.name} className={`flex items-center gap-3 p-3 rounded-lg border ${
              p.configured
                ? 'border-green-800/50 bg-green-900/10'
                : 'border-gray-800 bg-gray-900/30'
            }`}>
              {p.configured
                ? <CheckCircle2 size={16} className="text-green-400" />
                : <AlertCircle size={16} className="text-gray-600" />
              }
              <div>
                <p className={`text-sm font-medium ${p.configured ? 'text-green-300' : 'text-gray-500'}`}>
                  {p.name}
                </p>
                <p className="text-[10px] text-gray-600">
                  {p.configured ? p.model_name || 'Configured' : 'Not configured'}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-4">
        <button
          onClick={() => onNavigate('extraction')}
          className="flex items-center gap-3 p-4 rounded-xl border border-gray-800 bg-gray-900/30 hover:bg-blue-900/20 hover:border-blue-800/50 transition-all group"
        >
          <FileSearch size={24} className="text-gray-500 group-hover:text-blue-400 transition-colors" />
          <div className="text-left">
            <p className="text-sm font-semibold text-gray-300 group-hover:text-blue-300">추출 분석</p>
            <p className="text-[10px] text-gray-600">PDF 업로드 + AI 추출</p>
          </div>
        </button>
        <button
          onClick={() => onNavigate('review')}
          className="flex items-center gap-3 p-4 rounded-xl border border-gray-800 bg-gray-900/30 hover:bg-amber-900/20 hover:border-amber-800/50 transition-all group"
        >
          <ClipboardCheck size={24} className="text-gray-500 group-hover:text-amber-400 transition-colors" />
          <div className="text-left">
            <p className="text-sm font-semibold text-gray-300 group-hover:text-amber-300">HITL 리뷰</p>
            <p className="text-[10px] text-gray-600">{reviewStats?.pending ?? 0}건 대기 중</p>
          </div>
        </button>
        <button
          onClick={() => onNavigate('pipeline')}
          className="flex items-center gap-3 p-4 rounded-xl border border-gray-800 bg-gray-900/30 hover:bg-indigo-900/20 hover:border-indigo-800/50 transition-all group"
        >
          <Activity size={24} className="text-gray-500 group-hover:text-indigo-400 transition-colors" />
          <div className="text-left">
            <p className="text-sm font-semibold text-gray-300 group-hover:text-indigo-300">파이프라인</p>
            <p className="text-[10px] text-gray-600">M1 ~ M8 자동 실행</p>
          </div>
        </button>
      </div>

      {/* Review Stats */}
      {reviewStats && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <ClipboardCheck size={16} className="text-amber-400" />
            Review Statistics
          </h2>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-amber-500" />
              <span className="text-xs text-gray-400">Pending:</span>
              <span className="text-sm font-bold text-amber-300">{reviewStats.pending}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-green-500" />
              <span className="text-xs text-gray-400">Approved:</span>
              <span className="text-sm font-bold text-green-300">{reviewStats.approved}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500" />
              <span className="text-xs text-gray-400">Rejected:</span>
              <span className="text-sm font-bold text-red-300">{reviewStats.rejected}</span>
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-xs text-gray-500">Total:</span>
              <span className="text-sm font-bold text-gray-300">{reviewStats.total}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
