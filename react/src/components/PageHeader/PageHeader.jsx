import './PageHeader.css';
import { Link } from 'react-router-dom';
import { House } from 'lucide-react';

// Shared compact page header: home icon + title. Used by /currentrace and
// /nextrace so they share the same height and layout.
function PageHeader({ title }) {
    return (
        <div className="page-header">
            <Link to="/" className="page-header-home" aria-label="Home"><House /></Link>
            <h1>{title}</h1>
        </div>
    );
}

export default PageHeader;
