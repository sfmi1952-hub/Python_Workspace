import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Download, Table, Key } from 'lucide-react'

export default function Step1Mapping() {
    const [apiKey, setApiKey] = useState("")
    const [configured, setConfigured] = useState(false)

    const [targetPdf, setTargetPdf] = useState(null)
    const [targetExcel, setTargetExcel] = useState(null)
    const [referenceFiles, setReferenceFiles] = useState([])

    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [result, setResult] = useState(null)
    const [logs, setLogs] = useState([])
    const [downloadPath, setDownloadPath] = useState("")

    // New State for Rules
    const [rulesText, setRulesText] = useState("")
    const [rulesPath, setRulesPath] = useState("")
    const [activeTab, setActiveTab] = useState("table") // 'table' or 'rules'

    // Log Polling
    const logIntervalRef = useRef(null)
    const logContainerRef = useRef(null)

    useEffect(() => {
        if (loading) {
            logIntervalRef.current = setInterval(async () => {
                try {
                    const res = await axios.get('/api/logs')
                    setLogs(res.data.logs)
                } catch (e) {
                    // Silent failure on log poll is fine
                }
            }, 1000)
        } else {
            if (logIntervalRef.current) clearInterval(logIntervalRef.current)
        }
        return () => { if (logIntervalRef.current) clearInterval(logIntervalRef.current) }
    }, [loading])

    // Auto-scroll logs
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
        }
    }, [logs])

    const handleConfigure = async () => {
        if (!apiKey) return
        try {
            await axios.post('/api/configure', `api_key=${apiKey}`, {
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
            })
            setConfigured(true)
            setError(null)
        } catch (err) {
            setError("Configuration Failed: " + err.message)
        }
    }

    const handleAnalyze = async () => {
        if (!targetPdf || !targetExcel) {
            setError("Please upload both Target PDF and Target Excel.")
            return
        }
        if (!configured) {
            setError("Please configure API Key first.")
            return
        }

        setLoading(true)
        setError(null)
        setResult(null)
        setRulesText("")
        setRulesPath("")
        setLogs([])

        const formData = new FormData()
        formData.append('target_pdf', targetPdf)
        formData.append('target_excel', targetExcel)

        for (let i = 0; i < referenceFiles.length; i++) {
            formData.append('ref_files', referenceFiles[i])
        }

        try {
            const res = await axios.post('/api/analyze', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 1800000
            })

            setResult(res.data.preview)
            setDownloadPath(res.data.file_path)
            setRulesText(res.data.rules_text || "")
            setRulesPath(res.data.rules_file_path || "")

            // Auto-switch to rules tab if valid rules exist to show user what happened
            if (res.data.rules_text) {
                // Optional: setActiveTab('rules') 
            }
        } catch (err) {
            console.error(err)
            setError(err.response?.data?.detail || "Analysis failed. Check backend logs.")
        } finally {
            setLoading(false)
        }
    }

    const handleDownload = async () => {
        if (!downloadPath) return
        try {
            const response = await axios.get(`/api/download?path=${encodeURIComponent(downloadPath)}`, {
                responseType: 'blob',
            })
            const url = window.URL.createObjectURL(new Blob([response.data]))
            const link = document.createElement('a')
            link.href = url
            link.setAttribute('download', 'mapped_results.xlsx')
            document.body.appendChild(link)
            link.click()
            link.remove()
        } catch (err) {
            console.error(err)
            alert("Download failed")
        }
    }

    const handleDownloadRules = async () => {
        if (!rulesPath) return
        try {
            const response = await axios.get(`/api/download?path=${encodeURIComponent(rulesPath)}`, {
                responseType: 'blob',
            })
            const url = window.URL.createObjectURL(new Blob([response.data]))
            const link = document.createElement('a')
            link.href = url
            link.setAttribute('download', 'mapping_rules.txt')
            document.body.appendChild(link)
            link.click()
            link.remove()
        } catch (err) {
            console.error(err)
            alert("Download failed")
        }
    }

    return (
        <div className="h-full flex flex-col p-6 max-w-[1600px] mx-auto">
            {/* Header */}
            <header className="flex items-center justify-between mb-8 pb-4 border-b border-gray-800">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 text-transparent bg-clip-text">
                        PoC Step 1: Benefit Mapping
                    </h1>
                    <p className="text-gray-400 text-sm mt-1">Excel Benefit List + Policy PDF → Inferred Mapping & Evidence</p>
                </div>

                {/* API Key Config */}
                <div className={`flex items-center gap-2 p-2 rounded-lg border transition-all ${configured ? 'border-green-800/50 bg-green-900/10' : 'border-gray-700 bg-gray-800'}`}>
                    <Key size={16} className={configured ? "text-green-400" : "text-gray-400"} />
                    <input
                        type="password"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="Gemini API Key"
                        disabled={configured}
                        className="bg-transparent border-none focus:outline-none text-sm w-40 text-white placeholder-gray-500"
                    />
                    <button
                        onClick={() => configured ? setConfigured(false) : handleConfigure()}
                        className={`text-xs px-3 py-1.5 rounded font-medium transition-colors ${configured
                            ? "bg-green-900 text-green-200 hover:bg-green-800"
                            : "bg-blue-600 text-white hover:bg-blue-500"
                            }`}
                    >
                        {configured ? "Reset" : "Set"}
                    </button>
                </div>
            </header>

            <div className="flex flex-1 gap-8 overflow-hidden">
                {/* Left: Inputs */}
                <div className="w-96 flex flex-col gap-5 overflow-y-auto pr-2">

                    {/* 1. PDF */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-blue-500/50 rounded-xl p-5 transition-all">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-blue-900/50 text-blue-300 flex items-center justify-center text-xs">1</span>
                            Target Policy PDF
                        </label>
                        <input
                            type="file" accept=".pdf"
                            onChange={(e) => setTargetPdf(e.target.files[0])}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-blue-600/20 file:text-blue-300 hover:file:bg-blue-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 2. Excel */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-green-500/50 rounded-xl p-5 transition-all">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-green-900/50 text-green-300 flex items-center justify-center text-xs">2</span>
                            Benefit List (Excel)
                        </label>
                        <p className="text-xs text-gray-500 mb-3 ml-8">Column: "담보명_출력물명칭"</p>
                        <input
                            type="file" accept=".xlsx"
                            onChange={(e) => setTargetExcel(e.target.files[0])}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-green-600/20 file:text-green-300 hover:file:bg-green-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 3. Refs */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/50 rounded-xl p-5 transition-all flex-1">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-purple-900/50 text-purple-300 flex items-center justify-center text-xs">3</span>
                            References (Optional)
                        </label>
                        <p className="text-xs text-gray-500 mb-3 ml-8">Upload past rules/PDFs for context.</p>
                        <input
                            type="file" multiple
                            onChange={(e) => setReferenceFiles(Array.from(e.target.files))}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-purple-600/20 file:text-purple-300 hover:file:bg-purple-600/30 cursor-pointer"
                        />
                        {referenceFiles.length > 0 && (
                            <div className="mt-2 ml-1 text-xs text-purple-400 font-medium">
                                {referenceFiles.length} files attached.
                            </div>
                        )}
                    </div>

                    {/* Action */}
                    <button
                        onClick={handleAnalyze}
                        disabled={loading || !configured}
                        className="w-full py-4 mt-auto rounded-xl font-bold text-lg shadow-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed
                        bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white"
                    >
                        {loading ? <Loader2 className="animate-spin" /> : <CheckCircle />}
                        Start Analysis
                    </button>

                    {/* Log Viewer (Overlay or Embedded) */}
                    {loading && (
                        <div className="mt-4 bg-black rounded-lg p-3 border border-gray-800 font-mono text-xs h-32 overflow-y-auto w-full shadow-inner" ref={logContainerRef}>
                            {logs.map((log, i) => (
                                <div key={i} className="text-green-400/80 mb-1 break-words">
                                    {log}
                                </div>
                            ))}
                            {logs.length === 0 && <span className="text-gray-600 italic">Initializing logs...</span>}
                        </div>
                    )}


                    {error && (
                        <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-200 text-sm flex gap-2">
                            <AlertCircle size={18} className="shrink-0 mt-0.5" />
                            <span className="break-all">{error}</span>
                        </div>
                    )}
                </div>

                {/* Right: Results */}
                <div className="flex-1 bg-gray-900 rounded-2xl border border-gray-800 flex flex-col overflow-hidden shadow-2xl">
                    <div className="px-6 py-4 border-b border-gray-800 bg-gray-900/80 flex justify-between items-center">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => setActiveTab('table')}
                                className={`flex items-center gap-2 text-sm font-semibold transition-colors ${activeTab === 'table' ? 'text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}
                            >
                                <Table size={18} /> Results Preview
                            </button>
                            <div className="w-px h-4 bg-gray-700"></div>
                            <button
                                onClick={() => setActiveTab('rules')}
                                disabled={!rulesText}
                                className={`flex items-center gap-2 text-sm font-semibold transition-colors ${activeTab === 'rules' ? 'text-purple-400' : 'text-gray-500 hover:text-gray-300'} ${!rulesText && 'opacity-50 cursor-not-allowed'}`}
                            >
                                <FileText size={18} /> Extracted Rules
                            </button>
                        </div>

                        <div className="flex gap-2">
                            {downloadPath && activeTab === 'table' && (
                                <button
                                    onClick={handleDownload}
                                    className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-lg shadow-green-900/20"
                                >
                                    <Download size={16} /> Excel
                                </button>
                            )}
                            {rulesPath && activeTab === 'rules' && (
                                <button
                                    onClick={handleDownloadRules}
                                    className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-lg shadow-purple-900/20"
                                >
                                    <Download size={16} /> Rules.txt
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto bg-gray-900">
                        {result ? (
                            activeTab === 'table' ? (
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-gray-800 text-xs uppercase text-gray-400 font-semibold sticky top-0 z-10">
                                        <tr>
                                            <th className="p-4 border-b border-gray-700">Original Benefit Name</th>
                                            <th className="p-4 border-b border-gray-700 text-blue-300">Inferred Template</th>
                                            <th className="p-4 border-b border-gray-700 w-24 text-center">Page</th>
                                            <th className="p-4 border-b border-gray-700 text-gray-300">Evidence</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-800 text-sm">
                                        {result.map((row, i) => (
                                            <tr key={i} className="hover:bg-gray-800/50 transition-colors group">
                                                <td className="p-4 font-medium text-white">{row['담보명_출력물명칭']}</td>
                                                <td className="p-4 text-blue-200 group-hover:text-blue-100">{row['Inferred_Template_Name']}</td>
                                                <td className="p-4 text-center">
                                                    {row['Reference_Page'] && row['Reference_Page'] !== "" ? (
                                                        <span className="px-2 py-1 rounded bg-yellow-900/30 text-yellow-400 font-mono text-xs border border-yellow-900/50">
                                                            P.{row['Reference_Page']}
                                                        </span>
                                                    ) : <span className="text-gray-600">-</span>}
                                                </td>
                                                <td className="p-4 text-gray-400 italic leading-relaxed group-hover:text-gray-300">
                                                    {row['Reference_Sentence']}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : (
                                <div className="p-6 font-mono text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
                                    {rulesText}
                                </div>
                            )
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-4">
                                <div className="p-6 rounded-full bg-gray-800/50 border border-gray-800">
                                    <FileText size={48} className="opacity-50" />
                                </div>
                                <p className="text-lg font-medium">No results yet</p>
                                <p className="text-sm max-w-md text-center">Upload the Policy PDF and Benefit Excel list, then click "Start Analysis" to see the mapping table here.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
