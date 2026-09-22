import './StartRaceModal.css';

function StartRaceModal({ showMe, onStart, onClose }) {
    if (!showMe) return null;
    return (
        <div className="start-race-overlay" onClick={onClose}>
            <div className="start-race-modal" onClick={e => e.stopPropagation()}>
                <h2>Next Race</h2>
                <button className="start-race-btn" onClick={onStart}>Start</button>
            </div>
        </div>
    );
}

export default StartRaceModal;
