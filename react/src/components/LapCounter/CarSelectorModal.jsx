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


    if (cars && showMe) {
        return (
            <>
            <div className="fullscreenblur"></div>
            <div className="carselectormodal">
                <div className="carcontainer">
                    {cars.map((car, idx) => {
                        return <a className="carimage" key={idx} onClick={() => onCarSelected?.(car)}><CarImage url={car.url} /></a>
                    })}
                </div>

                <div className="carselectorbuttons">
                    <button onClick={onClose}>Done</button>
                </div>
            </div>
            </>
        );
    } else {
        return null;
    }
}

export default CarSelectorModal;
