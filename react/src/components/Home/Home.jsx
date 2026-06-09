import { Link } from 'react-router-dom';
import './Home.css';

function Home() {
    return (
        <div className="home-page">
            <h1 className="home-title">Lap Counter</h1>
            <nav className="home-nav">
                <Link to="/currentrace" className="home-button">Current Race</Link>
                <Link to="/nextrace" className="home-button">Next Race</Link>
                <Link to="/results" className="home-button">Results</Link>
                <Link to="/register" className="home-button">Driver Registration</Link>
                <Link to="/admin" className="home-button">Admin</Link>
            </nav>
        </div>
    );
}

export default Home;
