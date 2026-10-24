import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAdminAuth } from '../../contexts/adminAuth';
import './PinPrompt.css';

// Full page by default (RequireAdmin). With onCancel it is a modal over the current page.
function PinPrompt({ onCancel }) {
    const { login } = useAdminAuth();
    const navigate = useNavigate();
    const atRoot = useLocation().pathname === '/';
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
        <div className={onCancel ? 'pin-page pin-page--modal' : 'pin-page'} onClick={onCancel}>
            <div className="pin-card" onClick={e => e.stopPropagation()}>
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
                {onCancel
                    ? <button type="button" className="pin-back" onClick={onCancel}>Cancel</button>
                    : !atRoot && <button type="button" className="pin-back" onClick={() => navigate(-1)}>← Back</button>}
            </div>
        </div>
    );
}

export default PinPrompt;
