import { useState } from 'react';
import { useLoaderData, Link } from 'react-router-dom';
import { House } from 'lucide-react';
import './Register.css';

const API_URL = import.meta.env.VITE_API_URL;

const formatDate = (dateStr) =>
    new Date(dateStr).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });

const Register = () => {
    const meetings = useLoaderData() || [];

    const [step, setStep] = useState('name');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [selectedDriverId, setSelectedDriverId] = useState(null);
    const [selectedMeetingIds, setSelectedMeetingIds] = useState(new Set());
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
                setSelectedDriverId(null);
                setStep('meetings');
            }
        } catch {
            setError('Could not search for drivers. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleSelectExisting = async (driverId) => {
        setSelectedDriverId(driverId);
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/drivers/${driverId}/meetings`);
            if (res.ok) {
                const registeredIds = await res.json();
                const upcomingIds = new Set(meetings.map(m => m.id));
                setSelectedMeetingIds(new Set(registeredIds.filter(id => upcomingIds.has(id))));
            }
        } catch {
            setSelectedMeetingIds(new Set());
        } finally {
            setLoading(false);
        }
        setStep('meetings');
    };

    const toggleMeeting = (id) => {
        setSelectedMeetingIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const handleRegister = async () => {
        if (selectedMeetingIds.size === 0) {
            setError('Please select at least one meeting.');
            return;
        }
        setLoading(true);
        setError(null);
        try {
            let driverId = selectedDriverId;

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

            const results = await Promise.allSettled(
                [...selectedMeetingIds].map(async (meetingId) => {
                    const res = await fetch(`${API_URL}/meetings/${meetingId}/drivers`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ driver_id: driverId }),
                    });
                    // 409 = already registered for this meeting — treat as success
                    if (!res.ok && res.status !== 409) throw new Error(`Meeting ${meetingId}: ${res.status}`);
                })
            );

            const failures = results.filter(r => r.status === 'rejected');
            if (failures.length > 0) throw new Error('Some meeting registrations failed');

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
        setSelectedMeetingIds(new Set());
        setError(null);
    };

    return (
        <div className="register-page">
            <div className="register-card">

                {step === 'name' && (
                    <>
                        <div className="register-title-row">
                            <Link to="/" className="home-icon-link"><House /></Link>
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
                                    onClick={() => handleSelectExisting(d.id)}
                                    disabled={loading}
                                >
                                    {d.first_name}{d.last_name ? ` ${d.last_name}` : ''}
                                </button>
                            ))}
                        </div>
                        <button className="register-btn-secondary" onClick={() => { setSelectedDriverId(null); setStep('meetings'); }}>
                            I&rsquo;m new — create my profile
                        </button>
                    </>
                )}

                {step === 'meetings' && (
                    <>
                        <button className="register-back" onClick={() => setStep(searchResults.length > 0 ? 'found' : 'name')}>← Back</button>
                        <h1 className="register-heading">Select meetings</h1>
                        {meetings.length === 0 ? (
                            <p className="register-subtext">No upcoming meetings found.</p>
                        ) : (
                            <div className="register-meetings">
                                {meetings.map(m => (
                                    <label key={m.id} className="register-meeting-row">
                                        <input
                                            type="checkbox"
                                            className="register-checkbox"
                                            checked={selectedMeetingIds.has(m.id)}
                                            onChange={() => toggleMeeting(m.id)}
                                        />
                                        <span className="register-meeting-info">
                                            <span className="register-meeting-name">{m.name}</span>
                                            <span className="register-meeting-date">{formatDate(m.date)}</span>
                                        </span>
                                    </label>
                                ))}
                            </div>
                        )}
                        {error && <p className="register-error">{error}</p>}
                        <button
                            className="register-btn-primary"
                            onClick={handleRegister}
                            disabled={loading || selectedMeetingIds.size === 0}
                        >
                            {loading ? 'Registering…' : 'Register'}
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
                            {firstName} is set for {selectedMeetingIds.size === 1 ? '1 meeting' : `${selectedMeetingIds.size} meetings`}.
                        </p>
                        <button className="register-btn-secondary" onClick={reset}>
                            Register another driver
                        </button>
                    </>
                )}

            </div>
        </div>
    );
};

export default Register;
