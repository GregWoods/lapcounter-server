import { useState, useEffect } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { House, LogOut } from 'lucide-react';
import { useAdminAuth } from '../../contexts/AdminAuthContext';
import './Admin.css';

const API_URL = import.meta.env.VITE_API_URL ?? `http://${window.location.hostname}:8000`;

const SESSION_TYPES = ['Points', 'FastestLap', 'Championship'];
const END_CONDITIONS = ['Laps', 'Time', 'RacesPerDriver'];
const END_CONDITION_LABELS = { Laps: 'Laps', Time: 'Time', RacesPerDriver: 'Races per driver' };
const POINTS_SCORING_METHODS = ['LapPoints', 'PositionPoints'];
const FASTEST_LAP_SCORING_METHODS = ['FastestLap', 'AverageFastestLap'];

const SESSION_TYPE_LABELS = { Points: 'Points', FastestLap: 'Fastest Lap', Championship: 'Championship' };
const SCORING_METHOD_LABELS = {
    LapPoints: 'Lap Points',
    PositionPoints: 'Position Points',
    FastestLap: 'Personal best',
    AverageFastestLap: 'Average best per race',
};

const DEFAULT_SESSION = {
    session_type: 'Points',
    end_condition: 'Laps',
    end_condition_info: 20,
    scoring_method: 'PositionPoints',
    scoring_points: '10, 8, 6, 4, 3, 2, 1',
    start_time: '',
    end_time: '',
};

function parsePoints(str) {
    if (!str) return '';
    try {
        const parsed = JSON.parse(str);
        return Array.isArray(parsed) ? parsed.join(', ') : str;
    } catch {
        return str;
    }
}

function serializePoints(str) {
    if (!str || !str.trim()) return null;
    const nums = str.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n));
    return JSON.stringify(nums);
}

function MeetingForm({ initial, onSave, onCancel }) {
    const today = new Date().toISOString().slice(0, 10);
    const [form, setForm] = useState(initial || { name: '', date: today, venue: '', count_first_crossing: false });
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
            <div className="admin-form-row">
                <label>Count first crossing</label>
                <input type="checkbox" checked={!!form.count_first_crossing} onChange={e => set('count_first_crossing', e.target.checked)} />
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    );
}

function SessionForm({ initial, meetingId, onSave, onCancel }) {
    const [form, setForm] = useState(() => ({
        ...DEFAULT_SESSION,
        ...(initial ? {
            ...initial,
            scoring_points: parsePoints(initial.scoring_points),
            start_time: initial.start_time ? initial.start_time.slice(0, 5) : '',
            end_time: initial.end_time ? initial.end_time.slice(0, 5) : '',
        } : {}),
        meeting_id: meetingId,
    }));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const set = (field, value) => setForm(f => ({ ...f, [field]: value }));

    const isFastestLapSession = form.session_type === 'FastestLap';
    const availableScoringMethods = isFastestLapSession ? FASTEST_LAP_SCORING_METHODS : POINTS_SCORING_METHODS;

    const handleSessionTypeChange = (newType) => {
        const isFl = newType === 'FastestLap';
        const validMethods = isFl ? FASTEST_LAP_SCORING_METHODS : POINTS_SCORING_METHODS;
        setForm(f => ({
            ...f,
            session_type: newType,
            scoring_method: validMethods.includes(f.scoring_method) ? f.scoring_method : validMethods[0],
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        const payload = {
            ...form,
            scoring_points: form.scoring_method === 'PositionPoints' ? serializePoints(form.scoring_points) : null,
            start_time: form.start_time || null,
            end_time: form.end_time || null,
        };
        try {
            await onSave(payload);
        } catch (err) {
            setError(err.message);
            setSaving(false);
        }
    };

    return (
        <form className="admin-form admin-session-form" onSubmit={handleSubmit}>
            <div className="admin-form-row">
                <label>Type</label>
                <select value={form.session_type} onChange={e => handleSessionTypeChange(e.target.value)}>
                    {SESSION_TYPES.map(t => <option key={t} value={t}>{SESSION_TYPE_LABELS[t]}</option>)}
                </select>
            </div>
            <div className="admin-form-row">
                <label>End condition</label>
                <select value={form.end_condition} onChange={e => set('end_condition', e.target.value)}>
                    {END_CONDITIONS.map(c => <option key={c} value={c}>{END_CONDITION_LABELS[c] || c}</option>)}
                </select>
            </div>
            <div className="admin-form-row">
                <label>{form.end_condition === 'Laps' ? 'Laps' : form.end_condition === 'Time' ? 'Minutes' : 'Races per driver'}</label>
                <input
                    type="number"
                    value={form.end_condition_info || ''}
                    onChange={e => set('end_condition_info', parseInt(e.target.value) || null)}
                    min="1"
                />
            </div>
            <div className="admin-form-row">
                <label>{isFastestLapSession ? 'Ranking' : 'Scoring method'}</label>
                <select value={form.scoring_method} onChange={e => set('scoring_method', e.target.value)}>
                    {availableScoringMethods.map(m => <option key={m} value={m}>{SCORING_METHOD_LABELS[m]}</option>)}
                </select>
            </div>
            {form.scoring_method === 'PositionPoints' && (
                <div className="admin-form-row">
                    <label>Points per position</label>
                    <input
                        value={form.scoring_points || ''}
                        onChange={e => set('scoring_points', e.target.value)}
                        placeholder="10, 8, 6, 4, 3, 2, 1"
                    />
                </div>
            )}
            <div className="admin-form-row">
                <label>Start time</label>
                <input type="time" value={form.start_time || ''} onChange={e => set('start_time', e.target.value)} />
            </div>
            <div className="admin-form-row">
                <label>End time</label>
                <input type="time" value={form.end_time || ''} onChange={e => set('end_time', e.target.value)} />
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    );
}

function formatDiff(seconds) {
    if (seconds < 5)    return 'In sync';
    if (seconds < 60)   return `${seconds}s off`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m off`;
    return `${Math.round(seconds / 3600)}h off`;
}

function ClockSync() {
    const [piTs, setPiTs] = useState(null);
    const [fetchedAt, setFetchedAt] = useState(null);
    const [syncing, setSyncing] = useState(false);
    const [synced, setSynced] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetch(`${API_URL}/admin/clock`)
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data) { setPiTs(data.timestamp); setFetchedAt(Date.now()); } })
            .catch(() => {});
    }, []);

    if (!piTs) return null;

    const estimatedPiNow = piTs + (Date.now() - fetchedAt) / 1000;
    const absDiff = Math.round(Math.abs(Date.now() / 1000 - estimatedPiNow));
    const inSync = absDiff < 5;

    const handleSync = async () => {
        setSyncing(true);
        setError(null);
        try {
            const now = Date.now() / 1000;
            const res = await fetch(`${API_URL}/admin/sync-clock`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp: now }),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || 'Sync failed');
            }
            setPiTs(now);
            setFetchedAt(Date.now());
            setSynced(true);
        } catch (err) {
            setError(err.message);
        } finally {
            setSyncing(false);
        }
    };

    return (
        <div className="admin-card">
            <h2 className="admin-card-title">System Clock</h2>
            <div className="admin-clock-row">
                <div className="admin-clock-col">
                    <span className="admin-clock-label">Pi</span>
                    <span className="admin-clock-time">{new Date(estimatedPiNow * 1000).toLocaleTimeString()}</span>
                </div>
                <div className="admin-clock-col">
                    <span className="admin-clock-label">This device</span>
                    <span className="admin-clock-time">{new Date().toLocaleTimeString()}</span>
                </div>
                <div className="admin-clock-col">
                    <span className="admin-clock-label">Difference</span>
                    <span className={`admin-clock-time ${inSync ? 'admin-clock-ok' : 'admin-clock-warn'}`}>
                        {formatDiff(absDiff)}
                    </span>
                </div>
                <button
                    className={synced ? 'admin-btn-ghost' : 'admin-btn-primary'}
                    onClick={handleSync}
                    disabled={syncing || synced || inSync}
                >
                    {syncing ? 'Syncing…' : synced ? 'Synced ✓' : 'Sync to this device'}
                </button>
            </div>
            {error && <p className="admin-error" style={{ marginTop: '12px' }}>{error}</p>}
        </div>
    );
}

const Admin = () => {
    const { logout } = useAdminAuth();
    const loaderData = useLoaderData();
    const [meetings, setMeetings] = useState(loaderData?.meetings || []);
    const activeMeetingId = loaderData?.activeMeetingId ?? null;
    const [newMeetingOpen, setNewMeetingOpen] = useState(false);
    const [editingMeetingId, setEditingMeetingId] = useState(null);
    const [addingSessionTo, setAddingSessionTo] = useState(null);
    const [editingSessionId, setEditingSessionId] = useState(null);
    const [endingSessionId, setEndingSessionId] = useState(null);
    const [endingLoading, setEndingLoading] = useState(false);
    const [endingError, setEndingError] = useState(null);

    const reloadAll = async () => {
        const res = await fetch(`${API_URL}/meetings`);
        if (!res.ok) return;
        const allMeetings = await res.json();
        const withSessions = await Promise.all(
            allMeetings.map(async m => {
                const sr = await fetch(`${API_URL}/sessions?meeting_id=${m.id}`);
                return { ...m, sessions: sr.ok ? await sr.json() : [] };
            })
        );
        setMeetings(withSessions);
    };

    const handleEndSession = async () => {
        setEndingLoading(true);
        setEndingError(null);
        try {
            const res = await fetch(`${API_URL}/sessions/${endingSessionId}/finish`, { method: 'POST' });
            if (!res.ok) throw new Error('Failed to end session');
            await reloadAll();
            setEndingSessionId(null);
        } catch (err) {
            setEndingError(err.message);
        } finally {
            setEndingLoading(false);
        }
    };

    const handleCreateMeeting = async (form) => {
        const res = await fetch(`${API_URL}/meetings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error('Failed to create meeting');
        const newMeeting = await res.json();
        setMeetings(prev => [...prev, { ...newMeeting, sessions: [] }]);
        setNewMeetingOpen(false);
    };

    const handleUpdateMeeting = async (id, form) => {
        const res = await fetch(`${API_URL}/meetings/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error('Failed to update meeting');
        await reloadAll();
        setEditingMeetingId(null);
    };

    const handleCreateSession = async (meetingId, form) => {
        const res = await fetch(`${API_URL}/sessions/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error('Failed to create session');
        await reloadAll();
        setAddingSessionTo(null);
    };

    const handleUpdateSession = async (sessionId, meetingId, form) => {
        // Strip fields that shouldn't be patched (state is system-managed)
        // eslint-disable-next-line no-unused-vars
        const { meeting_id, state, ...updateFields } = form;
        const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateFields),
        });
        if (!res.ok) throw new Error('Failed to update session');
        await reloadAll();
        setEditingSessionId(null);
    };

    return (
        <div className="admin-page">
            <div className="admin-header">
                <div className="admin-header-left">
                    <Link to="/" className="home-icon-link"><House /></Link>
                    <h1 className="admin-title">Race Meetings</h1>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button className="admin-btn-ghost admin-btn-sm" onClick={logout} title="Lock admin">
                        <LogOut size={16} />
                    </button>
                    <button
                        className={newMeetingOpen ? 'admin-btn-ghost' : 'admin-btn-primary'}
                        onClick={() => { setNewMeetingOpen(v => !v); setEditingMeetingId(null); }}
                    >
                        {newMeetingOpen ? 'Cancel' : '+ New Meeting'}
                    </button>
                </div>
            </div>

            <ClockSync />

            {newMeetingOpen && (
                <div className="admin-card">
                    <h2 className="admin-card-title">New Meeting</h2>
                    <MeetingForm onSave={handleCreateMeeting} onCancel={() => setNewMeetingOpen(false)} />
                </div>
            )}

            {meetings.length === 0 && !newMeetingOpen && (
                <p className="admin-empty">No meetings yet. Create one above.</p>
            )}

            {[...meetings].sort((a, b) => b.date.localeCompare(a.date)).map(meeting => (
                <div key={meeting.id} className="admin-card">
                    {editingMeetingId === meeting.id ? (
                        <>
                            <h2 className="admin-card-title">Edit Meeting</h2>
                            <MeetingForm
                                initial={meeting}
                                onSave={(form) => handleUpdateMeeting(meeting.id, form)}
                                onCancel={() => setEditingMeetingId(null)}
                            />
                        </>
                    ) : (
                        <div className="admin-meeting-header">
                            <div className="admin-meeting-info">
                                <span className="admin-meeting-name">
                                    {meeting.name}
                                    {meeting.id === activeMeetingId && <span className="admin-active-badge">Active</span>}
                                </span>
                                <span className="admin-meeting-meta">
                                    {meeting.date}
                                    {meeting.venue && ` · ${meeting.venue}`}
                                    {meeting.count_first_crossing && ' · Count first crossing'}
                                </span>
                            </div>
                            <button
                                className="admin-btn-ghost admin-btn-sm"
                                onClick={() => { setEditingMeetingId(meeting.id); setNewMeetingOpen(false); }}
                            >
                                Edit
                            </button>
                        </div>
                    )}

                    <div className="admin-sessions">
                        <h3 className="admin-sessions-title">Sessions</h3>

                        {(meeting.sessions || []).length === 0 && addingSessionTo !== meeting.id && (
                            <p className="admin-sessions-empty">No sessions — add one below.</p>
                        )}

                        {(meeting.sessions || []).map(session => (
                            <div key={session.id} className="admin-session-row">
                                {editingSessionId === session.id ? (
                                    <SessionForm
                                        initial={session}
                                        meetingId={meeting.id}
                                        onSave={(form) => handleUpdateSession(session.id, meeting.id, form)}
                                        onCancel={() => setEditingSessionId(null)}
                                    />
                                ) : (
                                    <div className="admin-session-display">
                                        <span className="admin-session-type">{SESSION_TYPE_LABELS[session.session_type] || session.session_type}</span>
                                        <span className="admin-session-detail">
                                            {session.end_condition_info}&nbsp;{session.end_condition === 'Laps' ? 'laps' : session.end_condition === 'Time' ? 'min' : 'races/driver'}
                                        </span>
                                        <span className="admin-session-detail">
                                            {SCORING_METHOD_LABELS[session.scoring_method] || session.scoring_method || '—'}
                                        </span>
                                        {session.start_time && (
                                            <span className="admin-session-detail">{session.start_time.slice(0, 5)}</span>
                                        )}
                                        {session.state === 'InProgress' ? (
                                            <button
                                                className="admin-session-state admin-session-state--inprogress admin-session-state--end-btn"
                                                onClick={() => { setEndingSessionId(session.id); setEndingError(null); }}
                                                title="End this session"
                                            >
                                                In Progress
                                            </button>
                                        ) : (
                                            <span className={`admin-session-state admin-session-state--${(session.state || 'notstarted').toLowerCase().replace(' ', '')}`}>
                                                {session.state || 'NotStarted'}
                                            </span>
                                        )}
                                        {['Finished', 'InProgress'].includes(session.state) ? (
                                            <Link to={`/results/${session.id}`} className="admin-btn-ghost admin-btn-sm" style={{ textDecoration: 'none' }}>
                                                Results
                                            </Link>
                                        ) : (
                                            <button
                                                className="admin-btn-ghost admin-btn-sm"
                                                onClick={() => { setEditingSessionId(session.id); setAddingSessionTo(null); }}
                                            >
                                                Edit
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}

                        {addingSessionTo === meeting.id ? (
                            <div className="admin-session-row">
                                <SessionForm
                                    meetingId={meeting.id}
                                    onSave={(form) => handleCreateSession(meeting.id, form)}
                                    onCancel={() => setAddingSessionTo(null)}
                                />
                            </div>
                        ) : (
                            <button
                                className="admin-btn-add-session"
                                onClick={() => { setAddingSessionTo(meeting.id); setEditingSessionId(null); }}
                            >
                                + Add Session
                            </button>
                        )}
                    </div>
                </div>
            ))}

            {endingSessionId && (
                <div className="admin-modal-overlay" onClick={() => setEndingSessionId(null)}>
                    <div className="admin-modal" onClick={e => e.stopPropagation()}>
                        <p className="admin-modal-title">End this session?</p>
                        <p className="admin-modal-body">
                            The session will be marked Finished. If there is a next session queued, it will become In Progress.
                        </p>
                        {endingError && <p className="admin-error">{endingError}</p>}
                        <div className="admin-modal-actions">
                            <button className="admin-btn-ghost" onClick={() => setEndingSessionId(null)}>Cancel</button>
                            <button className="admin-btn-primary" onClick={handleEndSession} disabled={endingLoading}>
                                {endingLoading ? 'Ending…' : 'End Session'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Admin;
