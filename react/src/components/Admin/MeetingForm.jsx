import { useState } from 'react';
import './Admin.css';

export default function MeetingForm({ initial, onSave, onCancel }) {
    const today = new Date().toISOString().slice(0, 10);
    const [form, setForm] = useState(initial || { name: '', date: today, venue: '' });
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
                <label>Name</label>
                <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="Village Hall Grand Prix" required />
            </div>
            <div className="admin-form-row">
                <label>Date</label>
                <input type="date" value={form.date} onChange={e => set('date', e.target.value)} required />
            </div>
            <div className="admin-form-row">
                <label>Venue</label>
                <input value={form.venue || ''} onChange={e => set('venue', e.target.value)} placeholder="Optional" />
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
        </form>
    );
}
