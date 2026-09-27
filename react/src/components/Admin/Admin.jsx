import { useRef, useState } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { House, LogOut, ChevronDown, ChevronRight, Timer, Trophy } from 'lucide-react';
import { useAdminAuth } from '../../contexts/adminAuth';
import MqttSubscriber from '../MqttSubscriber.jsx';
import './Admin.css';
import { API_URL, MQTT_URL } from '../../endpoints.js';


// Race types offered in the session form. 'Points' = Finishing Position (race ends on
// laps, scored by position); 'FastestLap' = Fastest Lap (race ends on time, personal best).
const RACE_TYPES = ['Points', 'FastestLap'];
const SESSION_TYPE_LABELS = { Points: 'Finishing Position', FastestLap: 'Fastest Lap', Championship: 'Championship' };

// Fastest Lap → stopwatch; Finishing Position (and anything else) → trophy.
function SessionTypeIcon({ type }) {
    return type === 'FastestLap' ? <Timer size={26} /> : <Trophy size={26} />;
}

const DEFAULT_LAPS = 20;
const DEFAULT_MINUTES = 5;
const DEFAULT_RACES_PER_DRIVER = 3;
const DEFAULT_MAX_SIT_OUTS = 2;
const DEFAULT_YELLOW_GRACE_SECONDS = 5;
const DEFAULT_YELLOW_LAP_PENALTY_LAPS = 1;
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
                <label>Start grid</label>
                <div className="admin-form-choice">
                    <label className="admin-checkbox">
                        <input type="checkbox" checked={!!form.count_first_crossing} onChange={e => set('count_first_crossing', e.target.checked)} />
                        <span>First crossing counts as lap 1</span>
                    </label>
                    <p className="admin-form-hint">
                        Tick when the finish line is <strong>behind</strong> the grid, so cars run almost a
                        full lap to reach it. Leave unticked when the line sits <strong>just ahead of</strong> the
                        grid: that first crossing isn&apos;t a lap, so it is discarded. Lap 1 is timed from
                        lights-out either way.
                    </p>
                </div>
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
        </form>
    );
}

function SessionForm({ initial, meetingId, onSave, onCancel, hasPowerControl }) {
    const [form, setForm] = useState(() => ({
        session_type: initial?.session_type ?? 'Points',
        end_condition_info: initial?.end_condition_info ?? DEFAULT_LAPS,
        races_per_driver: initial?.races_per_driver ?? DEFAULT_RACES_PER_DRIVER,
        max_sit_outs: initial?.max_sit_outs ?? DEFAULT_MAX_SIT_OUTS,
        yellow_grace_seconds: initial?.yellow_grace_seconds ?? DEFAULT_YELLOW_GRACE_SECONDS,
        yellow_grace_power_pct: initial?.yellow_grace_power_pct ?? 100,
        yellow_post_grace_power_pct: initial?.yellow_post_grace_power_pct ?? 0,
        yellow_lap_penalty_laps: initial?.yellow_lap_penalty_laps ?? DEFAULT_YELLOW_LAP_PENALTY_LAPS,
        scoring_points: initial ? parsePoints(initial.scoring_points) : DEFAULT_POINTS,
    }));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const set = (field, value) => setForm(f => ({ ...f, [field]: value }));

    const isFastestLap = form.session_type === 'FastestLap';
    // Null means no sit-out limit — the "Sit-out penalty" toggle is just a friendlier
    // face on that same nullability, rather than a separate field.
    const sitOutPenaltyEnabled = form.max_sit_outs != null;
    const handleSitOutPenaltyToggle = (checked) => {
        set('max_sit_outs', checked ? (initial?.max_sit_outs ?? DEFAULT_MAX_SIT_OUTS) : null);
    };

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
            max_sit_outs: form.max_sit_outs || null,
            yellow_grace_seconds: form.yellow_grace_seconds || DEFAULT_YELLOW_GRACE_SECONDS,
            // Locked server-side-safe regardless of what's in React state — the power
            // fields are hidden rather than cleared when there's no power control, so
            // stale form state could still carry a value, and the running Layer 1 could
            // in principle change between opening this form and saving it. Without power
            // control, the percentages can only ever be 100 (nothing can enforce less),
            // and the lap penalty is Finishing Position sessions only.
            yellow_grace_power_pct: hasPowerControl ? (form.yellow_grace_power_pct ?? 100) : 100,
            yellow_post_grace_power_pct: hasPowerControl ? (form.yellow_post_grace_power_pct ?? 0) : 100,
            yellow_lap_penalty_laps: (!hasPowerControl && !isFastestLap)
                ? (form.yellow_lap_penalty_laps || DEFAULT_YELLOW_LAP_PENALTY_LAPS) : 0,
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
                <label>Race type</label>
                <select value={form.session_type} onChange={e => handleSessionTypeChange(e.target.value)}>
                    {RACE_TYPES.map(t => <option key={t} value={t}>{SESSION_TYPE_LABELS[t]}</option>)}
                </select>
            </div>
            <div className="admin-form-row">
                <label>{isFastestLap ? 'Duration' : 'Race laps'}</label>
                <div className="admin-form-inline-value">
                    <input
                        className="admin-input-narrow"
                        type="number"
                        value={form.end_condition_info || ''}
                        onChange={e => set('end_condition_info', parseInt(e.target.value) || null)}
                        min="1"
                    />
                    <span className="admin-form-unit">{isFastestLap ? 'min' : 'laps'}</span>
                </div>
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
                <label>Races per driver</label>
                <input
                    className="admin-input-narrow"
                    type="number"
                    value={form.races_per_driver || ''}
                    onChange={e => set('races_per_driver', parseInt(e.target.value) || null)}
                    min="1"
                />
            </div>
            <div className="admin-form-row">
                <label>Sit-out penalty</label>
                <label className="admin-toggle">
                    <input
                        type="checkbox"
                        checked={sitOutPenaltyEnabled}
                        onChange={e => handleSitOutPenaltyToggle(e.target.checked)}
                    />
                    <span className="admin-toggle-track"><span className="admin-toggle-thumb" /></span>
                </label>
            </div>
            {sitOutPenaltyEnabled && (
                <div className="admin-form-field-group">
                    <div className="admin-form-row">
                        <label>Max sit-outs</label>
                        <input
                            className="admin-input-narrow"
                            type="number"
                            value={form.max_sit_outs || ''}
                            onChange={e => set('max_sit_outs', parseInt(e.target.value) || null)}
                            min="1"
                        />
                    </div>
                    <p className="admin-form-hint">Driver is disqualified from the session after this many sit-outs.</p>
                </div>
            )}
            <div className="admin-form-section">
                <h4 className="admin-form-section-title">Yellow Flag</h4>
                <div className="admin-form-row">
                    <label>Grace period</label>
                    <div className="admin-form-inline-value">
                        <input
                            className="admin-input-narrow"
                            type="number"
                            value={form.yellow_grace_seconds || ''}
                            onChange={e => set('yellow_grace_seconds', parseInt(e.target.value) || null)}
                            min="1"
                        />
                        <span className="admin-form-unit">s</span>
                    </div>
                </div>
                {hasPowerControl && (
                    <>
                        <div className="admin-form-row">
                            <label>Max power during grace</label>
                            <div className="admin-form-inline-value">
                                <input
                                    className="admin-input-narrow"
                                    type="number"
                                    value={form.yellow_grace_power_pct ?? ''}
                                    onChange={e => set('yellow_grace_power_pct', parseInt(e.target.value) || 0)}
                                    min="0"
                                    max="100"
                                />
                                <span className="admin-form-unit">%</span>
                            </div>
                        </div>
                        <div className="admin-form-row">
                            <label>Max power after grace</label>
                            <div className="admin-form-inline-value">
                                <input
                                    className="admin-input-narrow"
                                    type="number"
                                    value={form.yellow_post_grace_power_pct ?? ''}
                                    onChange={e => set('yellow_post_grace_power_pct', parseInt(e.target.value) || 0)}
                                    min="0"
                                    max="100"
                                />
                                <span className="admin-form-unit">%</span>
                            </div>
                        </div>
                    </>
                )}
                {!hasPowerControl && !isFastestLap && (
                    <div className="admin-form-field-group">
                        <div className="admin-form-row">
                            <label>Penalty</label>
                            <div className="admin-form-inline-value">
                                <input
                                    className="admin-input-narrow"
                                    type="number"
                                    value={form.yellow_lap_penalty_laps || ''}
                                    onChange={e => set('yellow_lap_penalty_laps', parseInt(e.target.value) || null)}
                                    min="1"
                                />
                                <span className="admin-form-unit">laps</span>
                            </div>
                        </div>
                        <p className="admin-form-hint">Added to a driver&apos;s lap count for crossing the line after the grace period expires.</p>
                    </div>
                )}
            </div>
            {error && <p className="admin-error">{error}</p>}
            <div className="admin-form-actions">
                <button type="button" className="admin-btn-ghost" onClick={onCancel}>Cancel</button>
                <button type="submit" className="admin-btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
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

    // Queries are HTTP, events are MQTT: a session create/finish here changes what
    // /racecontrol should show (Next Session availability, "Session complete"), but
    // Admin only talks to the API, so nothing tells a /racecontrol tab already open
    // elsewhere. admin_update is a plain "something changed, re-fetch" ping — deliberately
    // not race_control, which is lapdata/BLE's command channel, not a browser-to-browser
    // UI-refresh signal. RaceControl.jsx just calls its own loadInfo() on receipt.
    const mqttClientRef = useRef(null);
    const publishAdminUpdate = (reason, extra = {}) => {
        mqttClientRef.current?.publish('admin_update', JSON.stringify({ reason, ...extra }));
    };

    // null = no layer1_status seen yet. Treated the same as "no power control" for
    // gating the session form's power-percentage fields — the form must never let an
    // operator set a percentage that silently does nothing, so "unknown" defaults to
    // the safe, locked state rather than briefly showing the fields as editable.
    const [layer1Capabilities, setLayer1Capabilities] = useState(null);
    const hasPowerControl = !!layer1Capabilities?.includes('power_control');

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
            publishAdminUpdate('session_finished', { session_id: endingSessionId });
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
        publishAdminUpdate('session_created', { meeting_id: meetingId });
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
            <MqttSubscriber
                mqttHost={MQTT_URL}
                clientRef={mqttClientRef}
                onLayer1StatusMessage={msg => setLayer1Capabilities(msg.capabilities || [])}
            />
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
                                    {meeting.count_first_crossing && ' · First crossing counts as lap 1'}
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

                        {(meeting.sessions || []).map((session, sessionIdx) => (
                            <div key={session.id} className="admin-session-row">
                                {editingSessionId === session.id ? (
                                    <SessionForm
                                        initial={session}
                                        meetingId={meeting.id}
                                        onSave={(form) => handleUpdateSession(session.id, meeting.id, form)}
                                        onCancel={() => setEditingSessionId(null)}
                                        hasPowerControl={hasPowerControl}
                                    />
                                ) : (
                                    <div className="admin-session-display">
                                        <span className="admin-session-title">Session {sessionIdx + 1}</span>
                                        {session.state === 'InProgress' && (
                                            <span className="admin-session-badge">In Progress</span>
                                        )}
                                        {session.races_per_driver != null && (
                                            <span className="admin-session-detail">
                                                {session.races_total != null ? `${session.races_total} races ` : ''}
                                                ({session.races_per_driver} races per driver)
                                            </span>
                                        )}
                                        <span className="admin-session-detail">
                                            {session.end_condition_info}&nbsp;{session.end_condition === 'Time' ? 'minute' : 'lap'} races
                                        </span>
                                        <span
                                            className="admin-session-icon"
                                            title={SESSION_TYPE_LABELS[session.session_type] || session.session_type}
                                        >
                                            <SessionTypeIcon type={session.session_type} />
                                        </span>
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
                                    hasPowerControl={hasPowerControl}
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
