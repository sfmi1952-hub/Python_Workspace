import { useState, useEffect } from 'react'
import axios from 'axios'
import {
  ClipboardCheck, CheckCircle, XCircle, ChevronLeft, ChevronRight,
  AlertCircle, Loader2, RefreshCw
} from 'lucide-react'
import ConfidenceBadge from './common/ConfidenceBadge.jsx'

export default function ReviewPanel() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(null) // review_id
  const [editValue, setEditValue] = useState({}) // { reviewId: correctedValue }

  const pageSize = 15

  const fetchReviews = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`/api/review/pending?page=${page}&page_size=${pageSize}`)
      setItems(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e) {
      console.error('Fetch reviews error:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchReviews() }, [page])

  const handleDecision = async (reviewId, action) => {
    setActionLoading(reviewId)
    try {
      await axios.post(`/api/review/${reviewId}/decide`, {
        action,
        corrected_value: action === 'reject' ? (editValue[reviewId] || '') : undefined,
        reviewer: 'admin',
      })
      // Refresh
      fetchReviews()
    } catch (err) {
      alert('Action failed: ' + (err.response?.data?.detail || err.message))
    } finally {
      setActionLoading(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="h-full flex flex-col p-6 bg-gray-950">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ClipboardCheck size={20} className="text-amber-400" />
          <h2 className="text-lg font-bold text-white">HITL Review Queue</h2>
          <span className="ml-2 px-2 py-0.5 rounded-full text-xs bg-amber-900/40 text-amber-300 border border-amber-800/50">
            {total} pending
          </span>
        </div>
        <button
          onClick={fetchReviews}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 transition-colors"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Table */}
      <div className="flex-1 bg-gray-900 rounded-xl border border-gray-800 flex flex-col overflow-hidden">
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <Loader2 className="animate-spin mr-2" size={20} /> Loading...
          </div>
        ) : items.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-600 space-y-3">
            <CheckCircle size={48} className="text-green-600/30" />
            <p className="text-lg font-medium">No Pending Reviews</p>
            <p className="text-xs text-gray-700">All items have been reviewed</p>
          </div>
        ) : (
          <div className="flex-1 overflow-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-gray-800 text-xs uppercase text-gray-400 font-semibold sticky top-0 z-10 shadow-lg">
                <tr>
                  <th className="p-3 border-b border-gray-700 w-12">#</th>
                  <th className="p-3 border-b border-gray-700">Product</th>
                  <th className="p-3 border-b border-gray-700">Benefit</th>
                  <th className="p-3 border-b border-gray-700">Attribute</th>
                  <th className="p-3 border-b border-gray-700">Extracted Value</th>
                  <th className="p-3 border-b border-gray-700">Confidence</th>
                  <th className="p-3 border-b border-gray-700 min-w-[180px]">Corrected Value</th>
                  <th className="p-3 border-b border-gray-700 w-40">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 text-sm">
                {items.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="p-3 text-gray-600 text-xs">{item.id}</td>
                    <td className="p-3 text-gray-300 font-mono text-xs">{item.product_code}</td>
                    <td className="p-3 text-gray-300 text-xs">{item.benefit_name}</td>
                    <td className="p-3 text-gray-400 text-xs">{item.attribute_name}</td>
                    <td className="p-3 font-mono text-xs text-blue-300">{item.extracted_value}</td>
                    <td className="p-3">
                      <ConfidenceBadge value={item.confidence} />
                    </td>
                    <td className="p-3">
                      <input
                        type="text"
                        placeholder="Corrected value..."
                        value={editValue[item.id] || ''}
                        onChange={(e) => setEditValue(prev => ({ ...prev, [item.id]: e.target.value }))}
                        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-amber-600"
                      />
                    </td>
                    <td className="p-3">
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => handleDecision(item.id, 'approve')}
                          disabled={actionLoading === item.id}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium bg-green-900/30 text-green-300 border border-green-800/50 hover:bg-green-900/50 transition-colors disabled:opacity-50"
                        >
                          {actionLoading === item.id ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
                          Approve
                        </button>
                        <button
                          onClick={() => handleDecision(item.id, 'reject')}
                          disabled={actionLoading === item.id}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium bg-red-900/30 text-red-300 border border-red-800/50 hover:bg-red-900/50 transition-colors disabled:opacity-50"
                        >
                          {actionLoading === item.id ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {total > pageSize && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800 bg-gray-900/80">
            <span className="text-xs text-gray-500">
              Showing {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} of {total}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 transition-colors"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-xs text-gray-400">{page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 transition-colors"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
