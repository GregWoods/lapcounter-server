import { useState } from 'react';
import { Link, useRouteLoaderData } from 'react-router-dom';
import { UserPlus, Flag, ListOrdered, Trophy, CalendarDays, ArrowLeft, LogOut, KeyRound, QrCode } from 'lucide-react';
import ChequeredFlagIcon from '../ChequeredFlagIcon';
import PinPrompt from '../PinPrompt/PinPrompt.jsx';
import { useAdminAuth } from '../../contexts/adminAuth';
import '../Home/Home.css';
import '../Admin/Admin.css';   // admin-btn-ghost, shared with the other pages' Lock admin button

// What a driver sees after scanning the QR code: only this meeting's pages.
export default function MeetingHome() {
    const meeting = useRouteLoaderData('meeting');
    const base = `/m/${meeting.public_id}`;
    // Only admins see the management pages; the routes are PIN-gated regardless.
    const { isAdmin, logout } = useAdminAuth();
    const [showPin, setShowPin] = useState(false);
    return (
        <div className="home-page">
            {isAdmin ? (
                <button
                    className="admin-btn-ghost admin-btn-sm home-lock-admin"
                    onClick={() => { logout(); setShowPin(false); }}
                    title="Lock admin"
                >
                    <LogOut size={16} />
                </button>
            ) : (
                <button
                    className="admin-btn-ghost admin-btn-sm home-lock-admin"
                    onClick={() => setShowPin(true)}
                    title="Admin"
                >
                    <KeyRound size={16} />
                </button>
            )}
            {/* Signing in flips isAdmin, which is what dismisses the modal. */}
            {showPin && !isAdmin && <PinPrompt onCancel={() => setShowPin(false)} />}
            <h1 className="home-title">{meeting.name}</h1>
            {meeting.ended_at && <p>This meeting has ended.</p>}
            <nav className="home-nav">
                <Link to={`${base}/register`} className="home-button"><UserPlus /><span>Driver Registration</span></Link>
                <Link to={`${base}/currentrace`} className="home-button"><Flag /><span>Current Race</span></Link>
                <Link to={`${base}/nextrace`} className="home-button"><ListOrdered /><span>Next Race</span></Link>
                <Link to={`${base}/results`} className="home-button"><Trophy /><span>Results</span></Link>
                {isAdmin && <>
                    <Link to={`${base}/welcome`} className="home-button"><QrCode /><span>Welcome Page</span></Link>
                    <Link to={`${base}/racecontrol`} className="home-button"><ChequeredFlagIcon /><span>Race Control</span></Link>
                    <Link to={`${base}/sessions`} className="home-button"><CalendarDays /><span>Sessions</span></Link>
                    <Link to="/meetings" className="home-button"><ArrowLeft /><span>All Meetings</span></Link>
                </>}
            </nav>
        </div>
    );
}
