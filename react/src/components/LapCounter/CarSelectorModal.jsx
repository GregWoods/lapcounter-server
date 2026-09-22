import { useEffect, useState } from 'react';
import CarImage from './CarImage';
import './CarSelectorModal.css';
import {driverSorter} from './lapUtils.js';


const CarSelectorModal = ({ showMe, onClose, carImgListUrl, drivers, setDrivers, driverIdx, setDriverIdx, onCarSelected }) => {

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


    const setCarImage = (car) => {
        if (drivers && setDrivers) {
            let newDrivers = [...drivers];
            newDrivers[driverIdx] = {...drivers[driverIdx], carImgUrl: car.url};
            setDrivers(newDrivers);
            skipDriver();
        }
        onCarSelected?.(car);
    }

    const skipDriver = () => {
        if (!drivers || !setDriverIdx) return;
        const currentDriver = drivers[driverIdx];
        const tmpDrivers = drivers.filter(Boolean).sort(driverSorter);
        const currentDriverSortedIdx = tmpDrivers.findIndex(driver => driver.number === currentDriver.number);

        let nextDriverSortedIdx;
        if (currentDriverSortedIdx === tmpDrivers.length - 1) {
            nextDriverSortedIdx = 0;
        } else {
            nextDriverSortedIdx = currentDriverSortedIdx + 1;
        }
        const nextDriverNumber = tmpDrivers[nextDriverSortedIdx].number;
        const nextDriverIdx = drivers.findIndex(driver => driver?.number === nextDriverNumber);

        setDriverIdx(nextDriverIdx);
    }


    const setSpotlightMe = () => {
        if (!drivers || !setDrivers) return;
        const newDrivers = drivers.map((driver, index) => {
            if (!driver) return null;
            return { ...driver, spotlightMe: (index === driverIdx) };
        });
        setDrivers(newDrivers);
    }

    if (cars && showMe) {
        if (drivers) setSpotlightMe();

        return (
            <>
            <div className="fullscreenblur"></div>
            <div className="carselectormodal">
                <div className="carcontainer">
                    {cars.map((car, idx) => {
                        return <a className="carimage" key={idx} onClick={() => setCarImage(car)}><CarImage url={car.url} /></a>
                    })}
                </div>

                <div className="carselectorbuttons">
                    {drivers && <><button onClick={skipDriver}>Skip</button>&nbsp;&nbsp;</>}
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
