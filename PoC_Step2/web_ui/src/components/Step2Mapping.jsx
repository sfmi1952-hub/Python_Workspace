
import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Download, Table, Key, Stethoscope } from 'lucide-react'

export default function Step2Mapping() {
    const [apiKey, setApiKey] = useState("")
    const [configured, setConfigured] = useState(false)

    const [targetPdf, setTargetPdf] = useState(null)
    const [targetExcel, setTargetExcel] = useState(null)
    // New Input: Diagnosis Code Mapping
    const [codeMapping, setCodeMapping] = useState(null)
    // New Input: Reference Files (RAG)
    const [refFiles, setRefFiles] = useState([])

    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [result, setResult] = useState(null)
    const [logs, setLogs] = useState([])
    const [downloadPath, setDownloadPath] = useState("")
    const [logicPath, setLogicPath] = useState("")

    // Log Polling
    const logIntervalRef = useRef(null)
    const logContainerRef = useRef(null)

    useEffect(() => {
        if (loading) {
            logIntervalRef.current = setInterval(async () => {
                try {
                    const res = await axios.get('/api/logs')
                    setLogs(res.data.logs)
                } catch (e) { }
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
            console.error(err)
            const msg = err.response?.data?.detail || err.message
            setError("Configuration Failed: " + msg)
        }
    }

    const handleAnalyze = async () => {
        if (!targetPdf || !targetExcel || !codeMapping) {
            setError("Please upload all 3 required files: Target PDF, Target Excel, and Code Mapping Table.")
            return
        }
        if (!configured) {
            setError("Please configure API Key first.")
            return
        }

        setLoading(true)
        setError(null)
        setResult(null)
        setLogs([])
        setDownloadPath("")
        setLogicPath("")

        const formData = new FormData()
        formData.append('target_pdf', targetPdf)
        formData.append('target_excel', targetExcel)
        formData.append('code_mapping', codeMapping)
        // Append all Ref Files
        for (let i = 0; i < refFiles.length; i++) {
            formData.append('ref_files', refFiles[i])
        }

        try {
            const res = await axios.post('/api/analyze_step2', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 1800000 // 30 mins
            })

            setResult(res.data.preview)
            setDownloadPath(res.data.file_path)
            setLogicPath(res.data.logic_path)

        } catch (err) {
            console.error(err)
            setError(err.response?.data?.detail || "Analysis failed. Check backend logs.")
        } finally {
            setLoading(false)
        }
    }

    const handleDownload = async (path, filename) => {
        if (!path) return
        try {
            const response = await axios.get(`/api/download?path=${encodeURIComponent(path)}`, {
                responseType: 'blob',
            })
            const url = window.URL.createObjectURL(new Blob([response.data]))
            const link = document.createElement('a')
            link.href = url
            link.setAttribute('download', filename)
            document.body.appendChild(link)
            link.click()
            link.remove()
        } catch (err) {
            console.error(err)
            alert("Download failed")
        }
    }

    return (
        <div className="h-full flex flex-col p-6 max-w-[1600px] mx-auto bg-gray-950 text-white font-sans">
            {/* Header */}
            <header className="flex items-center justify-between mb-8 pb-4 border-b border-gray-800">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 text-transparent bg-clip-text flex items-center gap-3">
                        <Stethoscope className="text-emerald-400" size={32} />
                        PoC Step 2: Diagnosis Code Inference
                    </h1>
                    <p className="text-gray-400 text-sm mt-1">Template List (from Step 1) + Policy PDF + Code Mapping Table → Inferred Diagnosis Code</p>
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
                            : "bg-emerald-600 text-white hover:bg-emerald-500"
                            }`}
                    >
                        {configured ? "Reset" : "Set"}
                    </button>
                </div>
            </header>

            <div className="flex flex-1 gap-8 overflow-hidden">
                {/* Left: Inputs */}
                <div className="w-96 flex flex-col gap-4 overflow-y-auto pr-2">

                    {/* 1. PDF */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-emerald-500/50 rounded-xl p-5 transition-all">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-emerald-900/50 text-emerald-300 flex items-center justify-center text-xs">1</span>
                            Target Policy PDF
                        </label>
                        <input
                            type="file" accept=".pdf"
                            onChange={(e) => setTargetPdf(e.target.files[0])}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-emerald-600/20 file:text-emerald-300 hover:file:bg-emerald-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 2. Target Excel (Benefit List) */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-blue-500/50 rounded-xl p-5 transition-all">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-blue-900/50 text-blue-300 flex items-center justify-center text-xs">2</span>
                            Benefit List (Result of Step 1)
                        </label>
                        <p className="text-xs text-gray-500 mb-3 ml-8">Required: "세부담보템플릿명" Column</p>
                        <input
                            type="file" accept=".xlsx"
                            onChange={(e) => setTargetExcel(e.target.files[0])}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-blue-600/20 file:text-blue-300 hover:file:bg-blue-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 3. Code Mapping Excel */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/50 rounded-xl p-5 transition-all">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-purple-900/50 text-purple-300 flex items-center justify-center text-xs">3</span>
                            Discovery Code Table (Excel)
                        </label>
                        <p className="text-xs text-gray-500 mb-3 ml-8">Cols: "진단분류", "분류번호"</p>
                        <input
                            type="file" accept=".xlsx"
                            onChange={(e) => setCodeMapping(e.target.files[0])}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-purple-600/20 file:text-purple-300 hover:file:bg-purple-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 4. Reference Files (RAG) */}
                    <div className="group bg-gray-900/50 border border-gray-700 hover:border-amber-500/50 rounded-xl p-5 transition-all">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-3">
                            <span className="w-6 h-6 rounded-full bg-amber-900/50 text-amber-300 flex items-center justify-center text-xs">4</span>
                            Reference Files for RAG (Optional)
                        </label>
                        <p className="text-xs text-gray-500 mb-3 ml-8">Upload PDF/Excel pairs for rules.</p>
                        <input
                            type="file" multiple
                            onChange={(e) => setRefFiles(e.target.files)}
                            className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-amber-600/20 file:text-amber-300 hover:file:bg-amber-600/30 cursor-pointer"
                        />
                        {refFiles.length > 0 && (
                            <div className="mt-2 ml-8 text-xs text-amber-400">
                                {refFiles.length} files selected
                            </div>
                        )}
                    </div>

                    {/* Action */}
                    <button
                        onClick={handleAnalyze}
                        disabled={loading || !configured}
                        className="w-full py-4 mt-auto rounded-xl font-bold text-lg shadow-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed
                        bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white"
                    >
                        {loading ? <Loader2 className="animate-spin" /> : <CheckCircle />}
                        Infer Diagnosis Codes
                    </button>

                    {/* Logs */}
                    {loading && (
                        <div className="mt-4 bg-black rounded-lg p-3 border border-gray-800 font-mono text-xs h-32 overflow-y-auto w-full shadow-inner" ref={logContainerRef}>
                            {logs.map((log, i) => (
                                <div key={i} className="text-emerald-400/80 mb-1 break-words">
                                    {log}
                                </div>
                            ))}
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
                        <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                            <Table size={18} /> Diagnosis Coding Results
                        </div>

                        <div className="flex gap-2">
                            {downloadPath && (
                                <button
                                    onClick={() => handleDownload(downloadPath, "diagnosis_coded_results.xlsx")}
                                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-lg shadow-emerald-900/20"
                                >
                                    <Download size={16} /> Result Excel
                                </button>
                            )}
                            {logicPath && (
                                <button
                                    onClick={() => handleDownload(logicPath, "mapping_logic.txt")}
                                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors border border-gray-700"
                                >
                                    <FileText size={16} /> Mapping Logic
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto bg-gray-900">
                        {result ? (
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-gray-800 text-xs uppercase text-gray-400 font-semibold sticky top-0 z-10">
                                    <tr>
                                        <th className="p-4 border-b border-gray-700 w-1/4">Template Name</th>
                                        <th className="p-4 border-b border-gray-700 w-1/4 text-emerald-300">Inferred Code</th>
                                        <th className="p-4 border-b border-gray-700 text-gray-300">Reasoning</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-800 text-sm">
                                    {result.map((row, i) => (
                                        <tr key={i} className="hover:bg-gray-800/50 transition-colors group">
                                            <td className="p-4 font-medium text-white">{row['세부담보템플릿명']}</td>
                                            <td className="p-4">
                                                {row['Inferred_Diagnosis_Code'] ? (
                                                    <span className="px-2 py-1 rounded bg-emerald-900/30 text-emerald-400 font-mono font-bold border border-emerald-900/50">
                                                        {row['Inferred_Diagnosis_Code']}
                                                    </span>
                                                ) : <span className="text-gray-600">-</span>}
                                            </td>
                                            <td className="p-4 text-gray-400 italic leading-relaxed group-hover:text-gray-300 text-xs">
                                                {row['Code_Mapping_Reason']}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-4">
                                <div className="p-6 rounded-full bg-gray-800/50 border border-gray-800">
                                    <FileText size={48} className="opacity-50" />
                                </div>
                                <p className="text-lg font-medium">Ready for Step 2 Analysis</p>
                                <p className="text-sm max-w-md text-center">Upload files to infer diagnosis codes.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
