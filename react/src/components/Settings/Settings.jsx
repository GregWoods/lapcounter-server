import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { API_URL } from '../../endpoints.js';
import '../Admin/Admin.css';

// Installation-wide settings: stored once, not per meeting.
export default function Settings() {
    const [form, setForm] = useState(null);
    const [status, setStatus] = useState('');

    useEffect(() => {
        fetch(`${API_URL}/settings`)
            .then(r => r.json())
            .then(setForm)
            .catch(() => setStatus('Could not load settings'));
    }, []);

    const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

    const save = async (e) => {
        e.preventDefault();
        setStatus('Saving…');
        try {
            const res = await fetch(`${API_URL}/settings`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(form),
            });
            if (res.ok) {
                setForm(await res.json());
                setStatus('Saved');
            } else {
                const body = await res.json().catch(() => ({}));
                setStatus(body.detail || 'Save failed');
            }
        } catch {
            setStatus('Could not reach the server');
        }
    };

    return (
        <div className="admin-page">
            <div className="admin-header">
                <h1 className="admin-title">Settings</h1>
                <Link to="/meetings" className="admin-btn-ghost admin-btn-sm" style={{ textDecoration: 'none' }}><ArrowLeft size={16} /> All Meetings</Link>
            </div>
            {form && (
                <div className="admin-card">
                    <form className="admin-form" onSubmit={save}>
                        <h2 className="admin-card-title">WiFi (Welcome page QR code)</h2>
                        <div className="admin-form-row">
                            <label>Network name (SSID)</label>
                            <input value={form.wifi_ssid} onChange={set('wifi_ssid')} />
                        </div>
                        <div className="admin-form-row">
                            <label>Security</label>
                            <select value={form.wifi_security} onChange={set('wifi_security')}>
                                <option value="WPA">WPA / WPA2 / WPA3</option>
                                <option value="WEP">WEP</option>
                                <option value="nopass">Open (no password)</option>
                            </select>
                        </div>
                        {form.wifi_security !== 'nopass' && (
                            <div className="admin-form-row">
                                <label>Password</label>
                                <input value={form.wifi_password} onChange={set('wifi_password')} />
                            </div>
                        )}
                        <p className="admin-form-hint">Leave the network name blank to hide the WiFi QR code. The password is shown to anyone who opens the Welcome page.</p>
                        <h2 className="admin-card-title">Meeting link</h2>
                        <div className="admin-form-row">
                            <label>Public base URL (optional)</label>
                            <input
                                value={form.public_base_url}
                                onChange={set('public_base_url')}
                                placeholder="http://192.168.8.3:8088"
                            />
                        </div>
                        <p className="admin-form-hint">Used for the meeting QR code instead of the address this page was loaded from.</p>
                        <div className="admin-form-actions">
                            <span className="admin-form-hint">{status}</span>
                            <button type="submit" className="admin-btn-primary">Save</button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
}
