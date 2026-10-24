import { useState, useRef } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { LogOut, Users } from 'lucide-react';
import { useAdminAuth } from '../../contexts/adminAuth';
import MqttSubscriber from '../MqttSubscriber.jsx';
import MeetingForm from './MeetingForm.jsx';
import ClockSyncPrompt from './ClockSyncPrompt.jsx';
import './Admin.css';
import { API_URL, MQTT_URL } from '../../endpoints.js';


// The default page: every meeting, with a link to each one's own home page. Sessions,
// Race Control and everything else are reached from there.
const Meetings = () => {
    const { logout } = useAdminAuth();
    const loaderData = useLoaderData();
    const [meetings, setMeetings] = useState(loaderData?.meetings || []);
    const [activeMeetingId, setActiveMeetingId] = useState(loaderData?.activeMeetingId ?? null);
    const [newMeetingOpen, setNewMeetingOpen] = useState(false);
    const [editingMeetingId, setEditingMeetingId] = useState(null);
    const [endingMeetingId, setEndingMeetingId] = useState(null);
    const [endingMeetingLoading, setEndingMeetingLoading] = useState(false);
    const [endingMeetingError, setEndingMeetingError] = useState(null);

    // admin_update is the "something changed, re-fetch" ping an already-open /racecontrol
    // listens for; ending or reopening a meeting changes which one is active.
    const mqttClientRef = useRef(null);
    const publishAdminUpdate = (reason, extra = {}) => {
        mqttClientRef.current?.publish('admin_update', JSON.stringify({ reason, ...extra }));
    };

    const meetingsSorted = [...meetings].sort((a, b) => b.date.localeCompare(a.date));

    const reloadAll = async () => {
        const [res, activeRes] = await Promise.all([
            fetch(`${API_URL}/meetings`),
            fetch(`${API_URL}/meetings/active`),
        ]);
        if (!res.ok) return;
        setMeetings(await res.json());
        setActiveMeetingId(activeRes.ok ? (await activeRes.json()).id : null);
    };

    const handleEndMeeting = async () => {
        setEndingMeetingLoading(true);
        setEndingMeetingError(null);
        try {
            const res = await fetch(`${API_URL}/meetings/${endingMeetingId}/end`, { method: 'POST' });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail || 'Failed to end meeting');
            }
            await reloadAll();
            publishAdminUpdate('meeting_ended', { meeting_id: endingMeetingId });
            setEndingMeetingId(null);
        } catch (err) {
            setEndingMeetingError(err.message);
        } finally {
            setEndingMeetingLoading(false);
        }
    };

    const handleReopenMeeting = async (id) => {
        const res = await fetch(`${API_URL}/meetings/${id}/reopen`, { method: 'POST' });
        if (!res.ok) return;
        await reloadAll();
        publishAdminUpdate('meeting_reopened', { meeting_id: id });
    };

    const handleCreateMeeting = async (form) => {
        const res = await fetch(`${API_URL}/meetings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error('Failed to create meeting');
        await reloadAll();
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

    return (
        <div className="admin-page">
            <MqttSubscriber mqttHost={MQTT_URL} clientRef={mqttClientRef} />
            <div className="admin-header">
                <div className="admin-header-left">
                    <h1 className="admin-title">Race Meetings</h1>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <Link to="/drivers" className="admin-btn-ghost admin-btn-sm" style={{ textDecoration: 'none' }} title="All drivers">
                        <Users size={16} /> Drivers
                    </Link>
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

            {meetingsSorted.map(meeting => (
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
                                    <Link to={`/m/${meeting.public_id}`}>{meeting.name}</Link>
                                    {meeting.id === activeMeetingId && <span className="admin-active-badge">Active</span>}
                                    {meeting.ended_at && <span className="admin-session-state--finished admin-active-badge">Ended</span>}
                                </span>
                                <span className="admin-meeting-meta">
                                    {meeting.date}
                                    {meeting.venue && ` · ${meeting.venue}`}
                                </span>
                            </div>
                            <Link to={`/m/${meeting.public_id}`} className="admin-btn-primary admin-btn-sm" style={{ textDecoration: 'none' }}>
                                Open
                            </Link>
                            {meeting.ended_at ? (
                                <button
                                    className="admin-btn-ghost admin-btn-sm"
                                    onClick={() => handleReopenMeeting(meeting.id)}
                                    title="Make this meeting available again"
                                >
                                    Reopen
                                </button>
                            ) : (
                                <button
                                    className="admin-btn-ghost admin-btn-sm admin-end-session-btn"
                                    onClick={() => { setEndingMeetingId(meeting.id); setEndingMeetingError(null); }}
                                    title="End this meeting"
                                >
                                    End Meeting
                                </button>
                            )}
                            <button
                                className="admin-btn-ghost admin-btn-sm"
                                onClick={() => { setEditingMeetingId(meeting.id); setNewMeetingOpen(false); }}
                            >
                                Edit
                            </button>
                        </div>
                    )}
                </div>
            ))}

            {endingMeetingId && (
                <div className="admin-modal-overlay" onClick={() => setEndingMeetingId(null)}>
                    <div className="admin-modal" onClick={e => e.stopPropagation()}>
                        <p className="admin-modal-title">End this meeting?</p>
                        <p className="admin-modal-body">
                            The meeting stops being the active one, so RaceControl moves on to the next
                            unended meeting. Its sessions and results stay as they are, and you can reopen it later.
                        </p>
                        {endingMeetingError && <p className="admin-error">{endingMeetingError}</p>}
                        <div className="admin-modal-actions">
                            <button className="admin-btn-ghost" onClick={() => setEndingMeetingId(null)}>Cancel</button>
                            <button className="admin-btn-primary" onClick={handleEndMeeting} disabled={endingMeetingLoading}>
                                {endingMeetingLoading ? 'Ending…' : 'End Meeting'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <ClockSyncPrompt />
        </div>
    );
};

export default Meetings;
