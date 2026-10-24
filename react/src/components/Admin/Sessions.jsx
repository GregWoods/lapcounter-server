import { useRef, useState } from 'react';
import { useLoaderData, useRouteLoaderData, Link } from 'react-router-dom';
import { House, LogOut } from 'lucide-react';
import { useAdminAuth } from '../../contexts/adminAuth';
import MqttSubscriber from '../MqttSubscriber.jsx';
import SessionForm from './SessionForm.jsx';
import SessionTypeIcon from './SessionTypeIcon.jsx';
import './Admin.css';
import { API_URL, MQTT_URL } from '../../endpoints.js';


// The sessions of one meeting (/m/:publicId/sessions). Reached from the meeting's home page.
const Sessions = () => {
    const { logout } = useAdminAuth();
    const meeting = useRouteLoaderData('meeting');
    const [sessions, setSessions] = useState(useLoaderData() || []);
    const [addingSession, setAddingSession] = useState(false);
    const [editingSessionId, setEditingSessionId] = useState(null);
    const [endingSessionId, setEndingSessionId] = useState(null);
    const [endingLoading, setEndingLoading] = useState(false);
    const [endingError, setEndingError] = useState(null);

    // Queries are HTTP, events are MQTT: a session create/finish here changes what
    // /racecontrol should show (Next Session availability, "Session complete"), but this
    // page only talks to the API, so nothing tells a /racecontrol tab already open
    // elsewhere. admin_update is a plain "something changed, re-fetch" ping — deliberately
    // not race_control, which is lapdata/BLE's command channel, not a browser-to-browser
    // UI-refresh signal. RaceControl.jsx just calls its own loadInfo() on receipt.
    // Tagged with this tab's id so it can ignore its own echo: it has already reloaded.
    const mqttClientRef = useRef(null);
    const senderId = useRef(Math.random().toString(36).slice(2));
    const publishAdminUpdate = (reason, extra = {}) => {
        mqttClientRef.current?.publish('admin_update', JSON.stringify({ reason, ...extra, sender: senderId.current }));
    };

    // null = no layer1_status seen yet. Treated the same as "no power control" for
    // gating the session form's power-percentage fields — the form must never let an
    // operator set a percentage that silently does nothing, so "unknown" defaults to
    // the safe, locked state rather than briefly showing the fields as editable.
    const [layer1Capabilities, setLayer1Capabilities] = useState(null);
    const hasPowerControl = !!layer1Capabilities?.includes('power_control');

    const base = `/m/${meeting.public_id}`;

    const reload = async () => {
        const res = await fetch(`${API_URL}/sessions?meeting_id=${meeting.id}`);
        if (res.ok) setSessions(await res.json());
    };

    const handleEndSession = async () => {
        setEndingLoading(true);
        setEndingError(null);
        try {
            const res = await fetch(`${API_URL}/sessions/${endingSessionId}/finish`, { method: 'POST' });
            if (!res.ok) throw new Error('Failed to end session');
            await reload();
            publishAdminUpdate('session_finished', { session_id: endingSessionId });
            setEndingSessionId(null);
        } catch (err) {
            setEndingError(err.message);
        } finally {
            setEndingLoading(false);
        }
    };

    const handleCreateSession = async (form) => {
        const res = await fetch(`${API_URL}/sessions/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error('Failed to create session');
        await reload();
        publishAdminUpdate('session_created', { meeting_id: meeting.id });
        setAddingSession(false);
    };

    const handleUpdateSession = async (sessionId, form) => {
        // Strip fields that shouldn't be patched (state is system-managed)
        // eslint-disable-next-line no-unused-vars
        const { meeting_id, state, ...updateFields } = form;
        const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateFields),
        });
        if (!res.ok) throw new Error('Failed to update session');
        await reload();
        setEditingSessionId(null);
    };

    return (
        <div className="admin-page">
            <MqttSubscriber
                mqttHost={MQTT_URL}
                clientRef={mqttClientRef}
                onAdminUpdateMessage={msg => { if (msg?.sender !== senderId.current) reload(); }}
                onLayer1StatusMessage={msg => setLayer1Capabilities(msg.capabilities || [])}
            />
            <div className="admin-header">
                <div className="admin-header-left">
                    <Link to={base} className="home-icon-link"><House /></Link>
                    <h1 className="admin-title">{meeting.name} — Sessions</h1>
                </div>
                <button className="admin-btn-ghost admin-btn-sm" onClick={logout} title="Lock admin">
                    <LogOut size={16} />
                </button>
            </div>

            <div className="admin-card">
                <div className="admin-sessions">
                    {sessions.length === 0 && !addingSession && (
                        <p className="admin-sessions-empty">No sessions — add one below.</p>
                    )}

                    {sessions.map((session, sessionIdx) => (
                        <div key={session.id} className="admin-session-row">
                            {editingSessionId === session.id ? (
                                <SessionForm
                                    initial={session}
                                    meetingId={meeting.id}
                                    onSave={(form) => handleUpdateSession(session.id, form)}
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
                                    {session.start_grid === 'InFrontOfLine' && (
                                        <span className="admin-session-detail">First crossing counts as lap 1</span>
                                    )}
                                    <SessionTypeIcon type={session.session_type} />
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
                                            <Link to={`${base}/results/${session.id}`} className="admin-btn-ghost admin-btn-sm" style={{ textDecoration: 'none' }}>
                                                Results
                                            </Link>
                                        ) : (
                                            <button
                                                className="admin-btn-ghost admin-btn-sm"
                                                onClick={() => { setEditingSessionId(session.id); setAddingSession(false); }}
                                            >
                                                Edit
                                            </button>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}

                    {addingSession ? (
                        <div className="admin-session-row">
                            <SessionForm
                                meetingId={meeting.id}
                                previousYellowGraceSeconds={sessions.at(-1)?.yellow_grace_seconds}
                                onSave={handleCreateSession}
                                onCancel={() => setAddingSession(false)}
                                hasPowerControl={hasPowerControl}
                            />
                        </div>
                    ) : (
                        <button
                            className="admin-btn-add-session"
                            onClick={() => { setAddingSession(true); setEditingSessionId(null); }}
                        >
                            + Add Session
                        </button>
                    )}
                </div>
            </div>

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

export default Sessions;
