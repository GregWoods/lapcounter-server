import { useEffect, useState } from 'react';
import ReactModal from 'react-modal';
import CarImage from './CarImage';
import './CarSelectorModal.css';


// eslint-disable-next-line no-unused-vars
const CarSelectorModal = ({ showMe, onClose, carImgListUrl, drivers, setDrivers, driverIdx, setDriverIdx }) => {

    //holds list of car Urls fetched from server
    const [cars, setCars] = useState([]);

    useEffect(() => {
        console.log('This is supposed to be in the modal');
        //console.log(process.env.PUBLIC_URL);
        fetch(carImgListUrl)
            .then((res) => res.json())
            .then((data) => {
                setCars(data);
                console.dir(data);
            },
                (error) => {
                    console.log(error);
                }
            );
    }, [carImgListUrl]);


    const setCarImage = (carUrl) => {
        console.log('setCarImage');
        console.dir(carUrl);

        let newDrivers = [...drivers];
        newDrivers[driverIdx] = {...drivers[driverIdx], carImgUrl: carUrl};
        setDrivers(newDrivers);
    }

    const previousDriver = () => {
        if (driverIdx === 0) {
            return;
        }
        setDriverIdx(prevDriverIdx => prevDriverIdx - 1);
    }

    const nextDriver = () => {
        if (driverIdx === drivers.length - 1) {
            return;
        }
        setDriverIdx(prevDriverIdx => prevDriverIdx + 1);
    }


    if (cars) {
        console.log("car selector modal");
        console.dir(drivers);
        console.log(driverIdx);
        return (
            <ReactModal
                isOpen={showMe}
                onRequestClose={onClose}
                id="carselectormodal"
                contentLabel="Select Car"
                closeTimeoutMS={1050}
                className="ReactModalContent"
                overlayClassName="ReactModalOverlay"
                ariaHideApp={false}
            >
                <div>
                    <h2>{drivers[driverIdx]?.name}</h2>
                </div>
                <div className="carcontainer">
                    {cars.map((car, idx) => {
                        return <a key={idx} onClick={() => setCarImage(car)}>
                            <CarImage url={car} />
                        </a>
                    })}
                </div>

                <div>
                    <a onClick={previousDriver}>&lt;&lt;</a>
                    <a onClick={onClose}>Done</a>
                    <a onClick={nextDriver}>&gt;&gt;</a>
                </div>
            </ReactModal>
        );
    } else {
        return null;
    }
}

export default CarSelectorModal;