import { useState } from 'react';
import { useRouteLoaderData, Link } from 'react-router-dom';
import { House } from 'lucide-react';
import './Register.css';
import { API_URL } from '../../endpoints.js';

const Register = () => {
    // Registration is always for the meeting whose link the driver opened.
    const meeting = useRouteLoaderData('meeting');
    const base = `/m/${meeting.public_id}`;

    const [step, setStep] = useState('name');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [selectedDriverId, setSelectedDriverId] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleNameSubmit = async (e) => {
        e.preventDefault();
        if (!firstName.trim()) return;
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`${API_URL}/drivers/search?q=${encodeURIComponent(firstName.trim())}`);
            if (!res.ok) throw new Error('Search failed');
            const results = await res.json();
            if (results.length > 0) {
                setSearchResults(results);
                setStep('found');
            } else {
                await register(null);
            }
        } catch {
            setError('Could not search for drivers. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    // Adds the driver to this meeting, creating their profile first when they're new.
    // Returns on success with the step moved to 'done'.
    const register = async (existingDriverId) => {
        setLoading(true);
        setError(null);
        try {
            let driverId = existingDriverId;

            if (driverId === null) {
                const res = await fetch(`${API_URL}/drivers/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        first_name: firstName.trim(),
                        last_name: lastName.trim() || null,
                        sit_out_next_race: false,
                    }),
                });
                if (!res.ok) throw new Error('Failed to create driver profile');
                driverId = (await res.json()).id;
            }
            setSelectedDriverId(existingDriverId);

            const res = await fetch(`${API_URL}/meetings/${meeting.id}/drivers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ driver_id: driverId }),
            });
            // 409 = already registered for this meeting — treat as success
            if (!res.ok && res.status !== 409) throw new Error('Registration failed. Please try again.');

            setStep('done');
        } catch (err) {
            setError(err.message || 'Registration failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const reset = () => {
        setStep('name');
        setFirstName('');
        setLastName('');
        setSearchResults([]);
        setSelectedDriverId(null);
        setError(null);
    };

    return (
        <div className="register-page">
            <div className="register-card">

                {step === 'name' && (
                    <>
                        <div className="register-title-row">
                            <Link to={base} className="home-icon-link"><House /></Link>
                            <h1 className="register-heading">Driver Registration</h1>
                        </div>
                        <form onSubmit={handleNameSubmit} className="register-form">
                            <label className="register-label">First name</label>
                            <input
                                className="register-input"
                                type="text"
                                value={firstName}
                                onChange={e => setFirstName(e.target.value)}
                                placeholder="Jake"
                                autoFocus
                                autoComplete="given-name"
                                required
                            />
                            <label className="register-label">
                                Last name <span className="register-optional">(optional)</span>
                            </label>
                            <input
                                className="register-input"
                                type="text"
                                value={lastName}
                                onChange={e => setLastName(e.target.value)}
                                placeholder="Woods"
                                autoComplete="family-name"
                            />
                            {error && <p className="register-error">{error}</p>}
                            <button className="register-btn-primary" type="submit" disabled={loading || !firstName.trim()}>
                                {loading ? 'Searching…' : 'Next'}
                            </button>
                        </form>
                    </>
                )}

                {step === 'found' && (
                    <>
                        <button className="register-back" onClick={() => setStep('name')}>← Back</button>
                        <h1 className="register-heading">Is this you?</h1>
                        <p className="register-subtext">Select your name, or register as a new driver below.</p>
                        <div className="register-results">
                            {searchResults.map(d => (
                                <button
                                    key={d.id}
                                    className="register-driver-btn"
                                    onClick={() => register(d.id)}
                                    disabled={loading}
                                >
                                    {d.first_name}{d.last_name ? ` ${d.last_name}` : ''}
                                </button>
                            ))}
                        </div>
                        {error && <p className="register-error">{error}</p>}
                        <button className="register-btn-secondary" onClick={() => register(null)} disabled={loading}>
                            I&rsquo;m new — create my profile
                        </button>
                    </>
                )}

                {step === 'done' && (
                    <>
                        <div className="register-done-icon">✓</div>
                        <h1 className="register-heading">
                            {selectedDriverId ? 'Welcome back!' : 'You\'re registered!'}
                        </h1>
                        <p className="register-subtext">
                            {firstName} is set for {meeting.name}.
                        </p>
                        <div className="register-done-actions">
                            <button className="register-btn-secondary" onClick={reset}>
                                Register another driver
                            </button>
                            <Link to={base} className="register-btn-primary register-btn-link">
                                Done
                            </Link>
                        </div>
                    </>
                )}

            </div>
        </div>
    );
};

export default Register;
