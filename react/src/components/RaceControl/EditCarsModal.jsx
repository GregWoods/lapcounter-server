import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { API_URL } from '../../endpoints.js';
import CarPicker from '../CarPicker/CarPicker';
import { carImageUrl, onCarImgError } from '../CarPicker/carImages.js';


// Put a different car on a lane (#111). Step 1 picks the lane, step 2 the car. A change is
// for the rest of the session: every queued race, and any race built later. A race already
// under way keeps its car, since a race is edited only while it is queued.
export default function EditCarsModal({ onClose, onChanged }) {
    const [lanes, setLanes] = useState(null);
    const [selectedLane, setSelectedLane] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetch(`${API_URL}/sessions/active/cars`)
            .then(res => res.ok ? res.json() : Promise.reject(res.status))
            .then(data => setLanes(data.lanes), () => setError('No session to edit cars for.'));
    }, []);

    // Step 2 handles Escape itself, so only listen while on step 1.
    useEffect(() => {
        if (selectedLane) return;
        const onKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onClose, selectedLane]);

    const chooseCar = async (car) => {
        const lane = selectedLane;
        try {
            const res = await fetch(`${API_URL}/sessions/active/lanes/${lane.lane}/car`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ car_id: car.id }),
            });
            if (!res.ok) throw new Error(res.status);
            const data = await res.json();
            setLanes(data.lanes);
            setError(null);
            onChanged?.();
        } catch {
            setError(`Couldn't change lane ${lane.lane}'s car.`);
        }
        setSelectedLane(null);
    };

    if (selectedLane) {
        return (
            <CarPicker
                lane={selectedLane.lane}
                laneColor={selectedLane.lane_color}
                currentCarId={selectedLane.car_id}
                onPick={chooseCar}
                onBack={() => setSelectedLane(null)}
                onClose={onClose}
            />
        );
    }

    return (
        <div className="rc-modal">
            <header className="rc-modal-header">
                <span className="rc-modal-icon-spacer" />
                <h2>Edit Cars</h2>
                <button className="rc-modal-icon" onClick={onClose} aria-label="Close">
                    <X />
                </button>
            </header>

            {error && <div className="rc-modal-error">{error}</div>}

            {lanes && (
                <>
                    <p className="rc-modal-hint">Pick a lane. Its new car is used for every remaining race this session.</p>
                    <div className="rc-lanecars">
                        {lanes.map((l) => (
                            <button
                                key={l.lane}
                                className={`rc-lanecar${l.lane_enabled ? '' : ' rc-lanecar--disabled'}`}
                                style={{ '--lane-color': l.lane_color }}
                                onClick={() => setSelectedLane(l)}
                            >
                                <span className="rc-lanecar-lane">{l.lane}</span>
                                <img src={carImageUrl(l.car_picture)} alt={l.car_name ?? 'Car'} onError={onCarImgError} />
                                <span className="rc-lanecar-driver">
                                    {l.lane_enabled ? (l.driver_name || '—') : 'Lane off'}
                                </span>
                            </button>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
