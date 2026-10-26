import { useEffect, useState } from 'react';
import { ArrowLeft, X } from 'lucide-react';
import { API_URL } from '../../endpoints.js';
import { onCarImgError } from './carImages.js';
import './CarPicker.css';

// Lane colours (the `lanes` table's CSS names) that need dark text on them.
const LIGHT_LANE_COLORS = new Set(['yellow', 'orange', 'white']);


// Full-screen picker for the car on one lane: RaceControl's Edit Cars (step 2) and
// NextRace's car thumbnails. Either way the car goes on the lane for the rest of the
// session (#111). Sized in em from its own clamp(), not the TV page's rem, so it works on a
// phone. `onBack` is optional: NextRace opens straight onto this step.
export default function CarPicker({ lane, laneColor, currentCarId, onPick, onBack, onClose }) {
    const [cars, setCars] = useState([]);

    useEffect(() => {
        fetch(`${API_URL}/api/cars`)
            .then(res => res.ok ? res.json() : [])
            .then(setCars, () => setCars([]));
    }, []);

    useEffect(() => {
        const onKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    return (
        // The lane colour drives the title pill and the current car's highlight alike.
        <div
            className={`carpicker${LIGHT_LANE_COLORS.has(laneColor) ? ' carpicker--light-lane' : ''}`}
            style={{ '--lane-color': laneColor }}
        >
            <header className="carpicker-header">
                {onBack ? (
                    <button className="carpicker-icon" onClick={onBack} aria-label="Back"><ArrowLeft /></button>
                ) : <span className="carpicker-icon-spacer" />}
                <h2>
                    <span className="carpicker-lane">Lane {lane}</span>
                    {' '}choose a car
                </h2>
                <button className="carpicker-icon" onClick={onClose} aria-label="Close"><X /></button>
            </header>
            <div className="carpicker-grid">
                {cars.map((car) => (
                    <button
                        key={car.id}
                        className={`carpicker-car${car.id === currentCarId ? ' carpicker-car--current' : ''}`}
                        onClick={() => onPick(car)}
                    >
                        <img src={car.url} alt={car.name ?? 'Car'} onError={onCarImgError} />
                    </button>
                ))}
            </div>
        </div>
    );
}
