import { Check, Copy } from 'lucide-react'

export default function ResultPanel({ data }) {
    if (!data) return null;

    // If data has an error
    if (data.error) {
        return (
            <div className="p-4 bg-red-900/20 border border-red-500 text-red-200 rounded-lg">
                <h3 className="text-lg font-bold mb-2">Analysis Failed</h3>
                <p>{data.error}</p>
            </div>
        )
    }

    // Helper to format key names (camelCase to Title Case)
    const formatKey = (key) => {
        return key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase());
    }

    return (
        <div className="flex flex-col gap-6 animate-in fade-in zoom-in-95 duration-300">

            {/* Summary Card */}
            <div className="bg-gray-800 rounded-xl p-6 shadow-lg border border-gray-700">
                <h2 className="text-2xl font-bold bg-gradient-to-r from-green-400 to-emerald-400 text-transparent bg-clip-text mb-4">
                    Extraction Complete
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-1">
                        <label className="text-xs text-gray-500 uppercase font-semibold tracking-wider">Benefit Name</label>
                        <div className="text-lg font-medium text-white">{data.benefitName || "-"}</div>
                    </div>
                    <div className="space-y-1">
                        <label className="text-xs text-gray-500 uppercase font-semibold tracking-wider">Diagnosis Code</label>
                        <div className="font-mono text-yellow-400 bg-yellow-900/20 px-2 py-1 rounded inline-block">
                            {data.diagnosisCode || "N/A"}
                        </div>
                    </div>
                </div>
            </div>

            {/* Detailed Grid */}
            <div className="bg-gray-800 rounded-xl overflow-hidden border border-gray-700 shadow-lg">
                <div className="px-6 py-4 bg-gray-750 border-b border-gray-700 flex justify-between items-center">
                    <h3 className="font-semibold text-gray-200">Detailed Extracted Fields</h3>
                    <button className="text-xs text-gray-400 hover:text-white flex items-center gap-1">
                        <Copy size={12} /> Copy JSON
                    </button>
                </div>

                <div className="divide-y divide-gray-700">
                    {Object.entries(data).map(([key, value]) => {
                        if (key === 'source_evidence' || key === 'citations') return null; // Handle separately
                        return (
                            <div key={key} className="grid grid-cols-3 p-4 hover:bg-gray-700/30 transition-colors">
                                <div className="col-span-1 text-sm text-gray-400 font-medium">{formatKey(key)}</div>
                                <div className="col-span-2 text-sm text-gray-100 break-words">{value !== "" ? value : <span className="text-gray-600 italic">Empty</span>}</div>
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* Evidence Section */}
            {data.source_evidence && (
                <div className="bg-blue-900/10 border border-blue-500/30 rounded-xl p-4">
                    <h3 className="text-blue-300 font-semibold mb-2 text-sm uppercase tracking-wider">Source Evidence</h3>
                    <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-line">
                        {data.source_evidence}
                    </p>
                </div>
            )}

        </div>
    )
}
