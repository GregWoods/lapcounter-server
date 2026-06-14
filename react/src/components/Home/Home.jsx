import { useState, useEffect } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { UserPlus, Flag, ListOrdered, Trophy, CalendarDays, Users } from 'lucide-react';
import './Home.css';

const DEFAULT_TITLE = 'Go! Go! Go! Race Manager';
const API_URL = import.meta.env.VITE_API_URL ?? `http://${window.location.hostname}:8000`;

function Home() {
    const activeMeeting = useLoaderData();
    const title = activeMeeting?.name || DEFAULT_TITLE;

    const [clockModalShown, setClockModalShown] = useState(false);
    const [clockDiff, setClockDiff] = useState(0);
    const [clockSyncing, setClockSyncing] = useState(false);
    const [clockError, setClockError] = useState(null);

    useEffect(() => {
        fetch(`${API_URL}/admin/clock`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data) return;
                const diff = Math.abs(Date.now() / 1000 - data.timestamp);
                if (diff > 1) { setClockDiff(diff); setClockModalShown(true); }
            })
            .catch(() => {});
    }, []);

    const handleClockSync = async () => {
        setClockSyncing(true);
        setClockError(null);
        try {
            const res = await fetch(`${API_URL}/admin/sync-clock`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp: Date.now() / 1000 }),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || 'Sync failed');
            }
            setClockModalShown(false);
        } catch (err) {
            setClockError(err.message);
        } finally {
            setClockSyncing(false);
        }
    };

    return (
        <div className="home-page">
            <h1 className="home-title">{title}</h1>
            <nav className="home-nav">
                <Link to="/register" className="home-button"><UserPlus /><span>Driver Registration</span></Link>
                <Link to="/currentrace" className="home-button"><Flag /><span>Current Race</span></Link>
                <Link to="/nextrace" className="home-button"><ListOrdered /><span>Next Race</span></Link>
                <Link to="/results" className="home-button"><Trophy /><span>Results</span></Link>
                <Link to="/drivers" className="home-button"><Users /><span>Drivers</span></Link>
                <Link to="/meetings" className="home-button"><CalendarDays /><span>Meetings</span></Link>
            </nav>

            {clockModalShown && (
                <div className="clock-modal-overlay">
                    <div className="clock-modal">
                        <p className="clock-modal-title">Pi clock out of sync</p>
                        <div className="clock-modal-times">
                            <div className="clock-modal-col">
                                <span className="clock-modal-label">This device</span>
                                <span className="clock-modal-value">{new Date().toLocaleTimeString()}</span>
                            </div>
                            <div className="clock-modal-col">
                                <span className="clock-modal-label">Difference</span>
                                <span className="clock-modal-value clock-modal-diff">
                                    {clockDiff < 60
                                        ? `${Math.round(clockDiff)}s`
                                        : clockDiff < 3600
                                            ? `${Math.round(clockDiff / 60)}m`
                                            : `${Math.round(clockDiff / 3600)}h`}
                                </span>
                            </div>
                        </div>
                        <p className="clock-modal-body">
                            Sync the Pi clock before starting races so start light timestamps are accurate.
                        </p>
                        <button className="clock-modal-btn" onClick={handleClockSync} disabled={clockSyncing}>
                            {clockSyncing ? 'Syncing…' : 'Sync Pi clock to this device'}
                        </button>
                        {clockError && <p className="clock-modal-error">{clockError}</p>}
                    </div>
                </div>
            )}
        </div>
    );
}

export default Home;
