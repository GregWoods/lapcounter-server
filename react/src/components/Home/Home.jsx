import { useLoaderData, Link } from 'react-router-dom';
import { UserPlus, Flag, ListOrdered, Trophy, CalendarDays, Users } from 'lucide-react';
import './Home.css';

const DEFAULT_TITLE = 'Go! Go! Go! Race Manager';

function Home() {
    const activeMeeting = useLoaderData();
    const title = activeMeeting?.display_title || DEFAULT_TITLE;

    return (
        <div className="home-page">
            <h1 className="home-title">{title}</h1>
            <nav className="home-nav">
                <Link to="/register" className="home-button"><UserPlus /><span>Driver Registration</span></Link>
                <Link to="/currentrace" className="home-button"><Flag /><span>Current Race</span></Link>
                <Link to="/nextrace" className="home-button"><ListOrdered /><span>Next Race</span></Link>
                <Link to="/results" className="home-button"><Trophy /><span>Results</span></Link>
                <Link to="/drivers" className="home-button"><Users /><span>Drivers</span></Link>
                <Link to="/admin" className="home-button"><CalendarDays /><span>Meetings</span></Link>
            </nav>
        </div>
    );
}

export default Home;
