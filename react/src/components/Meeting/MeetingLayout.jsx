import { Outlet, Link, useLoaderData } from 'react-router-dom';
import '../Home/Home.css';

// Wraps every /m/:publicId/... page. The loader resolves the id; an unknown one gets a
// plain message rather than a page that silently shows some other meeting's data.
export default function MeetingLayout() {
    const meeting = useLoaderData();
    if (!meeting) {
        return (
            <div className="home-page">
                <h1 className="home-title">Meeting not found</h1>
                <p>This link doesn&rsquo;t match a meeting. Check the QR code or ask the organiser.</p>
                <Link to="/" className="home-button"><span>Home</span></Link>
            </div>
        );
    }
    return <Outlet />;
}
