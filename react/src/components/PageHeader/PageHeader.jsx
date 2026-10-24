import './PageHeader.css';
import { Link } from 'react-router-dom';
import { House } from 'lucide-react';
import { useGuestBase } from '../utils/meetingPaths';

// Shared compact page header: home icon + title. Used by /currentrace and
// /nextrace so they share the same height and layout.
function PageHeader({ title }) {
    const base = useGuestBase();
    return (
        <div className="page-header">
            <Link to={base || '/'} className="page-header-home" aria-label="Home"><House /></Link>
            <h1>{title}</h1>
        </div>
    );
}

export default PageHeader;
