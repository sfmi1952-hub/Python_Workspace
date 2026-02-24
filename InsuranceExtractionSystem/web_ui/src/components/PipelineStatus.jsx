import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import {
  Activity, Play, Square, CheckCircle, XCircle, Clock,
  Loader2, Download, Send, FileCheck, RefreshCw
} from 'lucide-react'

const STEPS = [
  { key: 'crawl',      label: 'M1 Crawl',      desc: '약관 수집' },
  { key: 'store',       label: 'M2 Store',       desc: '저장소 적재' },
  { key: 'preprocess',  label: 'M3 Preprocess',  desc: '전처리' },
  { key: 'index',       label: 'M4 Index',       desc: 'RAG 인덱싱' },
  { key: 'extract',     label: 'M5 Extract',     desc: 'AI 추출' },
  { key: 'map',         label: 'M6 Map',         desc: '코드 매핑' },
  { key: 'validate',    label: 'M7 Validate',    desc: '검증/HITL' },
  { key: 'output',      label: 'M8 Output',      desc: 'DB 적재' },
  { key: 'transfer',    label: 'GW1 Transfer',   desc: '파일 전송' },
]

const PROVIDERS = [
  { id: 'gemini', label: 'Gemini 3.1 Pro' },
  { id: 'openai', label: 'GPT-5.2' },
  { id: 'claude', label: 'Claude Sonnet 4.6' },
]

export default function PipelineStatus() {
  const [status, setStatus] = useState(null)
  const [provider, setProvider] = useState('gemini')
  const [ensemble, setEnsemble] = useState(false)
  const [skipCrawl, setSkipCrawl] = useState(false)
  const [skipTransfer, setSkipTransfer] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const logRef = useRef(null)

  const fetchStatus = async () => {
    try {
      const res = await axios.get('/api/pipeline/status')
      setStatus(res.data)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 2000)
    return () => clearInterval(interval)
  }, [])

  // Auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [status?.logs])

  const handleTrigger = async () => {
    setTriggering(true)
    try {
      await axios.post('/api/pipeline/trigger', {
        provider,
        ensemble,
        skip_crawl: skipCrawl,
        skip_transfer: skipTransfer,
      })
      fetchStatus()
    } catch (err) {
      alert(err.response?.data?.detail || 'Pipeline trigger failed')
    } finally {
      setTriggering(false)
    }
  }

  const handleExportCsv = async () => {
    try {
      const res = await axios.post('/api/pipeline/export-csv')
      alert(res.data.message)
    } catch (err) {
      alert(err.response?.data?.detail || 'Export failed')
    }
  }

  const handleValidate = async () => {
    try {
      const res = await axios.post('/api/pipeline/validate')
      alert(res.data.message)
    } catch (err) {
      alert(err.response?.data?.detail || 'Validation failed')
    }
  }

  const isRunning = status?.status === 'running'
  const currentStepIdx = STEPS.findIndex(s => s.key === status?.current_step)

  const statusColor = {
    idle: 'text-gray-500',
    running: 'text-blue-400',
    completed: 'text-green-400',
    failed: 'text-red-400',
  }

  return (
    <div className="h-full flex flex-col p-6 bg-gray-950 overflow-hidden">
      <div className="flex gap-6 flex-1 overflow-hidden">
        {/* Left: Controls */}
        <div className="w-72 flex flex-col gap-3 shrink-0">
          {/* Pipeline Control */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
              <Activity size={16} className="text-blue-400" />
              Pipeline Control
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-gray-500 mb-1 block">Provider</label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  disabled={isRunning}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-xs text-white disabled:opacity-50"
                >
                  {PROVIDERS.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                  <input type="checkbox" checked={ensemble} onChange={(e) => setEnsemble(e.target.checked)} disabled={isRunning} className="rounded" />
                  Ensemble
                </label>
                <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                  <input type="checkbox" checked={skipCrawl} onChange={(e) => setSkipCrawl(e.target.checked)} disabled={isRunning} className="rounded" />
                  Skip Crawl
                </label>
              </div>

              <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                <input type="checkbox" checked={skipTransfer} onChange={(e) => setSkipTransfer(e.target.checked)} disabled={isRunning} className="rounded" />
                Skip Transfer
              </label>

              <button
                onClick={handleTrigger}
                disabled={isRunning || triggering}
                className="w-full py-2.5 rounded-lg font-bold text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white"
              >
                {triggering || isRunning ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                {isRunning ? 'Running...' : 'Run Pipeline'}
              </button>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 space-y-2">
            <h3 className="text-xs font-semibold text-gray-400 mb-2">Quick Actions</h3>
            <button
              onClick={handleValidate}
              className="w-full py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
            >
              <FileCheck size={14} /> Run Validation (M7)
            </button>
            <button
              onClick={handleExportCsv}
              className="w-full py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
            >
              <Download size={14} /> Export CSV (M8)
            </button>
          </div>

          {/* Status Summary */}
          {status && status.status !== 'idle' && (
            <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-400 mb-2">Run Status</h3>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">ID:</span>
                  <span className="font-mono text-gray-300">{status.run_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Status:</span>
                  <span className={`font-semibold ${statusColor[status.status] || 'text-gray-400'}`}>
                    {status.status.toUpperCase()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Progress:</span>
                  <span className="text-gray-300">{Math.round((status.progress || 0) * 100)}%</span>
                </div>
                {status.stats && Object.keys(status.stats).length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-800">
                    {Object.entries(status.stats).map(([k, v]) => (
                      <div key={k} className="flex justify-between text-[10px]">
                        <span className="text-gray-600">{k}:</span>
                        <span className="text-gray-400">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: Pipeline Steps + Logs */}
        <div className="flex-1 flex flex-col gap-4 overflow-hidden">
          {/* Step Progress */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-1">
              {STEPS.map((step, i) => {
                let state = 'pending'
                if (isRunning) {
                  if (i < currentStepIdx) state = 'done'
                  else if (i === currentStepIdx) state = 'active'
                } else if (status?.status === 'completed') {
                  state = 'done'
                } else if (status?.status === 'failed' && i <= currentStepIdx) {
                  state = i === currentStepIdx ? 'failed' : 'done'
                }

                const stateStyles = {
                  pending: 'bg-gray-800 border-gray-700 text-gray-600',
                  active:  'bg-blue-900/40 border-blue-700 text-blue-300 animate-pulse',
                  done:    'bg-green-900/30 border-green-800 text-green-400',
                  failed:  'bg-red-900/30 border-red-800 text-red-400',
                }

                return (
                  <div key={step.key} className="flex items-center flex-1">
                    <div className={`flex-1 flex flex-col items-center p-2 rounded-lg border text-center ${stateStyles[state]}`}>
                      <div className="text-[10px] font-bold">{step.label}</div>
                      <div className="text-[8px] opacity-60">{step.desc}</div>
                    </div>
                    {i < STEPS.length - 1 && (
                      <div className={`w-4 h-0.5 ${state === 'done' ? 'bg-green-800' : 'bg-gray-800'}`} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Logs */}
          <div className="flex-1 bg-black rounded-xl border border-gray-800 flex flex-col overflow-hidden">
            <div className="px-4 py-2 border-b border-gray-800 bg-gray-900/50 flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-400">Pipeline Logs</span>
              <span className="text-[10px] text-gray-600">{status?.logs?.length || 0} entries</span>
            </div>
            <div ref={logRef} className="flex-1 overflow-y-auto p-4 font-mono text-[11px] space-y-0.5">
              {(status?.logs || []).length === 0 ? (
                <div className="text-gray-700 text-center mt-8">No logs yet. Run the pipeline to see output.</div>
              ) : (
                status.logs.map((log, i) => (
                  <div key={i} className={`break-words ${
                    log.includes('ERROR') || log.includes('실패') ? 'text-red-400'
                    : log.includes('완료') || log.includes('SKIP') ? 'text-green-400/80'
                    : log.includes('──') ? 'text-blue-400/80 font-bold'
                    : 'text-gray-400'
                  }`}>
                    {log}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
