import { useState } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { House, LogOut } from 'lucide-react';
import { useAdminAuth } from '../../contexts/AdminAuthContext';
import '../Admin/Admin.css';

const API_URL = import.meta.env.VITE_API_URL;

function DriverForm({ initial, onSave, onCancel }) {
    const [form, setForm] = useState(initial || { first_name: '', last_name: '' });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const set = (field, value) => setForm(f => ({ ...f, [field]: value }));

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        try {
            await onSave(form);
        } catch (err) {
            setError(err.message);
            setSaving(false);
        }
    };

    return (
        <form className="admin-form" onSubmit={handleSubmit}>
            <div className="admin-form-row">
                <label>First name</label>
                <input value={form.first_name} onChange={e => set('first_name', e.target.value)} placeholder="Jake" required />
            </div>
            <div className="admin-form-row">
                <label>Last name</label>
                <input value={form.last_name || ''} onChange={e => set('last_name', e.target.value)} placeholder="Optional" />
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    );
}

const Drivers = () => {
    const { logout } = useAdminAuth();
    const loaderData = useLoaderData();
    const [drivers, setDrivers] = useState(loaderData || []);
    const [newOpen, setNewOpen] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [confirmDeleteId, setConfirmDeleteId] = useState(null);

    const reload = async () => {
        const res = await fetch(`${API_URL}/drivers/`);
        if (res.ok) setDrivers(await res.json());
    };

    const handleCreate = async (form) => {
        const res = await fetch(`${API_URL}/drivers/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...form, sit_out_next_race: false }),
        });
        if (!res.ok) throw new Error('Failed to create driver');
        await reload();
        setNewOpen(false);
    };

    const handleUpdate = async (id, form) => {
        const res = await fetch(`${API_URL}/drivers/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error('Failed to update driver');
        await reload();
        setEditingId(null);
    };

    const handleDelete = async (id) => {
        const res = await fetch(`${API_URL}/drivers/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete driver');
        await reload();
        setConfirmDeleteId(null);
    };

    const sorted = [...drivers].sort((a, b) =>
        a.first_name.localeCompare(b.first_name) || (a.last_name || '').localeCompare(b.last_name || '')
    );

    return (
        <div className="admin-page">
            <div className="admin-header">
                <div className="admin-header-left">
                    <Link to="/" className="home-icon-link"><House /></Link>
                    <h1 className="admin-title">Drivers</h1>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button className="admin-btn-ghost admin-btn-sm" onClick={logout} title="Lock admin">
                        <LogOut size={16} />
                    </button>
                    <button
                        className={newOpen ? 'admin-btn-ghost' : 'admin-btn-primary'}
                        onClick={() => { setNewOpen(v => !v); setEditingId(null); }}
                    >
                        {newOpen ? 'Cancel' : '+ New Driver'}
                    </button>
                </div>
            </div>

            {newOpen && (
                <div className="admin-card">
                    <h2 className="admin-card-title">New Driver</h2>
                    <DriverForm onSave={handleCreate} onCancel={() => setNewOpen(false)} />
                </div>
            )}

            {sorted.length === 0 && !newOpen && (
                <p className="admin-empty">No drivers yet. Create one above.</p>
            )}

            {sorted.map(driver => (
                <div key={driver.id} className="admin-card">
                    {editingId === driver.id ? (
                        <>
                            <h2 className="admin-card-title">Edit Driver</h2>
                            <DriverForm
                                initial={driver}
                                onSave={(form) => handleUpdate(driver.id, form)}
                                onCancel={() => setEditingId(null)}
                            />
                        </>
                    ) : (
                        <div className="admin-meeting-header">
                            <div className="admin-meeting-info">
                                <span className="admin-meeting-name">
                                    {[driver.first_name, driver.last_name].filter(Boolean).join(' ')}
                                </span>
                            </div>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                {confirmDeleteId === driver.id ? (
                                    <>
                                        <span style={{ color: '#888', fontSize: '0.85rem', alignSelf: 'center' }}>Delete?</span>
                                        <button className="admin-btn-primary admin-btn-sm" onClick={() => handleDelete(driver.id)}>Yes</button>
                                        <button className="admin-btn-ghost admin-btn-sm" onClick={() => setConfirmDeleteId(null)}>No</button>
                                    </>
                                ) : (
                                    <>
                                        <button
                                            className="admin-btn-ghost admin-btn-sm"
                                            onClick={() => { setEditingId(driver.id); setNewOpen(false); setConfirmDeleteId(null); }}
                                        >Edit</button>
                                        <button
                                            className="admin-btn-ghost admin-btn-sm"
                                            onClick={() => setConfirmDeleteId(driver.id)}
                                        >Delete</button>
                                    </>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
};

export default Drivers;
