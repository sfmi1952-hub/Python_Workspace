import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import {
  Upload, FileText, CheckCircle, AlertCircle, Loader2,
  Download, Table, Key, Layers, Settings2
} from 'lucide-react'
import ConfidenceBadge from './common/ConfidenceBadge.jsx'
import SourceBadge from './common/SourceBadge.jsx'

const PROVIDERS = [
  { id: 'gemini', label: 'Gemini 3.1 Pro' },
  { id: 'openai', label: 'GPT-5.2' },
  { id: 'claude', label: 'Claude Sonnet 4.6' },
]

export default function ExtractionPanel() {
  // API Key config
  const [apiKey, setApiKey] = useState('')
  const [configured, setConfigured] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState('gemini')

  // Ensemble
  const [ensemble, setEnsemble] = useState(false)
  const [secondaryProvider, setSecondaryProvider] = useState('openai')

  // Files
  const [targetPdf, setTargetPdf] = useState(null)
  const [mappingFiles, setMappingFiles] = useState([])
  const [refFiles, setRefFiles] = useState([])

  // State
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [processingTime, setProcessingTime] = useState(0)

  // Existing results
  const [existingResults, setExistingResults] = useState([])

  const handleConfigure = async () => {
    if (!apiKey) return
    try {
      await axios.post('/api/admin/configure-provider', {
        provider: selectedProvider,
        api_key: apiKey,
      })
      setConfigured(true)
      setError(null)
    } catch (err) {
      setError('API Key configuration failed: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handleAnalyze = async () => {
    if (!targetPdf) {
      setError('Target PDF is required')
      return
    }
    if (!configured) {
      setError('Please configure API Key first')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('pdf_file', targetPdf)
    formData.append('provider', selectedProvider)
    formData.append('ensemble', ensemble)
    if (ensemble) formData.append('secondary_provider', secondaryProvider)

    for (const f of mappingFiles) {
      formData.append('mapping_file', f)
    }
    for (const f of refFiles) {
      formData.append('reference_file', f)
    }

    try {
      const res = await axios.post('/api/extraction/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 3600000,
      })
      setResult(res.data)
      setProcessingTime(res.data.processing_time || 0)
    } catch (err) {
      setError(err.response?.data?.detail || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  // Load existing results
  useEffect(() => {
    axios.get('/api/extraction/results?page_size=20')
      .then(res => setExistingResults(res.data.items || []))
      .catch(() => {})
  }, [result])

  const ATTR_COLUMNS = [
    'diagnosis_code', 'exemption_code', 'edi_code',
    'hospital_grade', 'hospital_class', 'accident_type',
    'admission_limit', 'min_admission', 'coverage_period',
  ]

  const ATTR_LABELS = {
    diagnosis_code: 'Diagnosis',
    exemption_code: 'Exemption',
    edi_code: 'EDI',
    hospital_grade: 'Grade',
    hospital_class: 'Class',
    accident_type: 'Accident',
    admission_limit: 'Limit(D)',
    min_admission: 'Min(D)',
    coverage_period: 'Period',
  }

  return (
    <div className="h-full flex flex-col p-6 bg-gray-950">
      <div className="flex flex-1 gap-6 overflow-hidden">
        {/* Left: Controls */}
        <div className="w-80 flex flex-col gap-3 overflow-y-auto pr-2 shrink-0">
          {/* Provider Selection */}
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <label className="text-sm font-semibold text-gray-200 mb-2 block">LLM Provider</label>
            <select
              value={selectedProvider}
              onChange={(e) => { setSelectedProvider(e.target.value); setConfigured(false) }}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white"
            >
              {PROVIDERS.map(p => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
          </div>

          {/* API Key */}
          <div className={`bg-gray-900/50 border rounded-lg p-4 ${configured ? 'border-green-800/50' : 'border-gray-700'}`}>
            <label className="text-sm font-semibold text-gray-200 mb-2 flex items-center gap-2">
              <Key size={14} /> API Key
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={`${selectedProvider} API Key`}
                disabled={configured}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-600"
              />
              <button
                onClick={() => configured ? setConfigured(false) : handleConfigure()}
                className={`text-xs px-3 py-1.5 rounded font-medium transition-colors ${
                  configured
                    ? 'bg-green-900 text-green-200 hover:bg-green-800'
                    : 'bg-blue-600 text-white hover:bg-blue-500'
                }`}
              >
                {configured ? 'Reset' : 'Set'}
              </button>
            </div>
          </div>

          {/* Ensemble Toggle */}
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
              <Settings2 size={14} /> Ensemble Mode
            </label>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setEnsemble(!ensemble)}
                className={`relative w-10 h-5 rounded-full transition-colors ${ensemble ? 'bg-blue-600' : 'bg-gray-700'}`}
              >
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${ensemble ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
              <span className="text-xs text-gray-400">{ensemble ? 'ON' : 'OFF'}</span>
            </div>
            {ensemble && (
              <select
                value={secondaryProvider}
                onChange={(e) => setSecondaryProvider(e.target.value)}
                className="mt-2 w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-xs text-white"
              >
                {PROVIDERS.filter(p => p.id !== selectedProvider).map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            )}
          </div>

          {/* PDF Upload */}
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
              <span className="w-5 h-5 rounded-full bg-blue-900/50 text-blue-300 flex items-center justify-center text-xs">1</span>
              Target Policy PDF
            </label>
            <input
              type="file" accept=".pdf"
              onChange={(e) => setTargetPdf(e.target.files[0])}
              className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-blue-600/20 file:text-blue-300 hover:file:bg-blue-600/30 cursor-pointer"
            />
          </div>

          {/* Mapping Tables */}
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
              <span className="w-5 h-5 rounded-full bg-purple-900/50 text-purple-300 flex items-center justify-center text-xs">2</span>
              Mapping Tables
            </label>
            <input
              type="file" multiple accept=".xlsx,.csv"
              onChange={(e) => setMappingFiles(Array.from(e.target.files))}
              className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-purple-600/20 file:text-purple-300 hover:file:bg-purple-600/30 cursor-pointer"
            />
            {mappingFiles.length > 0 && (
              <div className="mt-1 text-[10px] text-purple-400">{mappingFiles.length} files</div>
            )}
          </div>

          {/* Reference Files */}
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
            <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
              <span className="w-5 h-5 rounded-full bg-amber-900/50 text-amber-300 flex items-center justify-center text-xs">3</span>
              RAG References (Opt.)
            </label>
            <input
              type="file" multiple
              onChange={(e) => setRefFiles(Array.from(e.target.files))}
              className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-amber-600/20 file:text-amber-300 hover:file:bg-amber-600/30 cursor-pointer"
            />
          </div>

          {/* Run Button */}
          <button
            onClick={handleAnalyze}
            disabled={loading || !configured}
            className="w-full py-3 mt-2 rounded-lg font-bold text-sm shadow-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white"
          >
            {loading ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle size={16} />}
            {loading ? 'Extracting...' : 'Start Extraction'}
          </button>

          {/* Error */}
          {error && (
            <div className="p-3 rounded-lg bg-red-900/20 border border-red-800 text-red-200 text-xs flex gap-2">
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              <span className="break-all">{error}</span>
            </div>
          )}
        </div>

        {/* Right: Results */}
        <div className="flex-1 bg-gray-900 rounded-xl border border-gray-800 flex flex-col overflow-hidden shadow-2xl">
          <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/80 flex justify-between items-center">
            <div className="flex items-center gap-2 text-sm font-semibold text-blue-400">
              <Table size={16} /> Results
              {result && (
                <span className="text-[10px] text-gray-500 font-normal ml-2">
                  {result.results?.length ?? 0} attributes | {processingTime}s |
                  Overall: <ConfidenceBadge value={result.overall_confidence} />
                </span>
              )}
            </div>
            {result?.ensemble_used && (
              <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-900/40 text-amber-300">
                Ensemble Verified
              </span>
            )}
          </div>

          <div className="flex-1 overflow-auto bg-gray-900">
            {result?.results?.length > 0 ? (
              <table className="w-full text-left border-collapse">
                <thead className="bg-gray-800 text-xs uppercase text-gray-400 font-semibold sticky top-0 z-10 shadow-lg">
                  <tr>
                    <th className="p-3 border-b border-gray-700">Attribute</th>
                    <th className="p-3 border-b border-gray-700">Value</th>
                    <th className="p-3 border-b border-gray-700">Confidence</th>
                    <th className="p-3 border-b border-gray-700">Source</th>
                    <th className="p-3 border-b border-gray-700 max-w-[400px]">Reasoning</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 text-sm">
                  {result.results.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-800/50 transition-colors">
                      <td className="p-3 border-b border-gray-800 font-medium text-gray-200">
                        {r.attribute_label || r.attribute_name}
                      </td>
                      <td className="p-3 border-b border-gray-800 font-mono text-xs text-blue-300">
                        {r.extracted_value || <span className="text-gray-700">-</span>}
                      </td>
                      <td className="p-3 border-b border-gray-800">
                        <ConfidenceBadge value={r.confidence} />
                      </td>
                      <td className="p-3 border-b border-gray-800">
                        <SourceBadge value={r.source} />
                      </td>
                      <td className="p-3 border-b border-gray-800 text-gray-500 text-[10px] max-w-[400px] truncate" title={r.reasoning}>
                        {r.reasoning || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : existingResults.length > 0 ? (
              <div>
                <div className="px-4 py-2 text-xs text-gray-500 border-b border-gray-800">Recent Results</div>
                <table className="w-full text-left border-collapse">
                  <thead className="bg-gray-800 text-xs uppercase text-gray-400 font-semibold sticky top-0 z-10">
                    <tr>
                      <th className="p-3 border-b border-gray-700">Product</th>
                      <th className="p-3 border-b border-gray-700">Benefit</th>
                      <th className="p-3 border-b border-gray-700">Attribute</th>
                      <th className="p-3 border-b border-gray-700">Value</th>
                      <th className="p-3 border-b border-gray-700">Confidence</th>
                      <th className="p-3 border-b border-gray-700">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800 text-sm">
                    {existingResults.map(r => (
                      <tr key={r.id} className="hover:bg-gray-800/50">
                        <td className="p-3 text-gray-300 text-xs">{r.product_code}</td>
                        <td className="p-3 text-gray-300 text-xs">{r.benefit_name}</td>
                        <td className="p-3 text-gray-400 text-xs">{r.attribute_name}</td>
                        <td className="p-3 font-mono text-xs text-blue-300">{r.extracted_value}</td>
                        <td className="p-3"><ConfidenceBadge value={r.confidence} /></td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] ${
                            r.verification_status === 'confirmed' ? 'bg-green-900/40 text-green-300'
                            : r.verification_status === 'pending_review' ? 'bg-amber-900/40 text-amber-300'
                            : 'bg-gray-800 text-gray-400'
                          }`}>
                            {r.verification_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-4">
                <div className="p-6 rounded-full bg-gray-800/50 border border-gray-800">
                  <Layers size={48} className="opacity-50" />
                </div>
                <p className="text-lg font-medium">Ready for Extraction</p>
                <p className="text-xs text-gray-700">Upload a PDF and configure API Key to start</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
