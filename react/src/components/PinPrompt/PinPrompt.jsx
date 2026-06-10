import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAdminAuth } from '../../contexts/AdminAuthContext';
import './PinPrompt.css';

function PinPrompt() {
    const { login } = useAdminAuth();
    const [pin, setPin] = useState('');
    const [error, setError] = useState(false);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!login(pin)) {
            setError(true);
            setPin('');
        }
    };

    return (
        <div className="pin-page">
            <div className="pin-card">
                <h1 className="pin-title">Admin Access</h1>
                <p className="pin-subtitle">Enter PIN to continue</p>
                <form className="pin-form" onSubmit={handleSubmit}>
                    <input
                        className="pin-input"
                        type="password"
                        inputMode="numeric"
                        value={pin}
                        onChange={e => { setPin(e.target.value); setError(false); }}
                        autoFocus
                        placeholder="••••"
                    />
                    {error && <p className="pin-error">Incorrect PIN</p>}
                    <button type="submit" className="pin-btn">Enter</button>
                </form>
                <Link to="/" className="pin-back">← Back to home</Link>
            </div>
        </div>
    );
}

export default PinPrompt;
