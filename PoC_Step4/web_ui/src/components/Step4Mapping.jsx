
import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Download, Table, Layers, FileType } from 'lucide-react'

export default function Step4Mapping() {
    const [apiKey, setApiKey] = useState("")
    const [configured, setConfigured] = useState(false)

    // Inputs
    const [targetDocx, setTargetDocx] = useState(null)
    const [targetCsv, setTargetCsv] = useState(null)
    const [mappingFiles, setMappingFiles] = useState([])
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
        if (!targetDocx || !targetCsv || mappingFiles.length === 0 || refFiles.length < 2) {
            setError("Please upload: Target DOCX, Target CSV, Mapping Files, and at least 1 Pair of Ref Files.")
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
        formData.append('target_docx', targetDocx)
        formData.append('target_csv', targetCsv)

        for (let i = 0; i < mappingFiles.length; i++) {
            formData.append('mapping_files', mappingFiles[i])
        }

        for (let i = 0; i < refFiles.length; i++) {
            formData.append('ref_files', refFiles[i])
        }

        try {
            const res = await axios.post('/api/analyze_step4', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 3600000 // 60 mins
            })

            // Result preview is expected to be array of objects
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

    const Cell = ({ val }) => (
        <td className="p-3 border-b border-gray-800 text-gray-300 font-mono text-xs whitespace-nowrap">
            {val ? val : <span className="text-gray-700">-</span>}
        </td>
    )

    return (
        <div className="h-full flex flex-col p-6 max-w-[1920px] mx-auto bg-gray-950 text-white font-sans">
            {/* Header */}
            <header className="flex items-center justify-between mb-6 pb-4 border-b border-gray-800">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-teal-400 text-transparent bg-clip-text flex items-center gap-3">
                        <Layers className="text-emerald-400" size={32} />
                        PoC Step 4: Risk Inference
                    </h1>
                    <p className="text-gray-400 text-sm mt-1">
                        Infer Coverage Criteria (Item Category/Value) based on Risk Names (Table of Contents) using 2-Phase Logic
                    </p>
                </div>

                {/* API Key Config */}
                <div className={`flex items-center gap-2 p-2 rounded-lg border transition-all ${configured ? 'border-green-800/50 bg-green-900/10' : 'border-gray-700 bg-gray-800'}`}>
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
                        {configured ? "Reset" : "Set Key"}
                    </button>
                </div>
            </header>

            <div className="flex flex-1 gap-6 overflow-hidden">
                {/* Left: Inputs */}
                <div className="w-80 flex flex-col gap-3 overflow-y-auto pr-2 shrink-0">

                    {/* 1. Target Policy DOCX */}
                    <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
                            <span className="w-5 h-5 rounded-full bg-emerald-900/50 text-emerald-300 flex items-center justify-center text-xs">1</span>
                            Target Policy (Word)
                        </label>
                        <input
                            type="file" accept=".docx,.doc"
                            onChange={(e) => setTargetDocx(e.target.files[0])}
                            className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-emerald-600/20 file:text-emerald-300 hover:file:bg-emerald-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 2. Target Code CSV */}
                    <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
                            <span className="w-5 h-5 rounded-full bg-emerald-900/50 text-emerald-300 flex items-center justify-center text-xs">2</span>
                            Target Coverage Code (CSV)
                        </label>
                        <p className="text-[10px] text-gray-500 mb-2">Contains List of Risk Names to process.</p>
                        <input
                            type="file" accept=".csv,.xlsx"
                            onChange={(e) => setTargetCsv(e.target.files[0])}
                            className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-emerald-600/20 file:text-emerald-300 hover:file:bg-emerald-600/30 cursor-pointer"
                        />
                    </div>

                    {/* 3. Mapping Files */}
                    <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
                            <span className="w-5 h-5 rounded-full bg-purple-900/50 text-purple-300 flex items-center justify-center text-xs">3</span>
                            Code Mapping Definitions
                        </label>
                        <input
                            type="file" multiple accept=".csv,.xlsx"
                            onChange={(e) => setMappingFiles(e.target.files)}
                            className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-purple-600/20 file:text-purple-300 hover:file:bg-purple-600/30 cursor-pointer"
                        />
                        {mappingFiles.length > 0 && (
                            <div className="mt-2 text-[10px] text-purple-400">
                                {mappingFiles.length} files selected
                            </div>
                        )}
                    </div>

                    {/* 4. Reference Pairs */}
                    <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-2">
                            <span className="w-5 h-5 rounded-full bg-amber-900/50 text-amber-300 flex items-center justify-center text-xs">4</span>
                            Reference Pairs (Word + CSV)
                        </label>
                        <p className="text-[10px] text-gray-500 mb-2">Upload matching .docx and .csv pairs for Logic Extraction.</p>
                        <input
                            type="file" multiple accept=".docx,.doc,.csv,.xlsx"
                            onChange={(e) => setRefFiles(e.target.files)}
                            className="text-xs text-gray-400 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-amber-600/20 file:text-amber-300 hover:file:bg-amber-600/30 cursor-pointer"
                        />
                        {refFiles.length > 0 && (
                            <div className="mt-2 text-[10px] text-amber-400">
                                {refFiles.length} files selected
                            </div>
                        )}
                    </div>

                    {/* Action */}
                    <button
                        onClick={handleAnalyze}
                        disabled={loading || !configured}
                        className="w-full py-3 mt-2 rounded-lg font-bold text-sm shadow-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50
                        bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white"
                    >
                        {loading ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle size={16} />}
                        Start Phase 1 & 2
                    </button>

                    {/* Logs */}
                    {loading && (
                        <div className="mt-4 bg-black rounded-lg p-3 border border-gray-800 font-mono text-[10px] h-48 overflow-y-auto w-full shadow-inner" ref={logContainerRef}>
                            {logs.map((log, i) => (
                                <div key={i} className="text-emerald-400/80 mb-1 break-words">
                                    {log}
                                </div>
                            ))}
                        </div>
                    )}

                    {error && (
                        <div className="p-3 mt-2 rounded-lg bg-red-900/20 border border-red-800 text-red-200 text-xs flex gap-2">
                            <AlertCircle size={14} className="shrink-0 mt-0.5" />
                            <span className="break-all">{error}</span>
                        </div>
                    )}
                </div>

                {/* Right: Results (Scrollable) */}
                <div className="flex-1 bg-gray-900 rounded-xl border border-gray-800 flex flex-col overflow-hidden shadow-2xl">
                    <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/80 flex justify-between items-center">
                        <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                            <Table size={16} /> Inferred Results (Preview)
                        </div>

                        <div className="flex gap-2">
                            {downloadPath && (
                                <button
                                    onClick={() => handleDownload(downloadPath, "PoC_Step4_Results.zip")}
                                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium flex items-center gap-1.5 transition-colors"
                                >
                                    <Download size={14} /> Download ZIP
                                </button>
                            )}
                            {logicPath && (
                                <button
                                    onClick={() => handleDownload(logicPath, "Logic_Risk_Inference.txt")}
                                    className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded text-xs font-medium flex items-center gap-1.5 transition-colors border border-gray-700"
                                >
                                    <FileText size={14} /> View Logic
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto bg-gray-900 relative">
                        {result ? (
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-gray-800 text-xs uppercase text-gray-400 font-semibold sticky top-0 z-10 shadow-lg">
                                    <tr>
                                        <th className="p-3 border-b border-gray-700 min-w-[200px]">Risk Name</th>
                                        <th className="p-3 border-b border-gray-700 min-w-[100px] text-blue-300">Category Code</th>
                                        <th className="p-3 border-b border-gray-700 min-w-[150px] text-blue-300">Category Name</th>
                                        <th className="p-3 border-b border-gray-700 min-w-[100px] text-amber-300">Value Code</th>
                                        <th className="p-3 border-b border-gray-700 min-w-[150px] text-amber-300">Value Name</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-800 text-sm">
                                    {result.map((row, i) => (
                                        <tr key={i} className="hover:bg-gray-800/50 transition-colors">
                                            <td className="p-3 border-b border-gray-800 font-medium text-white">{row['위험률명']}</td>
                                            <Cell val={row['항목구분코드']} />
                                            <Cell val={row['항목구분명']} />
                                            <Cell val={row['항목값코드']} />
                                            <Cell val={row['항목값명']} />
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-4">
                                <div className="p-6 rounded-full bg-gray-800/50 border border-gray-800">
                                    <FileType size={48} className="opacity-50" />
                                </div>
                                <p className="text-lg font-medium">Ready for Step 4 Inference</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
