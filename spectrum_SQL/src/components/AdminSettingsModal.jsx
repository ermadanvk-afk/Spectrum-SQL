import React, { useState, useEffect } from 'react';
import { X, UserPlus, Shield, Edit2, Check, XCircle } from 'lucide-react';

export default function AdminSettingsModal({ onClose, apiFetch }) {
  const [view, setView] = useState('list'); // 'list', 'create', 'edit'
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([{ name: 'Purchase Manager' }]);
  const [databases, setDatabases] = useState([]);
  const [status, setStatus] = useState({ message: '', error: '' });
  
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
        padding: '32px',
        borderRadius: '12px',
        border: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        width: '100%',
        maxWidth: view === 'list' ? '900px' : '450px',
        maxHeight: '90vh',
        position: 'relative',
        overflowY: 'auto'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #333', paddingBottom: '16px', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Shield size={28} style={{ color: '#d97757' }} />
            <h2 style={{ color: '#eee', margin: 0, fontWeight: 600 }}>
              {view === 'list' && 'User Master'}
              {view === 'create' && 'Create New User'}
              {view === 'edit' && 'Edit User'}
              {view === 'db_list' && 'Database Master'}
              {view === 'db_create' && 'Create New Database'}
              {view === 'db_edit' && 'Edit Database'}
            </h2>
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            {view === 'list' && (
              <>
                <button 
                  onClick={() => { setView('db_list'); setStatus({ message: '', error: '' }); }}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #444', backgroundColor: 'transparent', color: '#ccc', cursor: 'pointer' }}
                >
                  Manage Databases
                </button>
                <button 
                  onClick={openCreate}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
                >
                  <UserPlus size={16} /> New User
                </button>
              </>
            )}
            
            {view === 'db_list' && (
              <>
                <button 
                  onClick={() => { setView('list'); setStatus({ message: '', error: '' }); }}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #444', backgroundColor: 'transparent', color: '#ccc', cursor: 'pointer' }}
                >
                  Manage Users
                </button>
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
              </>
            )}

            {(view === 'create' || view === 'edit') && (
              <button 
                onClick={() => { setView('list'); setStatus({ message: '', error: '' }); }}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #444', backgroundColor: 'transparent', color: '#ccc', cursor: 'pointer' }}
              >
                Back to List
              </button>
            )}
            
            {(view === 'db_create' || view === 'db_edit') && (
              <button 
                onClick={() => { setView('db_list'); setStatus({ message: '', error: '' }); }}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #444', backgroundColor: 'transparent', color: '#ccc', cursor: 'pointer' }}
              >
                Back to Databases
              </button>
            )}
            <button 
              onClick={onClose}
              style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '4px' }}
              title="Close"
            >
              <X size={24} />
            </button>
          </div>
        </div>
        
        {status.error && <div style={{ padding: '10px', backgroundColor: 'rgba(239,68,68,0.1)', color: '#fca5a5', borderRadius: '6px', fontSize: '0.85rem' }}>{status.error}</div>}
        {status.message && <div style={{ padding: '10px', backgroundColor: 'rgba(34,197,94,0.1)', color: '#86efac', borderRadius: '6px', fontSize: '0.85rem' }}>{status.message}</div>}

        {view === 'list' && (
          <div style={{ overflowX: 'auto', marginTop: '16px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: '#ccc' }}>
              <thead>
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
          <form onSubmit={view === 'create' ? handleCreateUser : handleUpdateUser} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '8px' }}>
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
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Roles</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '6px', maxHeight: '150px', overflowY: 'auto' }}>
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

            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.9rem', color: '#aaa' }}>Database Access</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '6px', maxHeight: '150px', overflowY: 'auto' }}>
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
            
            <button type="submit" style={{ padding: '12px', borderRadius: '6px', border: 'none', backgroundColor: '#d97757', color: '#fff', fontWeight: 600, cursor: 'pointer', marginTop: '16px' }}>
              {view === 'create' ? 'Create User' : 'Save Changes'}
            </button>
          </form>
        )}

        {view === 'db_list' && (
          <div style={{ overflowX: 'auto', marginTop: '16px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: '#ccc' }}>
              <thead>
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
          <form onSubmit={view === 'db_create' ? handleCreateDatabase : handleUpdateDatabase} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '8px' }}>
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
        )}
      </div>
    </div>
  );
}
