import { Link } from 'react-router-dom';
import '../Home/Home.css';

// Shown instead of the QR codes (and at "/") when no meeting is in progress. The system
// can't tell whether the last ended meeting is today's or an old one, so it never guesses:
// guests get nothing to scan until an admin starts a meeting. `adminLink` adds the way in.
export default function NoMeeting({ adminLink = false }) {
    return (
        <div className="home-page" style={{ justifyContent: 'center' }}>
            <h1 className="home-title">No Meetings in Progress</h1>
            {adminLink && (
                <Link to="/meetings" className="home-button" style={{ width: 'auto' }}><span>Admin</span></Link>
            )}
        </div>
    );
}
