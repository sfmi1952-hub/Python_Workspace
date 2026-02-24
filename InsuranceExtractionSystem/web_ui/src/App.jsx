import { useState } from 'react'
import { Layers, FileSearch, ClipboardCheck, Activity, Settings } from 'lucide-react'
import Dashboard from './components/Dashboard.jsx'
import ExtractionPanel from './components/ExtractionPanel.jsx'
import ReviewPanel from './components/ReviewPanel.jsx'
import PipelineStatus from './components/PipelineStatus.jsx'

const TABS = [
  { id: 'dashboard',  label: '대시보드',   icon: Layers },
  { id: 'extraction', label: '추출 분석',  icon: FileSearch },
  { id: 'review',     label: 'HITL 리뷰', icon: ClipboardCheck },
  { id: 'pipeline',   label: '파이프라인', icon: Activity },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white">
      {/* Top Nav */}
      <nav className="flex items-center justify-between px-6 py-3 border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
            <Layers size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold bg-gradient-to-r from-blue-400 to-indigo-400 text-transparent bg-clip-text leading-tight">
              Insurance Extraction System
            </h1>
            <p className="text-[10px] text-gray-500 leading-tight">AI-based Policy Information Extraction</p>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-gray-900 rounded-lg p-1 border border-gray-800">
          {TABS.map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-300 border border-blue-800/50'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-transparent'
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            )
          })}
        </div>

        <div className="text-[10px] text-gray-600">v1.0.0</div>
      </nav>

      {/* Content */}
      <main className="flex-1 overflow-hidden">
        {activeTab === 'dashboard'  && <Dashboard onNavigate={setActiveTab} />}
        {activeTab === 'extraction' && <ExtractionPanel />}
        {activeTab === 'review'     && <ReviewPanel />}
        {activeTab === 'pipeline'   && <PipelineStatus />}
      </main>
    </div>
  )
}
