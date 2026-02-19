import { useState } from 'react'
import FileUpload from './components/FileUpload'
import ResultPanel from './components/ResultPanel'
import ChatBot from './components/ChatBot'
import { MessageSquare } from 'lucide-react'

function App() {
  const [extractedData, setExtractedData] = useState(null)
  const [showChat, setShowChat] = useState(false)
  const [chatContext, setChatContext] = useState("")

  const handleAnalysisComplete = (data) => {
    setExtractedData(data)
    // Pass extracted text to chat context (simplified for now)
    setChatContext(JSON.stringify(data, null, 2))
  }

  return (
    <div className="h-screen flex flex-col bg-gray-900 text-white overflow-hidden">
      {/* Header */}
      <header className="flex-none h-16 border-b border-gray-700 flex items-center justify-between px-6 bg-gray-800">
        <div className="flex items-center gap-2">
          <span className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 text-transparent bg-clip-text">
            Samsung Fire & Marine Info Extractor
          </span>
          <span className="text-xs px-2 py-0.5 rounded bg-blue-900 text-blue-200">AI Powered</span>
        </div>
        <div>
          <button
            onClick={() => setShowChat(!showChat)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${showChat ? 'bg-blue-600 text-white' : 'bg-gray-700 hover:bg-gray-600'
              }`}
          >
            <MessageSquare size={18} />
            {showChat ? 'Hide Chat' : 'AI Assistant'}
          </button>
        </div>
      </header>

      {/* Main Content (Split View) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: File Upload & Controls */}
        <div className="w-1/3 min-w-[350px] border-r border-gray-700 p-6 flex flex-col bg-gray-800/50">
          <FileUpload onAnalyzeComplete={handleAnalysisComplete} />
        </div>

        {/* Right Panel: Results */}
        <div className="flex-1 bg-gray-900 p-6 overflow-auto">
          {extractedData ? (
            <ResultPanel data={extractedData} />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-gray-500">
              <div className="text-6xl mb-4">📄</div>
              <p className="text-xl">Upload a policy PDF to begin analysis</p>
            </div>
          )}
        </div>
      </div>

      {/* Floating Chat */}
      {showChat && (
        <div className="fixed bottom-6 right-6 w-96 h-[600px] z-50">
          <ChatBot context={chatContext} onClose={() => setShowChat(false)} />
        </div>
      )}
    </div>
  )
}

export default App
