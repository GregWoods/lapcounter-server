import { useState } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { House, LogOut, ChevronDown, ChevronRight } from 'lucide-react';
import { useAdminAuth } from '../../contexts/AdminAuthContext';
import './Admin.css';

const API_URL = import.meta.env.VITE_API_URL ?? `http://${window.location.hostname}:8000`;

// Race types offered in the session form. 'Points' = Finishing Position (race ends on
// laps, scored by position); 'FastestLap' = Fastest Lap (race ends on time, personal best).
const RACE_TYPES = ['Points', 'FastestLap'];
const SESSION_TYPE_LABELS = { Points: 'Finishing Position', FastestLap: 'Fastest Lap', Championship: 'Championship' };

const DEFAULT_LAPS = 20;
const DEFAULT_MINUTES = 5;
const DEFAULT_RACES_PER_DRIVER = 3;
const DEFAULT_POINTS = '10, 8, 6, 4, 3, 2';

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
        session_type: initial?.session_type ?? 'Points',
        end_condition_info: initial?.end_condition_info ?? DEFAULT_LAPS,
        races_per_driver: initial?.races_per_driver ?? DEFAULT_RACES_PER_DRIVER,
        scoring_points: initial ? parsePoints(initial.scoring_points) : DEFAULT_POINTS,
    }));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const set = (field, value) => setForm(f => ({ ...f, [field]: value }));

    const isFastestLap = form.session_type === 'FastestLap';

    const handleSessionTypeChange = (newType) => {
        setForm(f => ({
            ...f,
            session_type: newType,
            end_condition_info: newType === 'FastestLap' ? DEFAULT_MINUTES : DEFAULT_LAPS,
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        const payload = {
            meeting_id: meetingId,
            session_type: form.session_type,
            // 'Laps' for Finishing Position races, 'Time' for Fastest Lap races.
            end_condition: isFastestLap ? 'Time' : 'Laps',
            end_condition_info: form.end_condition_info || null,
            races_per_driver: form.races_per_driver || null,
            scoring_method: isFastestLap ? 'FastestLap' : 'PositionPoints',
            scoring_points: isFastestLap ? null : serializePoints(form.scoring_points),
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
                <label>Race Type</label>
                <select value={form.session_type} onChange={e => handleSessionTypeChange(e.target.value)}>
                    {RACE_TYPES.map(t => <option key={t} value={t}>{SESSION_TYPE_LABELS[t]}</option>)}
                </select>
            </div>
            <div className="admin-form-row">
                <label>{isFastestLap ? 'Race Time (minutes)' : 'Race Laps'}</label>
                <input
                    type="number"
                    value={form.end_condition_info || ''}
                    onChange={e => set('end_condition_info', parseInt(e.target.value) || null)}
                    min="1"
                />
            </div>
            {!isFastestLap && (
                <div className="admin-form-row">
                    <label>Points scoring</label>
                    <input
                        value={form.scoring_points || ''}
                        onChange={e => set('scoring_points', e.target.value)}
                        placeholder={DEFAULT_POINTS}
                    />
                </div>
            )}
            <div className="admin-form-row">
                <label>Session ends after</label>
                <div className="admin-form-inline">
                    <input
                        className="admin-input-narrow"
                        type="number"
                        value={form.races_per_driver || ''}
                        onChange={e => set('races_per_driver', parseInt(e.target.value) || null)}
                        min="1"
                    />
                    <span className="admin-form-suffix">races per driver</span>
                </div>
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
            </div>
        </form>
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
    // undefined = follow default (expand the in-progress meeting, else the latest);
    // a meeting id pins that one open; null collapses everything.
    const [expandedMeetingId, setExpandedMeetingId] = useState(undefined);

    const meetingsSorted = [...meetings].sort((a, b) => b.date.localeCompare(a.date));
    const inProgressMeeting = meetingsSorted.find(m => (m.sessions || []).some(s => s.state === 'InProgress'));
    const defaultExpandedId = inProgressMeeting?.id ?? meetingsSorted[0]?.id ?? null;
    const effectiveExpandedId = expandedMeetingId === undefined ? defaultExpandedId : expandedMeetingId;
    const toggleMeeting = (id) =>
        setExpandedMeetingId(prev => {
            const current = prev === undefined ? defaultExpandedId : prev;
            return current === id ? null : id;
        });

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

            {newMeetingOpen && (
                <div className="admin-card">
                    <h2 className="admin-card-title">New Meeting</h2>
                    <MeetingForm onSave={handleCreateMeeting} onCancel={() => setNewMeetingOpen(false)} />
                </div>
            )}

            {meetings.length === 0 && !newMeetingOpen && (
                <p className="admin-empty">No meetings yet. Create one above.</p>
            )}

            {meetingsSorted.map(meeting => {
                const isExpanded = effectiveExpandedId === meeting.id;
                const isEditing = editingMeetingId === meeting.id;
                return (
                <div key={meeting.id} className="admin-card">
                    {isEditing ? (
                        <>
                            <h2 className="admin-card-title">Edit Meeting</h2>
                            <MeetingForm
                                initial={meeting}
                                onSave={(form) => handleUpdateMeeting(meeting.id, form)}
                                onCancel={() => setEditingMeetingId(null)}
                            />
                        </>
                    ) : (
                        <div
                            className="admin-meeting-header admin-meeting-header--toggle"
                            onClick={() => toggleMeeting(meeting.id)}
                        >
                            <span className="admin-collapse-chevron">
                                {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                            </span>
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
                                onClick={(e) => { e.stopPropagation(); setEditingMeetingId(meeting.id); setNewMeetingOpen(false); }}
                            >
                                Edit
                            </button>
                        </div>
                    )}

                    {(isExpanded || isEditing) && (
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
                                        {session.state === 'InProgress' && (
                                            <span className="admin-session-badge">In Progress</span>
                                        )}
                                        <span className="admin-session-detail">
                                            {session.end_condition_info}&nbsp;{session.end_condition === 'Time' ? 'min' : 'laps'}
                                        </span>
                                        {session.races_per_driver != null && (
                                            <span className="admin-session-detail">{session.races_per_driver} races/driver</span>
                                        )}
                                        <div className="admin-session-actions">
                                            {session.state === 'InProgress' && (
                                                <button
                                                    className="admin-btn-ghost admin-btn-sm admin-end-session-btn"
                                                    onClick={() => { setEndingSessionId(session.id); setEndingError(null); }}
                                                    title="End this session"
                                                >
                                                    End Session
                                                </button>
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
                    )}
                </div>
                );
            })}

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
