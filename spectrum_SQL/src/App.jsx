import { useState, useRef, useEffect } from 'react'
import { Sparkles, MessageSquare, Plus, PanelLeft, PanelLeftClose, Trash2 } from 'lucide-react'
import MessageBubble from './components/MessageBubble'
import ChatInput from './components/ChatInput'

function App() {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isAnalysisEnabled, setIsAnalysisEnabled] = useState(false)
  const [isVisualAnalysisEnabled, setIsVisualAnalysisEnabled] = useState(false)

  // Chat History State
  const [allChats, setAllChats] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)

  const scrollRef = useRef(null)
  const abortControllerRef = useRef(null)
  const isSwitchingChatRef = useRef(false)

  // Fetch all sessions on mount
  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('/api/sessions')
        if (response.ok) {
          const data = await response.json()
          setAllChats(data)
        }
      } catch (error) {
        console.error("Failed to fetch sessions", error)
      }
    }
    fetchSessions()
  }, [])

  // Auto scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = async (query) => {
    // Add user message to UI
    setMessages(prev => [...prev, { role: 'user', content: query }])

    // Add loading state
    setIsLoading(true)
    setMessages(prev => [...prev, { role: 'assistant', type: 'loading' }])

    let sessionId = currentChatId;
    if (!sessionId) {
      try {
        const res = await fetch('/api/sessions', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          sessionId = data.id;
          setCurrentChatId(sessionId);
          // Update sidebar with new chat
          setAllChats(prev => [{ id: sessionId, title: query, date: new Date().toISOString() }, ...prev]);
        }
      } catch (e) {
        console.error("Failed to create session", e);
      }
    } else {
      // Update title of existing chat if it's "New Chat"
      setAllChats(prev => prev.map(c => 
        c.id === sessionId && c.title === "New Chat" ? { ...c, title: query } : c
      ));
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          session_id: sessionId
        }),
        signal: controller.signal
      })

      const data = await response.json()

      // Replace loading state with actual response
      setMessages(prev => {
        const newMsgs = [...prev]
        newMsgs.pop() // remove loading

        if (!response.ok) {
          let errorContent = data.detail || "An error occurred while generating the response.";
          const lowerError = errorContent.toLowerCase();
          if (lowerError.includes('timeout') || lowerError.includes('hyt00')) {
            errorContent = "The query took longer than the 45-second limit and was stopped. Please try a more specific question, or ask for a narrower time range.";
          }

          newMsgs.push({
            id: data.message_id, // backend should return this even on error if possible, though we might not update errors
            role: 'assistant',
            type: 'error',
            content: errorContent
          })
        } else {
          newMsgs.push({
            id: data.message_id,
            role: 'assistant',
            type: 'success',
            query: query,
            analysisEnabled: isAnalysisEnabled,
            visualAnalysisEnabled: isVisualAnalysisEnabled,
            ...data
          })
        }
        return newMsgs
      })
    } catch (error) {
      if (error.name === 'AbortError') {
        if (!isSwitchingChatRef.current) {
          setMessages(prev => {
            const newMsgs = [...prev]
            newMsgs.pop() // remove loading
            newMsgs.push({
              role: 'assistant',
              type: 'error',
              content: "Query was stopped."
            })
            return newMsgs
          })
        }
      } else {
        setMessages(prev => {
          const newMsgs = [...prev]
          newMsgs.pop() // remove loading
          newMsgs.push({
            role: 'assistant',
            type: 'error',
            content: "Failed to connect to the backend server. Is it running?"
          })
          return newMsgs
        })
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null;
    }
  }

  const handleStop = (isSwitching = false) => {
    const switching = typeof isSwitching === 'boolean' ? isSwitching : false;
    if (abortControllerRef.current) {
      isSwitchingChatRef.current = switching;
      abortControllerRef.current.abort();
    }
  }

  const handleAnalysisComplete = async (index, analysisData, messageId) => {
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs[index]) {
        newMsgs[index] = { ...newMsgs[index], analysis: analysisData };
      }
      return newMsgs;
    });

    if (messageId) {
      try {
        await fetch(`/api/messages/${messageId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ analysis: analysisData })
        });
      } catch (e) {
        console.error("Failed to save analysis to backend", e);
      }
    }
  }

  const handleVisualAnalysisComplete = async (index, specData, messageId) => {
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs[index]) {
        newMsgs[index] = { ...newMsgs[index], visual_spec: specData };
      }
      return newMsgs;
    });

    if (messageId) {
      try {
        await fetch(`/api/messages/${messageId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ visual_spec: specData })
        });
      } catch (e) {
        console.error("Failed to save visual spec to backend", e);
      }
    }
  }

  const createNewChat = () => {
    isSwitchingChatRef.current = true;
    handleStop();
    setCurrentChatId(null);
    setMessages([]);
    isSwitchingChatRef.current = false;
  }

  const handleChatSelect = async (chatId) => {
    isSwitchingChatRef.current = true;
    handleStop(); // Abort any ongoing request
    setCurrentChatId(chatId);
    setMessages([{ role: 'assistant', type: 'loading_history' }]); // temporary loading state
    
    try {
      const response = await fetch(`/api/sessions/${chatId}/messages`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data);
      } else {
        setMessages([{ role: 'assistant', type: 'error', content: 'Failed to load chat history.' }]);
      }
    } catch (e) {
      console.error("Failed to load messages", e);
      setMessages([{ role: 'assistant', type: 'error', content: 'Failed to connect to server.' }]);
    } finally {
      isSwitchingChatRef.current = false;
    }
  }

  const deleteChat = async (id) => {
    setAllChats(prev => prev.filter(c => c.id !== id));
    if (currentChatId === id) {
      handleStop(true);
      setCurrentChatId(null);
      setMessages([]);
    }
    try {
      await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    } catch (e) {
      console.error("Failed to delete chat on backend", e);
    }
  }

  return (
    <div className="claude-layout">
      {/* Sidebar */}
      <aside className={`sidebar ${isSidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header" style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="sidebar-toggle"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
            >
              {isSidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeft size={20} />}
            </button>
            <span className="sidebar-text" style={{ fontWeight: 600, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={18} style={{ color: '#d97757' }} /> ERP Co-Pilot
            </span>
          </div>
        </div>

        <div className="sidebar-item" style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="sidebar-text" style={{ fontSize: '0.9rem' }}>Auto-Analysis</span>
          <label className="switch">
            <input
              type="checkbox"
              checked={isAnalysisEnabled}
              onChange={(e) => setIsAnalysisEnabled(e.target.checked)}
            />
            <span className="slider round"></span>
          </label>
        </div>

        <div className="sidebar-item" style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="sidebar-text" style={{ fontSize: '0.9rem' }}>Visual Analysis</span>
          <label className="switch">
            <input
              type="checkbox"
              checked={isVisualAnalysisEnabled}
              onChange={(e) => setIsVisualAnalysisEnabled(e.target.checked)}
            />
            <span className="slider round"></span>
          </label>
        </div>

        <div
          className="sidebar-item"
          style={{ marginTop: '16px' }}
          onClick={createNewChat}
        >
          <Plus size={18} className="sidebar-icon" />
          <span className="sidebar-text">New chat</span>
        </div>

        <div className="sidebar-item" style={{ cursor: 'default', color: 'var(--text-main)', opacity: 0.5, marginTop: '16px' }}>
          <MessageSquare size={18} className="sidebar-icon" />
          <span className="sidebar-text" style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase' }}>Recent Chats</span>
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: '4px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {allChats.map(chat => (
            <div
              key={chat.id}
              className="sidebar-item"
              style={{
                background: currentChatId === chat.id ? 'rgba(255, 255, 255, 0.1)' : 'transparent',
                color: currentChatId === chat.id ? '#fff' : '#a3a3a3',
                display: 'flex',
                justifyContent: 'space-between',
                paddingRight: '8px'
              }}
              onClick={() => handleChatSelect(chat.id)}
              title={chat.title}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', overflow: 'hidden' }}>
                <MessageSquare size={16} className="sidebar-icon" style={{ flexShrink: 0 }} />
                <span className="sidebar-text" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {chat.title}
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteChat(chat.id);
                }}
                className="delete-btn sidebar-text"
                style={{ background: 'transparent', border: 'none', color: '#a3a3a3', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <div className="chat-container" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="claude-greeting">
              <Sparkles size={48} style={{ color: '#d97757' }} />
              Type, discover, go.
            </div>
          ) : (
            messages.map((msg, idx) => (
              <MessageBubble
                key={idx}
                message={msg}
                onAnalysisComplete={(data) => handleAnalysisComplete(idx, data, msg.id)}
                onVisualAnalysisComplete={(spec) => handleVisualAnalysisComplete(idx, spec, msg.id)}
              />
            ))
          )}
        </div>

        <ChatInput onSend={handleSend} onStop={handleStop} isLoading={isLoading} />
      </main>
    </div>
  )
}

export default App
