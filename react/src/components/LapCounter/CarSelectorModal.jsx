import { useEffect, useState } from 'react';
import ReactModal from 'react-modal';
import CarImage from './CarImage';
import './CarSelectorModal.css';


// eslint-disable-next-line no-unused-vars
const CarSelectorModal = ({ showMe, onClose, carImgListUrl, drivers, setDrivers, driverIdxToFocus }) => {

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


    if (cars) {
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
            <div className="carcontainer">
                {cars.map((car, idx) => {
                    return <CarImage key={idx} url={car} />
                })}
            </div>
            </ReactModal>
        );
    } else {
        return null;
    }
}

export default CarSelectorModal;