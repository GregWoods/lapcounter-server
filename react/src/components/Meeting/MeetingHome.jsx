import { Link, useRouteLoaderData } from 'react-router-dom';
import { UserPlus, Flag, ListOrdered, Trophy, CalendarDays, ArrowLeft } from 'lucide-react';
import ChequeredFlagIcon from '../ChequeredFlagIcon';
import { useAdminAuth } from '../../contexts/adminAuth';
import '../Home/Home.css';

// What a driver sees after scanning the QR code: only this meeting's pages.
export default function MeetingHome() {
    const meeting = useRouteLoaderData('meeting');
    const base = `/m/${meeting.public_id}`;
    // Only admins see the management pages; the routes are PIN-gated regardless.
    const { isAdmin } = useAdminAuth();
    return (
        <div className="home-page">
            <h1 className="home-title">{meeting.name}</h1>
            {meeting.ended_at && <p>This meeting has ended.</p>}
            <nav className="home-nav">
                <Link to={`${base}/register`} className="home-button"><UserPlus /><span>Driver Registration</span></Link>
                <Link to={`${base}/currentrace`} className="home-button"><Flag /><span>Current Race</span></Link>
                <Link to={`${base}/nextrace`} className="home-button"><ListOrdered /><span>Next Race</span></Link>
                <Link to={`${base}/results`} className="home-button"><Trophy /><span>Results</span></Link>
                {isAdmin && <>
                    <Link to={`${base}/racecontrol`} className="home-button"><ChequeredFlagIcon /><span>Race Control</span></Link>
                    <Link to={`${base}/sessions`} className="home-button"><CalendarDays /><span>Sessions</span></Link>
                    <Link to="/" className="home-button"><ArrowLeft /><span>All Meetings</span></Link>
                </>}
            </nav>
        </div>
    );
}
