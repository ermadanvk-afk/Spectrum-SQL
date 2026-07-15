import { useState, useRef, useEffect } from 'react'
import { Sparkles, MessageSquare, Plus, PanelLeft, PanelLeftClose, Trash2, LogOut, Shield, Settings, UserPlus, X } from 'lucide-react'
import MessageBubble from './components/MessageBubble'
import ChatInput from './components/ChatInput'
import Auth from './components/Auth'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [userRole, setUserRole] = useState(null)
  const [userName, setUserName] = useState(null)
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isAnalysisEnabled, setIsAnalysisEnabled] = useState(false)
  const [isVisualAnalysisEnabled, setIsVisualAnalysisEnabled] = useState(false)
  const [sessionExpiredModal, setSessionExpiredModal] = useState(false)
  
  const [userPermissions, setUserPermissions] = useState({ display_token: false, display_sql: false, user_type: 2 })
  const [adminModalOpen, setAdminModalOpen] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'Purchase Manager', display_token: false, display_sql: false, user_type: 2 })
  const [adminStatus, setAdminStatus] = useState({ message: '', error: '' })

  // Chat History State
  const [allChats, setAllChats] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)

  const scrollRef = useRef(null)
  const abortControllerRef = useRef(null)
  const isSwitchingChatRef = useRef(false)

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    } catch (e) {
      console.error('Logout failed', e)
    }
    setIsAuthenticated(false)
    setUserRole(null)
    setUserName(null)
    setMessages([])
    setAllChats([])
    setCurrentChatId(null)
  }

  const handleLoginSuccess = (tokenOrRole, possibleRole, perms, username) => {
    const role = possibleRole || tokenOrRole // Handle old and new Auth.jsx signatures
    setIsAuthenticated(true)
    setUserRole(role || null)
    if (perms) {
      setUserPermissions(perms)
    }
    if (username) {
      setUserName(username)
    }
  }

  const apiFetch = async (url, options = {}) => {
    let response = await fetch(url, {
      ...options,
      credentials: 'include'
    })

    if (response.status === 401 && url !== '/api/auth/me' && url !== '/api/auth/login' && url !== '/api/auth/logout' && url !== '/api/auth/refresh') {
      try {
        const refreshResponse = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'include'
        })
        
        if (refreshResponse.ok) {
          response = await fetch(url, {
            ...options,
            credentials: 'include'
          })
          
          if (response.ok) {
            return response
          }
        }
      } catch (e) {
        console.error("Silent refresh failed", e)
      }
      
      window.dispatchEvent(new Event('sessionExpired'))
      throw new Error("SESSION_EXPIRED")
    }

    return response
  }

  useEffect(() => {
    const handleSessionExpired = () => setSessionExpiredModal(true)
    window.addEventListener('sessionExpired', handleSessionExpired)
    return () => window.removeEventListener('sessionExpired', handleSessionExpired)
  }, [])

  // Fetch all sessions on mount or when token changes
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await apiFetch('/api/auth/me')
        if (response.ok) {
          const data = await response.json()
          setIsAuthenticated(true)
          setUserRole(data.role || null)
          setUserName(data.username || null)
          setUserPermissions({
            display_token: data.display_token,
            display_sql: data.display_sql,
            user_type: data.user_type
          })
        } else {
          setIsAuthenticated(false)
        }
      } catch (error) {
        console.error("Failed to fetch user info", error)
        setIsAuthenticated(false)
      } finally {
        setIsCheckingAuth(false)
      }
    }
    checkAuth()
  }, [])

  useEffect(() => {
    if (!isAuthenticated) return
    const fetchSessions = async () => {
      try {
        const response = await apiFetch('/api/sessions')
        if (response.ok) {
          const data = await response.json()
          setAllChats(data)
        }
      } catch (error) {
        console.error("Failed to fetch sessions", error)
      }
    }
    fetchSessions()
  }, [isAuthenticated])

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
        const res = await apiFetch('/api/sessions', { method: 'POST' });
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
      const response = await apiFetch('/api/ask', {
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
            id: data.message_id,
            role: 'assistant',
            type: 'error',
            content: errorContent
          })
        } else if (data.status === 'error') {
          // Backend returned 200 but pipeline reported an error (e.g. AUTH_ERROR)
          newMsgs.push({
            id: data.message_id,
            role: 'assistant',
            type: 'error',
            content: data.explanation || "You do not have access to the requested data."
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
        if (error.message !== "SESSION_EXPIRED") {
          setMessages(prev => {
            const newMsgs = [...prev]
            newMsgs.pop() // remove loading
            newMsgs.push({
              role: 'assistant',
              type: 'error',
              content: error.message || "Failed to connect to the backend server. Is it running?"
            })
            return newMsgs
          })
        }
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
    let updatedCost = null;
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs[index]) {
        const currentCost = newMsgs[index].cost;
        if (currentCost && analysisData.cost) {
          updatedCost = {
            input_tokens: currentCost.input_tokens + analysisData.cost.input_tokens,
            output_tokens: currentCost.output_tokens + analysisData.cost.output_tokens,
            cost_inr: currentCost.cost_inr + analysisData.cost.cost_inr
          };
          newMsgs[index] = { ...newMsgs[index], analysis: analysisData, cost: updatedCost };
        } else {
          newMsgs[index] = { ...newMsgs[index], analysis: analysisData };
        }
      }
      return newMsgs;
    });

    if (messageId) {
      try {
        const body = { analysis: analysisData };
        if (analysisData.cost) body.cost = analysisData.cost;
        await apiFetch(`/api/messages/${messageId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
      } catch (e) {
        console.error("Failed to save analysis to backend", e);
      }
    }
  }

  const handleVisualAnalysisComplete = async (index, specData, messageId) => {
    let updatedCost = null;
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs[index]) {
        const currentCost = newMsgs[index].cost;
        if (currentCost && specData.cost) {
          updatedCost = {
            input_tokens: currentCost.input_tokens + specData.cost.input_tokens,
            output_tokens: currentCost.output_tokens + specData.cost.output_tokens,
            cost_inr: currentCost.cost_inr + specData.cost.cost_inr
          };
          newMsgs[index] = { ...newMsgs[index], visual_spec: specData, cost: updatedCost };
        } else {
          newMsgs[index] = { ...newMsgs[index], visual_spec: specData };
        }
      }
      return newMsgs;
    });

    if (messageId) {
      try {
        const body = { visual_spec: specData };
        if (specData.cost) body.cost = specData.cost;
        await apiFetch(`/api/messages/${messageId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
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
      const response = await apiFetch(`/api/sessions/${chatId}/messages`);
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
      await apiFetch(`/api/sessions/${id}`, { method: 'DELETE' });
    } catch (e) {
      console.error("Failed to delete chat on backend", e);
    }
  }

  if (isCheckingAuth) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', backgroundColor: '#111', color: '#d97757' }}>
        Loading...
      </div>
    )
  }

  // If not logged in, show the Auth screen
  if (!isAuthenticated) {
    return <Auth onLoginSuccess={handleLoginSuccess} />
  }
  
  const handleCreateUser = async (e) => {
    e.preventDefault()
    setAdminStatus({ message: '', error: '' })
    try {
      const response = await apiFetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUser)
      })
      const data = await response.json()
      if (response.ok) {
        setAdminStatus({ message: 'User created successfully!', error: '' })
        setNewUser({ username: '', password: '', role: 'Purchase Manager', display_token: false, display_sql: false, user_type: 2 })
      } else {
        setAdminStatus({ error: data.detail || 'Failed to create user.', message: '' })
      }
    } catch (error) {
      setAdminStatus({ error: error.message || 'Error creating user.', message: '' })
    }
  }

  return (
    <div className="claude-layout">
      {sessionExpiredModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(4px)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <div style={{
            backgroundColor: '#1e1e1e',
            padding: '32px',
            borderRadius: '12px',
            border: '1px solid #333',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '16px',
            maxWidth: '400px',
            textAlign: 'center'
          }}>
            <Shield size={48} style={{ color: '#d97757' }} />
            <h2 style={{ color: '#eee', margin: 0, fontWeight: 600 }}>Session Expired</h2>
            <p style={{ color: '#aaa', margin: 0, fontSize: '0.95rem' }}>Hey, your session is expired. Kindly login again.</p>
            <button 
              onClick={() => {
                setSessionExpiredModal(false)
                handleLogout()
              }}
              style={{
                marginTop: '8px',
                backgroundColor: '#d97757',
                color: 'white',
                border: 'none',
                padding: '12px 24px',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: 'pointer',
                width: '100%',
                transition: 'opacity 0.2s'
              }}
              onMouseOver={(e) => e.target.style.opacity = 0.9}
              onMouseOut={(e) => e.target.style.opacity = 1}
            >
              Login Again
            </button>
          </div>
        </div>
      )}

      {/* Admin Settings Modal */}
      {adminModalOpen && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(4px)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <div style={{
            backgroundColor: '#1e1e1e',
            padding: '32px',
            borderRadius: '12px',
            border: '1px solid #333',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            width: '100%',
            maxWidth: '450px',
            position: 'relative'
          }}>
            <button 
              onClick={() => {
                setAdminModalOpen(false)
                setAdminStatus({ message: '', error: '' })
              }}
              style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <UserPlus size={28} style={{ color: '#d97757' }} />
              <h2 style={{ color: '#eee', margin: 0, fontWeight: 600 }}>Create New User</h2>
            </div>
            
            {adminStatus.error && <div style={{ padding: '10px', backgroundColor: 'rgba(239,68,68,0.1)', color: '#fca5a5', borderRadius: '6px', fontSize: '0.85rem' }}>{adminStatus.error}</div>}
            {adminStatus.message && <div style={{ padding: '10px', backgroundColor: 'rgba(34,197,94,0.1)', color: '#86efac', borderRadius: '6px', fontSize: '0.85rem' }}>{adminStatus.message}</div>}

            <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <input type="text" placeholder="Username" required value={newUser.username} onChange={(e) => setNewUser({...newUser, username: e.target.value})} style={{ padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff' }} />
              <input type="password" placeholder="Password" required value={newUser.password} onChange={(e) => setNewUser({...newUser, password: e.target.value})} style={{ padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff' }} />
              <select value={newUser.role} onChange={(e) => setNewUser({...newUser, role: e.target.value})} style={{ padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff' }}>
                <option value="Purchase Manager">Purchase Manager</option>
              </select>
              <select value={newUser.user_type} onChange={(e) => setNewUser({...newUser, user_type: parseInt(e.target.value)})} style={{ padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff' }}>
                <option value={2}>General User</option>
                <option value={1}>Admin</option>
              </select>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input type="checkbox" id="display_token" checked={newUser.display_token} onChange={(e) => setNewUser({...newUser, display_token: e.target.checked})} />
                <label htmlFor="display_token" style={{ color: '#aaa', fontSize: '0.9rem' }}>Allow viewing Tokens & Cost</label>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input type="checkbox" id="display_sql" checked={newUser.display_sql} onChange={(e) => setNewUser({...newUser, display_sql: e.target.checked})} />
                <label htmlFor="display_sql" style={{ color: '#aaa', fontSize: '0.9rem' }}>Allow viewing Generated SQL</label>
              </div>
              
              <button type="submit" style={{ padding: '12px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer', marginTop: '8px' }}>
                Create User
              </button>
            </form>
          </div>
        </div>
      )}

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

        {/* Role Badge */}
        {userRole && (
          <div className="sidebar-item" style={{
            marginTop: '8px',
            padding: '8px 16px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            gap: '6px',
            cursor: 'default'
          }}>
            {userName && (
              <span className="sidebar-text" style={{ fontSize: '0.9rem', color: '#eee', fontWeight: 600, paddingLeft: '4px' }}>
                Hi, {userName}!
              </span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Shield size={16} style={{ color: '#d97757', flexShrink: 0 }} />
              <span className="sidebar-text" style={{
                fontSize: '0.8rem',
                fontWeight: 600,
                color: '#d97757',
                backgroundColor: 'rgba(217, 119, 87, 0.1)',
                padding: '4px 12px',
                borderRadius: '12px',
                border: '1px solid rgba(217, 119, 87, 0.25)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}>
                {userRole}
              </span>
            </div>
          </div>
        )}


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
          {isSidebarOpen && allChats.map(chat => (
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

        {userPermissions.user_type === 1 && (
          <div
            className="sidebar-item"
            style={{
              marginTop: 'auto',
              borderTop: '1px solid var(--border-light)',
              paddingTop: '16px',
              color: '#a3a3a3'
            }}
            onClick={() => setAdminModalOpen(true)}
          >
            <Settings size={18} className="sidebar-icon" />
            <span className="sidebar-text">Admin Settings</span>
          </div>
        )}

        {/* Logout Button */}
        <div
          className="sidebar-item"
          style={{
            marginTop: userPermissions.user_type === 1 ? '8px' : 'auto',
            borderTop: userPermissions.user_type === 1 ? 'none' : '1px solid var(--border-light)',
            paddingTop: userPermissions.user_type === 1 ? '0px' : '16px',
            color: '#ef4444'
          }}
          onClick={handleLogout}
        >
          <LogOut size={18} className="sidebar-icon" />
          <span className="sidebar-text">Log out</span>
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
                showCost={userPermissions.display_token}
                showSql={userPermissions.display_sql}
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
