import { useState, useRef, useEffect } from 'react'
import { Sparkles, MessageSquare, Plus, PanelLeft, PanelLeftClose, Trash2 } from 'lucide-react'
import MessageBubble from './components/MessageBubble'
import ChatInput from './components/ChatInput'

function App() {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false) // default closed to match requested view
  const [isAnalysisEnabled, setIsAnalysisEnabled] = useState(false)
  const [isVisualAnalysisEnabled, setIsVisualAnalysisEnabled] = useState(false)

  // Chat History State
  const [allChats, setAllChats] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)

  const scrollRef = useRef(null)
  const abortControllerRef = useRef(null)
  const isSwitchingChatRef = useRef(false)

  // Load history from local storage on mount
  useEffect(() => {
    const savedChats = localStorage.getItem('spectrum_chats')
    if (savedChats) {
      try {
        let parsedChats = JSON.parse(savedChats);
        // Clean up any broken loading states that might have been saved previously
        parsedChats = parsedChats.map(chat => ({
          ...chat,
          messages: chat.messages.filter(m => m.type !== 'loading').map(m => ({ ...m, isHistorical: true }))
        }));
        setAllChats(parsedChats);
      } catch (e) {
        console.error("Failed to parse chat history", e)
      }
    }
  }, [])

  // Save to local storage whenever messages change
  useEffect(() => {
    if (messages.length === 0) return;

    // Filter out loading messages so they don't get stuck forever on chat switch
    const persistentMessages = messages.filter(m => m.type !== 'loading');

    let chatId = currentChatId;

    setAllChats(prevChats => {
      const existingChatIndex = prevChats.findIndex(c => c.id === chatId);
      let updatedChats = [...prevChats];

      if (existingChatIndex >= 0) {
        // Update existing chat
        updatedChats[existingChatIndex] = {
          ...updatedChats[existingChatIndex],
          messages: persistentMessages
        };
      } else {
        // Create new chat
        chatId = Date.now().toString();
        setCurrentChatId(chatId);

        // Find the first user message for the title
        const firstUserMsg = persistentMessages.find(m => m.role === 'user');
        const title = firstUserMsg ? firstUserMsg.content : "New Chat";

        updatedChats.unshift({
          id: chatId,
          title: title,
          messages: persistentMessages,
          date: new Date().toISOString()
        });
      }

      localStorage.setItem('spectrum_chats', JSON.stringify(updatedChats));
      return updatedChats;
    });
  }, [messages])

  // Auto scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = async (query) => {
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: query }])

    // Add loading state
    setIsLoading(true)
    setMessages(prev => [...prev, { role: 'assistant', type: 'loading' }])

    // Extract history of successful interactions
    const successfulPairs = [];
    let currentUserMsg = null;

    // Parse current messages state before adding the new query
    for (const msg of messages) {
      if (msg.role === 'user') {
        currentUserMsg = msg.content;
      } else if (msg.role === 'assistant' && msg.type === 'success' && currentUserMsg) {
        successfulPairs.push({ question: currentUserMsg, sql: msg.sql });
        currentUserMsg = null;
      }
    }

    // Sliding window: keep only the last 3 interactions
    const history = successfulPairs.slice(-3);

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
          history: history
        }),
        signal: controller.signal
      })

      const data = await response.json()

      // Replace loading state with actual response
      setMessages(prev => {
        const newMsgs = [...prev]
        newMsgs.pop() // remove loading

        if (!response.ok) {
          newMsgs.push({
            role: 'assistant',
            type: 'error',
            content: data.detail || "An error occurred while generating the response."
          })
        } else {
          newMsgs.push({
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

  const handleAnalysisComplete = (index, analysisData) => {
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs[index]) {
        newMsgs[index] = { ...newMsgs[index], analysis: analysisData };
      }
      return newMsgs;
    });
  }

  const handleVisualAnalysisComplete = (index, specData) => {
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs[index]) {
        newMsgs[index] = { ...newMsgs[index], visual_spec: specData };
      }
      return newMsgs;
    });
  }

  const createNewChat = () => {
    isSwitchingChatRef.current = true;
    handleStop();
    setCurrentChatId(null);
    setMessages([]);
    isSwitchingChatRef.current = false;
  }

  const handleChatSelect = (chatId) => {
    isSwitchingChatRef.current = true;
    handleStop(); // Abort any ongoing request
    const chat = allChats.find(c => c.id === chatId);
    if (chat) {
      setCurrentChatId(chatId);
      setMessages(chat.messages);
    }
    isSwitchingChatRef.current = false;
  }

  const deleteChat = (id) => {
    setAllChats(prev => {
      const updated = prev.filter(c => c.id !== id);
      localStorage.setItem('spectrum_chats', JSON.stringify(updated));
      return updated;
    });
    if (currentChatId === id) {
      handleStop(true);
      setCurrentChatId(null);
      setMessages([]);
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
              <Sparkles size={18} style={{ color: '#d97757' }} /> Spectrum SQL
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
                onAnalysisComplete={(data) => handleAnalysisComplete(idx, data)}
                onVisualAnalysisComplete={(spec) => handleVisualAnalysisComplete(idx, spec)}
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
