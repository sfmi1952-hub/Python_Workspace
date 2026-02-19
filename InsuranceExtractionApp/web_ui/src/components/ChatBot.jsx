import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { X, Send, Bot, User } from 'lucide-react'

export default function ChatBot({ context, onClose }) {
    const [messages, setMessages] = useState([
        { role: 'assistant', text: '안녕하세요! 약관이나 추출된 데이터에 대해 궁금한 점이 있으신가요?' }
    ])
    const [input, setInput] = useState("")
    const [loading, setLoading] = useState(false)
    const messagesEndRef = useRef(null)

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }

    useEffect(() => {
        scrollToBottom()
    }, [messages])

    const handleSend = async () => {
        if (!input.trim()) return

        const userMsg = input
        setMessages(prev => [...prev, { role: 'user', text: userMsg }])
        setInput("")
        setLoading(true)

        try {
            // Form Data for simple compatibility with backend endpoint
            const formData = new FormData()
            formData.append('prompt', userMsg)
            if (context) {
                formData.append('context', context)
            }

            const response = await axios.post('http://localhost:8000/api/chat', formData)

            setMessages(prev => [...prev, { role: 'assistant', text: response.data.response }])
        } catch (err) {
            setMessages(prev => [...prev, { role: 'assistant', text: "Error: " + (err.response?.data?.detail || err.message) }])
        } finally {
            setLoading(false)
        }
    }

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    return (
        <div className="flex flex-col h-full bg-gray-800 rounded-2xl shadow-2xl border border-gray-600 overflow-hidden font-sans">
            {/* Header */}
            <div className="bg-gray-700 px-4 py-3 flex justify-between items-center border-b border-gray-600">
                <div className="flex items-center gap-2 text-white font-medium">
                    <Bot size={20} className="text-blue-400" /> AI Assistant
                </div>
                <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
                    <X size={20} />
                </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-800/95">
                {messages.map((msg, idx) => (
                    <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm
                    ${msg.role === 'user'
                                ? 'bg-blue-600 text-white rounded-br-none'
                                : 'bg-gray-700 text-gray-100 rounded-bl-none'
                            }`}>
                            {msg.text}
                        </div>
                    </div>
                ))}
                {loading && (
                    <div className="flex justify-start">
                        <div className="bg-gray-700 rounded-2xl rounded-bl-none px-4 py-3 text-sm text-gray-400 flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></span>
                            <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]"></span>
                            <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0.4s]"></span>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 bg-gray-750 border-t border-gray-700">
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask a question..."
                        className="flex-1 bg-gray-900 border border-gray-600 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-500"
                    />
                    <button
                        onClick={handleSend}
                        disabled={!input.trim() || loading}
                        className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white p-3 rounded-xl transition-colors shadow-lg shadow-blue-900/20"
                    >
                        <Send size={18} />
                    </button>
                </div>
            </div>
        </div>
    )
}
