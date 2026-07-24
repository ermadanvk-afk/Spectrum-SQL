import React, { useState, useEffect } from 'react';
import { X, UserPlus, Shield, Edit2, Check, XCircle, Users, Database, FileText, ArrowLeft } from 'lucide-react';

export default function AdminSettingsModal({ onClose, apiFetch }) {
  const [showMainMenu, setShowMainMenu] = useState(true);
  const [activeTab, setActiveTab] = useState('user_settings');
  const [view, setView] = useState('list'); // 'list', 'create', 'edit'
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([{ name: 'Purchase Manager' }]);
  const [databases, setDatabases] = useState([]);
  const [status, setStatus] = useState({ message: '', error: '' });
  
  const [logs, setLogs] = useState([]);
  const [logsPagination, setLogsPagination] = useState({ page: 1, total_pages: 1, total: 0 });
  const [logDates, setLogDates] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return { start: d.toISOString().split('T')[0], end: new Date().toISOString().split('T')[0] };
  });

  
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    roles: ['Purchase Manager'],
    display_token: false,
    display_sql: false,
    user_type: 2,
    is_active: true,
    allowed_databases: []
  });
  const [editingUserId, setEditingUserId] = useState(null);

  const [editingDbId, setEditingDbId] = useState(null);
  const [dbFormData, setDbFormData] = useState({ name: '', connection_string: '' });

  useEffect(() => {
    fetchUsers();
    fetchRoles();
    fetchDatabases();
  }, []);

  const fetchUsers = async () => {
    try {
      const res = await apiFetch('/api/users');
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
      } else {
        setStatus({ error: 'Failed to fetch users', message: '' });
      }
    } catch (e) {
      setStatus({ error: 'Error fetching users', message: '' });
    }
  };

  const fetchRoles = async () => {
    try {
      const res = await apiFetch('/api/roles');
      if (res.ok) {
        const data = await res.json();
        if (data && data.length > 0) {
          setRoles(data);
        }
      }
    } catch (e) {
      console.error('Failed to fetch roles', e);
    }
  };

  const fetchDatabases = async () => {
    try {
      const res = await apiFetch('/api/databases');
      if (res.ok) {
        const data = await res.json();
        setDatabases(data);
      }
    } catch (e) {
      console.error('Failed to fetch databases', e);
    }
  };

  const fetchLogs = async (page = 1) => {
    try {
      const params = new URLSearchParams({
        page: page,
        page_size: 15,
        start_date: logDates.start ? new Date(logDates.start).toISOString() : '',
        end_date: logDates.end ? new Date(logDates.end + 'T23:59:59.999Z').toISOString() : ''
      });
      const res = await apiFetch(`/api/logs?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.data);
        setLogsPagination({ page: data.page, total_pages: data.total_pages, total: data.total });
      } else {
        setStatus({ error: 'Failed to fetch logs', message: '' });
      }
    } catch (e) {
      setStatus({ error: 'Error fetching logs', message: '' });
    }
  };


  const handleCreateUser = async (e) => {
    e.preventDefault();
    setStatus({ message: '', error: '' });
    try {
      const response = await apiFetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      const data = await response.json();
      if (response.ok) {
        setStatus({ message: 'User created successfully!', error: '' });
        fetchUsers();
        setView('list');
      } else {
        setStatus({ error: data.detail || 'Failed to create user.', message: '' });
      }
    } catch (error) {
      setStatus({ error: error.message || 'Error creating user.', message: '' });
    }
  };

  const handleUpdateUser = async (e) => {
    e.preventDefault();
    setStatus({ message: '', error: '' });
    
    // We only send password if it's provided
    const updateData = { ...formData };
    if (!updateData.password) {
      delete updateData.password;
    }
    
    try {
      const response = await apiFetch(`/api/users/${editingUserId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateData)
      });
      const data = await response.json();
      if (response.ok) {
        setStatus({ message: 'User updated successfully!', error: '' });
        fetchUsers();
        setView('list');
      } else {
        setStatus({ error: data.detail || 'Failed to update user.', message: '' });
      }
    } catch (error) {
      setStatus({ error: error.message || 'Error updating user.', message: '' });
    }
  };

  const handleCreateDatabase = async (e) => {
    e.preventDefault();
    setStatus({ message: '', error: '' });
    try {
      const response = await apiFetch('/api/databases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dbFormData)
      });
      const data = await response.json();
      if (response.ok) {
        setStatus({ message: 'Database added successfully!', error: '' });
        fetchDatabases();
        setView('db_list');
      } else {
        setStatus({ error: data.detail || 'Failed to add database.', message: '' });
      }
    } catch (error) {
      setStatus({ error: error.message || 'Error adding database.', message: '' });
    }
  };

  const handleUpdateDatabase = async (e) => {
    e.preventDefault();
    setStatus({ message: '', error: '' });
    try {
      const response = await apiFetch(`/api/databases/${editingDbId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dbFormData)
      });
      const data = await response.json();
      if (response.ok) {
        setStatus({ message: 'Database updated successfully!', error: '' });
        fetchDatabases();
        setView('db_list');
      } else {
        setStatus({ error: data.detail || 'Failed to update database.', message: '' });
      }
    } catch (error) {
      setStatus({ error: error.message || 'Error updating database.', message: '' });
    }
  };

  const handleDeleteDatabase = async (dbId) => {
    if (!window.confirm('Are you sure you want to delete this database?')) return;
    setStatus({ message: '', error: '' });
    try {
      const response = await apiFetch(`/api/databases/${dbId}`, { method: 'DELETE' });
      if (response.ok) {
        setStatus({ message: 'Database deleted successfully!', error: '' });
        fetchDatabases();
      } else {
        const data = await response.json();
        setStatus({ error: data.detail || 'Failed to delete database.', message: '' });
      }
    } catch (error) {
      setStatus({ error: error.message || 'Error deleting database.', message: '' });
    }
  };

  const openEdit = (user) => {
    setFormData({
      username: user.username,
      password: '', // Blank by default, only update if typed
      roles: user.roles || (roles.length > 0 ? [roles[0].name] : ['Purchase Manager']),
      display_token: user.display_token,
      display_sql: user.display_sql,
      user_type: user.user_type,
      is_active: user.is_active !== undefined ? user.is_active : true,
      allowed_databases: user.allowed_databases || []
    });
    setEditingUserId(user.id);
    setView('edit');
    setStatus({ message: '', error: '' });
  };

  const openCreate = () => {
    setFormData({
      username: '',
      password: '',
      roles: roles.length > 0 ? [roles[0].name] : ['Purchase Manager'],
      display_token: false,
      display_sql: false,
      user_type: 2,
      is_active: true,
      allowed_databases: []
    });
    setView('create');
    setStatus({ message: '', error: '' });
  };

  return (
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
        padding: showMainMenu ? '32px' : '24px',
        borderRadius: showMainMenu ? '12px' : '0',
        border: showMainMenu ? '1px solid #333' : 'none',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        width: showMainMenu ? '100%' : '100vw',
        maxWidth: showMainMenu ? '900px' : '100vw',
        height: showMainMenu ? '85vh' : '100vh',
        boxSizing: 'border-box',
        position: 'relative',
        overflowY: 'hidden',
        transition: 'all 0.3s ease'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #333', paddingBottom: '16px', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {showMainMenu ? (
              <Shield size={28} style={{ color: '#d97757' }} />
            ) : (
              <button 
                onClick={() => {
                  if (activeTab === 'user_settings' && (view === 'create' || view === 'edit')) {
                    setView('list');
                    setStatus({ message: '', error: '' });
                  } else if (activeTab === 'db_settings' && (view === 'db_create' || view === 'db_edit')) {
                    setView('db_list');
                    setStatus({ message: '', error: '' });
                  } else {
                    setShowMainMenu(true);
                  }
                }} 
                style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '4px' }}
              >
                <ArrowLeft size={24} />
              </button>
            )}
            <h2 style={{ color: '#eee', margin: 0, fontWeight: 600 }}>
              {showMainMenu ? 'Settings' : (
                activeTab === 'user_settings' ? 'Settings > User Settings' :
                activeTab === 'db_settings' ? 'Settings > Database Configs' :
                'Settings > System Logs'
              )}
            </h2>
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            {!showMainMenu && activeTab === 'user_settings' && view === 'list' && (
                <button 
                  onClick={openCreate}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
                >
                  <UserPlus size={16} /> New User
                </button>
            )}
            
            {!showMainMenu && activeTab === 'db_settings' && view === 'db_list' && (
                <button 
                  onClick={() => {
                    setDbFormData({ name: '', connection_string: '' });
                    setView('db_create');
                    setStatus({ message: '', error: '' });
                  }}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                >
                  New Database
                </button>
            )}


            <button 
              onClick={() => showMainMenu ? onClose() : setShowMainMenu(true)}
              style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '4px' }}
              title={showMainMenu ? "Close" : "Back"}
            >
              <X size={24} />
            </button>
          </div>
        </div>
        
        {status.error && <div style={{ padding: '10px', backgroundColor: 'rgba(239,68,68,0.1)', color: '#fca5a5', borderRadius: '6px', fontSize: '0.85rem' }}>{status.error}</div>}
        {status.message && <div style={{ padding: '10px', backgroundColor: 'rgba(34,197,94,0.1)', color: '#86efac', borderRadius: '6px', fontSize: '0.85rem' }}>{status.message}</div>}

        {showMainMenu ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '24px', flex: 1, padding: '24px 0', alignContent: 'center' }}>
            <button
              onClick={() => { setActiveTab('user_settings'); setView('list'); setShowMainMenu(false); setStatus({ message: '', error: '' }); }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px',
                backgroundColor: 'rgba(217, 119, 87, 0.1)', border: '1px solid rgba(217, 119, 87, 0.3)', borderRadius: '12px',
                padding: '32px 16px', cursor: 'pointer', color: '#fff', transition: 'all 0.2s ease',
                height: '100%', minHeight: '220px'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(217, 119, 87, 0.2)'; e.currentTarget.style.borderColor = '#d97757'; e.currentTarget.style.transform = 'translateY(-4px)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'rgba(217, 119, 87, 0.1)'; e.currentTarget.style.borderColor = 'rgba(217, 119, 87, 0.3)'; e.currentTarget.style.transform = 'none'; }}
            >
              <Users size={48} color="#d97757" />
              <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>User Settings</span>
              <span style={{ fontSize: '0.85rem', color: '#aaa', textAlign: 'center' }}>Manage users, roles, and access</span>
            </button>
            <button
              onClick={() => { setActiveTab('db_settings'); setView('db_list'); setShowMainMenu(false); setStatus({ message: '', error: '' }); fetchDatabases(); }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px',
                backgroundColor: 'rgba(217, 119, 87, 0.1)', border: '1px solid rgba(217, 119, 87, 0.3)', borderRadius: '12px',
                padding: '32px 16px', cursor: 'pointer', color: '#fff', transition: 'all 0.2s ease',
                height: '100%', minHeight: '220px'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(217, 119, 87, 0.2)'; e.currentTarget.style.borderColor = '#d97757'; e.currentTarget.style.transform = 'translateY(-4px)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'rgba(217, 119, 87, 0.1)'; e.currentTarget.style.borderColor = 'rgba(217, 119, 87, 0.3)'; e.currentTarget.style.transform = 'none'; }}
            >
              <Database size={48} color="#d97757" />
              <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>Database Configs</span>
              <span style={{ fontSize: '0.85rem', color: '#aaa', textAlign: 'center' }}>Add or delete connections</span>
            </button>
            <button
              onClick={() => { setActiveTab('logs'); setShowMainMenu(false); fetchLogs(1); setStatus({ message: '', error: '' }); }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px',
                backgroundColor: 'rgba(217, 119, 87, 0.1)', border: '1px solid rgba(217, 119, 87, 0.3)', borderRadius: '12px',
                padding: '32px 16px', cursor: 'pointer', color: '#fff', transition: 'all 0.2s ease',
                height: '100%', minHeight: '220px'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(217, 119, 87, 0.2)'; e.currentTarget.style.borderColor = '#d97757'; e.currentTarget.style.transform = 'translateY(-4px)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'rgba(217, 119, 87, 0.1)'; e.currentTarget.style.borderColor = 'rgba(217, 119, 87, 0.3)'; e.currentTarget.style.transform = 'none'; }}
            >
              <FileText size={48} color="#d97757" />
              <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>System Logs</span>
              <span style={{ fontSize: '0.85rem', color: '#aaa', textAlign: 'center' }}>View query logs and feedback</span>
            </button>
          </div>
        ) : (
          <>
            {activeTab === 'user_settings' && (
              <>


        {view === 'list' && (
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto', marginTop: '16px', border: '1px solid #333', borderRadius: '8px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: '#ccc' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#222', zIndex: 1 }}>
                <tr style={{ borderBottom: '1px solid #444', textAlign: 'left' }}>
                  <th style={{ padding: '12px 8px' }}>Username</th>
                  <th style={{ padding: '12px 8px' }}>Roles</th>
                  <th style={{ padding: '12px 8px' }}>Type</th>
                  <th style={{ padding: '12px 8px' }}>Cost View</th>
                  <th style={{ padding: '12px 8px' }}>SQL View</th>
                  <th style={{ padding: '12px 8px' }}>Status</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} style={{ borderBottom: '1px solid #333' }}>
                    <td style={{ padding: '12px 8px' }}>{u.username}</td>
                    <td style={{ padding: '12px 8px' }}>{u.roles && u.roles.length > 0 ? u.roles.join(', ') : '-'}</td>
                    <td style={{ padding: '12px 8px' }}>{u.user_type === 1 ? 'Admin' : 'General'}</td>
                    <td style={{ padding: '12px 8px' }}>
                      {u.display_token ? <Check size={16} color="#86efac" /> : <XCircle size={16} color="#fca5a5" />}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      {u.display_sql ? <Check size={16} color="#86efac" /> : <XCircle size={16} color="#fca5a5" />}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <span style={{ 
                        padding: '4px 8px', 
                        borderRadius: '12px', 
                        fontSize: '0.75rem',
                        backgroundColor: (u.is_active !== false) ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        color: (u.is_active !== false) ? '#86efac' : '#fca5a5'
                      }}>
                        {(u.is_active !== false) ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                      <button 
                        onClick={() => openEdit(u)}
                        style={{ background: 'none', border: 'none', color: '#d97757', cursor: 'pointer', padding: '4px' }}
                        title="Edit User"
                      >
                        <Edit2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: '#888' }}>
                      No users found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {(view === 'create' || view === 'edit') && (
          <div style={{ flex: 1, overflowY: 'auto', width: '100%', paddingRight: '16px' }}>
            <form onSubmit={view === 'create' ? handleCreateUser : handleUpdateUser} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginTop: '8px', width: '100%' }}>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Username</label>
                  <input type="text" required value={formData.username} onChange={(e) => setFormData({...formData, username: e.target.value})} style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff', boxSizing: 'border-box' }} />
                </div>
                
                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>
                    Password {view === 'edit' && <span style={{ fontSize: '0.8rem', fontStyle: 'italic' }}>(Leave blank to keep current)</span>}
                  </label>
                  <input type="password" required={view === 'create'} value={formData.password} onChange={(e) => setFormData({...formData, password: e.target.value})} style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff', boxSizing: 'border-box' }} />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Access Type</label>
                  <select value={formData.user_type} onChange={(e) => setFormData({...formData, user_type: parseInt(e.target.value)})} style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff', boxSizing: 'border-box' }}>
                    <option value={2}>General User</option>
                    <option value={1}>Admin</option>
                  </select>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                  <input type="checkbox" id="display_token" checked={formData.display_token} onChange={(e) => setFormData({...formData, display_token: e.target.checked})} />
                  <label htmlFor="display_token" style={{ color: '#ccc', fontSize: '0.95rem' }}>Allow viewing Tokens & Cost</label>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <input type="checkbox" id="display_sql" checked={formData.display_sql} onChange={(e) => setFormData({...formData, display_sql: e.target.checked})} />
                  <label htmlFor="display_sql" style={{ color: '#ccc', fontSize: '0.95rem' }}>Allow viewing Generated SQL</label>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '6px', marginTop: '8px' }}>
                  <input type="checkbox" id="is_active" checked={formData.is_active} onChange={(e) => setFormData({...formData, is_active: e.target.checked})} />
                  <label htmlFor="is_active" style={{ color: '#ccc', fontSize: '0.95rem', fontWeight: 600 }}>Active Account</label>
                  <span style={{ color: '#888', fontSize: '0.8rem', marginLeft: 'auto' }}>If unchecked, user cannot log in</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Roles</label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '6px', flex: 1, overflowY: 'auto', minHeight: '150px' }}>
                    {roles.map(r => (
                      <div key={r.name} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input 
                          type="checkbox" 
                          id={`role_${r.name}`} 
                          checked={formData.roles.includes(r.name)}
                          onChange={(e) => {
                            const isChecked = e.target.checked;
                            setFormData(prev => ({
                              ...prev,
                              roles: isChecked 
                                ? [...prev.roles, r.name]
                                : prev.roles.filter(name => name !== r.name)
                            }));
                          }}
                        />
                        <label htmlFor={`role_${r.name}`} style={{ color: '#ccc', fontSize: '0.95rem' }}>{r.name}</label>
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Database Access</label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '6px', flex: 1, overflowY: 'auto', minHeight: '150px' }}>
                    {databases.map(db => (
                      <div key={db.id} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input 
                          type="checkbox" 
                          id={`db_${db.id}`} 
                          checked={formData.allowed_databases.includes(db.id)}
                          onChange={(e) => {
                            const isChecked = e.target.checked;
                            setFormData(prev => ({
                              ...prev,
                              allowed_databases: isChecked 
                                ? [...prev.allowed_databases, db.id]
                                : prev.allowed_databases.filter(id => id !== db.id)
                            }));
                          }}
                        />
                        <label htmlFor={`db_${db.id}`} style={{ color: '#ccc', fontSize: '0.95rem' }}>{db.name}</label>
                      </div>
                    ))}
                    {databases.length === 0 && <span style={{ color: '#888', fontSize: '0.85rem' }}>No databases configured.</span>}
                  </div>
                </div>
              </div>

              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
                <button type="submit" style={{ padding: '12px 24px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                  {view === 'create' ? 'Create User' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        )}
              </>
            )}

            {activeTab === 'db_settings' && (
              <>
        {view === 'db_list' && (
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto', marginTop: '16px', border: '1px solid #333', borderRadius: '8px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: '#ccc' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#222', zIndex: 1 }}>
                <tr style={{ borderBottom: '1px solid #444', textAlign: 'left' }}>
                  <th style={{ padding: '12px 8px' }}>Database Name</th>
                  <th style={{ padding: '12px 8px' }}>Connection String</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {databases.map(db => (
                  <tr key={db.id} style={{ borderBottom: '1px solid #333' }}>
                    <td style={{ padding: '12px 8px' }}>{db.name}</td>
                    <td style={{ padding: '12px 8px', wordBreak: 'break-all' }}>{db.connection_string}</td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                      <button 
                        onClick={() => {
                          setDbFormData({ name: db.name, connection_string: db.connection_string });
                          setEditingDbId(db.id);
                          setView('db_edit');
                          setStatus({ message: '', error: '' });
                        }}
                        style={{ background: 'none', border: 'none', color: '#d97757', cursor: 'pointer', padding: '4px' }}
                        title="Edit Database"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button 
                        onClick={() => handleDeleteDatabase(db.id)}
                        style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: '4px' }}
                        title="Delete Database"
                      >
                        <XCircle size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
                {databases.length === 0 && (
                  <tr>
                    <td colSpan={3} style={{ padding: '24px', textAlign: 'center', color: '#888' }}>
                      No databases found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {(view === 'db_create' || view === 'db_edit') && (
          <div style={{ flex: 1, overflowY: 'auto', width: '100%', paddingRight: '16px' }}>
            <form onSubmit={view === 'db_create' ? handleCreateDatabase : handleUpdateDatabase} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '8px', maxWidth: '600px', margin: '0 auto', width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Database Name</label>
              <input type="text" required value={dbFormData.name} onChange={(e) => setDbFormData({...dbFormData, name: e.target.value})} style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff', boxSizing: 'border-box' }} />
            </div>
            
            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Connection String</label>
              <input type="text" required value={dbFormData.connection_string} onChange={(e) => setDbFormData({...dbFormData, connection_string: e.target.value})} style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff', boxSizing: 'border-box' }} placeholder="e.g. Server=myServerAddress;Database=myDataBase;User Id=myUsername;Password=myPassword;" />
            </div>
            
            <button type="submit" style={{ padding: '12px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer', marginTop: '16px' }}>
              {view === 'db_create' ? 'Create Database' : 'Save Changes'}
            </button>
            </form>
          </div>
        )}
              </>
            )}

            {activeTab === 'logs' && (
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label style={{ color: '#aaa', fontSize: '0.9rem' }}>Start Date</label>
                <input 
                  type="date" 
                  value={logDates.start} 
                  onChange={e => setLogDates(prev => ({ ...prev, start: e.target.value }))}
                  style={{ padding: '8px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff' }}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label style={{ color: '#aaa', fontSize: '0.9rem' }}>End Date</label>
                <input 
                  type="date" 
                  value={logDates.end} 
                  onChange={e => setLogDates(prev => ({ ...prev, end: e.target.value }))}
                  style={{ padding: '8px', borderRadius: '6px', border: '1px solid #333', backgroundColor: '#0d0d0d', color: '#fff' }}
                />
              </div>
              <button 
                onClick={() => fetchLogs(1)}
                style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
              >
                Fetch Logs
              </button>
            </div>
            
            <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #333', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', color: '#ccc', fontSize: '0.9rem' }}>
                <thead style={{ position: 'sticky', top: 0, backgroundColor: '#222', zIndex: 1 }}>
                  <tr style={{ borderBottom: '1px solid #444', textAlign: 'left' }}>
                    <th style={{ padding: '12px 8px', whiteSpace: 'nowrap' }}>Date</th>
                    <th style={{ padding: '12px 8px', whiteSpace: 'nowrap' }}>User</th>
                    <th style={{ padding: '12px 8px' }}>Question</th>
                    <th style={{ padding: '12px 8px', whiteSpace: 'nowrap' }}>Rating</th>
                    <th style={{ padding: '12px 8px' }}>Comment</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map(log => (
                    <tr key={log.id} style={{ borderBottom: '1px solid #333' }}>
                      <td style={{ padding: '12px 8px', whiteSpace: 'nowrap' }}>{log.date ? new Date(log.date).toLocaleString() : '-'}</td>
                      <td style={{ padding: '12px 8px' }}>{log.user}</td>
                      <td style={{ padding: '12px 8px' }}>{log.question || '-'}</td>
                      <td style={{ padding: '12px 8px', textAlign: 'center' }}>{log.rating === true ? '👍' : (log.rating === false ? '👎' : '-')}</td>
                      <td style={{ padding: '12px 8px' }}>{log.comment || '-'}</td>
                    </tr>
                  ))}
                  {logs.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#888' }}>
                        No logs found in this date range.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '16px' }}>
              <div style={{ color: '#888', fontSize: '0.9rem' }}>
                Showing {logs.length} of {logsPagination.total} logs
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  disabled={logsPagination.page <= 1}
                  onClick={() => fetchLogs(logsPagination.page - 1)}
                  style={{ padding: '6px 12px', borderRadius: '4px', border: '1px solid #444', backgroundColor: 'transparent', color: logsPagination.page <= 1 ? '#555' : '#ccc', cursor: logsPagination.page <= 1 ? 'not-allowed' : 'pointer' }}
                >
                  Prev
                </button>
                <span style={{ color: '#ccc', fontSize: '0.9rem' }}>Page {logsPagination.page} of {Math.max(1, logsPagination.total_pages)}</span>
                <button
                  disabled={logsPagination.page >= logsPagination.total_pages}
                  onClick={() => fetchLogs(logsPagination.page + 1)}
                  style={{ padding: '6px 12px', borderRadius: '4px', border: '1px solid #444', backgroundColor: 'transparent', color: logsPagination.page >= logsPagination.total_pages ? '#555' : '#ccc', cursor: logsPagination.page >= logsPagination.total_pages ? 'not-allowed' : 'pointer' }}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
          </>
        )}
      </div>
    </div>
  );
}
