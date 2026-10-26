import { useEffect, useState } from 'react';
import CarImage from './CarImage';
import './CarSelectorModal.css';


// NextRace's car picker. /currentrace has none: a race is edited only while it is queued.
const CarSelectorModal = ({ showMe, onClose, carImgListUrl, onCarSelected }) => {

    const [cars, setCars] = useState([]);

    useEffect(() => {
        fetch(carImgListUrl)
            .then((res) => res.json())
            .then((data) => {
                setCars(data);
            },
                (error) => {
                    console.log('Error fetching carImgListUrl: ', carImgListUrl)
                    console.log(error);
                }
            );
    }, [carImgListUrl]);

    // Escape and a click outside close it too, so it can always be dismissed.
    useEffect(() => {
        if (!showMe) return;
        const onKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [showMe, onClose]);


    if (cars && showMe) {
        return (
            <>
            <div className="fullscreenblur" onClick={onClose}></div>
            <div className="carselectormodal">
                <div className="carcontainer">
                    {cars.map((car, idx) => {
                        return <a className="carimage" key={idx} onClick={() => onCarSelected?.(car)}><CarImage url={car.url} /></a>
                    })}
                </div>

                <div className="carselectorbuttons">
                    <button onClick={onClose}>Cancel</button>
                </div>
            </div>
            </>
        );
    } else {
        return null;
    }
}

export default CarSelectorModal;
