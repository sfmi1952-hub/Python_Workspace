import { useState } from 'react'
import axios from 'axios'
import { Upload, FileText, Loader2, AlertCircle, CheckCircle } from 'lucide-react'

export default function FileUpload({ onAnalyzeComplete }) {
    const [file, setFile] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [apiKey, setApiKey] = useState("")
    const [isConfigured, setIsConfigured] = useState(false)

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0])
            setError(null)
        }
    }

    const handleConfigure = async () => {
        if (!apiKey) return;
        try {
            await axios.post('http://localhost:8000/api/configure', { api_key: apiKey });
            setIsConfigured(true);
        } catch (err) {
            setError("Failed to configure API Key: " + err.message);
        }
    }

    const handleUpload = async () => {
        if (!file) return
        if (!isConfigured) {
            setError("Please configure Gemini API Key first.")
            return
        }

        setLoading(true)
        setError(null)

        const formData = new FormData()
        formData.append('file', file)

        try {
            const response = await axios.post('http://localhost:8000/api/analyze', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            })
            onAnalyzeComplete(response.data)
        } catch (err) {
            console.error(err)
            setError(err.response?.data?.detail || "Failed to analyze file. Is the backend running?")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="flex flex-col h-full gap-6">

            {/* API Key Config Section */}
            {!isConfigured && (
                <div className="p-4 bg-gray-700/50 rounded-lg border border-gray-600">
                    <h3 className="text-sm font-semibold mb-2 text-gray-300">Configuration</h3>
                    <div className="flex gap-2">
                        <input
                            type="password"
                            placeholder="Enter Gemini API Key"
                            className="flex-1 px-3 py-2 bg-gray-900 border border-gray-600 rounded text-sm focus:outline-none focus:border-blue-500"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                        />
                        <button
                            onClick={handleConfigure}
                            className="px-3 py-2 bg-green-600 hover:bg-green-700 rounded text-sm font-medium transition-colors"
                        >
                            Set
                        </button>
                    </div>
                </div>
            )}

            <div className="flex-1 flex flex-col gap-4">
                <h2 className="text-lg font-semibold text-gray-200 flex items-center gap-2">
                    <FileText className="text-blue-400" /> Source Document
                </h2>

                {/* Upload Box */}
                <div className="border-2 border-dashed border-gray-600 rounded-xl p-8 flex flex-col items-center justify-center text-center hover:border-blue-500 hover:bg-gray-800/30 transition-all cursor-pointer relative">
                    <input
                        type="file"
                        accept=".pdf,.xlsx,.xls"
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                        onChange={handleFileChange}
                    />
                    <div className="bg-gray-700 p-4 rounded-full mb-4">
                        <Upload size={32} className="text-blue-400" />
                    </div>
                    <p className="text-gray-300 font-medium">Click or Drag file here</p>
                    <p className="text-gray-500 text-sm mt-2">Supports PDF & Excel</p>
                </div>

                {/* Selected File Status */}
                {file && (
                    <div className="bg-gray-700/50 rounded-lg p-3 flex items-center justify-between animate-in fade-in slide-in-from-top-2">
                        <div className="flex items-center gap-3 overflow-hidden">
                            <FileText className="text-gray-400 flex-shrink-0" size={20} />
                            <span className="text-sm text-gray-200 truncate">{file.name}</span>
                        </div>
                        <span className="text-xs text-gray-500 whitespace-nowrap">
                            {(file.size / 1024 / 1024).toFixed(2)} MB
                        </span>
                    </div>
                )}

                {/* Error Message */}
                {error && (
                    <div className="bg-red-900/20 border border-red-500/50 text-red-200 p-3 rounded-lg text-sm flex items-start gap-2">
                        <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                        <span>{error}</span>
                    </div>
                )}
            </div>

            {/* Action Button */}
            <button
                onClick={handleUpload}
                disabled={!file || loading || !isConfigured}
                className={`w-full py-4 rounded-xl flex items-center justify-center gap-2 font-bold text-lg transition-all shadow-lg
            ${!file || loading || !isConfigured
                        ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-blue-900/20'
                    }`}
            >
                {loading ? (
                    <>
                        <Loader2 className="animate-spin" /> Analyzing...
                    </>
                ) : (
                    <>
                        Run Analysis
                    </>
                )}
            </button>

            {isConfigured && (
                <div className="text-center">
                    <span className="text-xs text-green-500 flex items-center justify-center gap-1">
                        <CheckCircle size={12} /> System Ready
                    </span>
                </div>
            )}
        </div>
    )
}
