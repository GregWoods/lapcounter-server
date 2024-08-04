import { useEffect, useState } from 'react';
import CarImage from './CarImage';
import './CarSelectorModal.css';
import {driverSorter} from './lapUtils.js';

// eslint-disable-next-line no-unused-vars
const CarSelectorModal = ({ showMe, onClose, carImgListUrl, drivers, setDrivers, driverIdx, setDriverIdx, parentSelector }) => {

    //holds list of car Urls fetched from server
    const [cars, setCars] = useState([]);
    //const [carSelectorModalContentRef, setCarSelectorModalContentRef] = useState(null);

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

    const skipDriver = () => {
        //need to find the index of the next driver on screen
        //  this may not be the next driver in the array
        //  this is hampered a little by the fact that I omitted adding a unique key for each driver, and used index instead!
        const currentDriver = drivers[driverIdx];
        const tmpDrivers = [...drivers].sort(driverSorter);
        const currentDriverSortedIdx = tmpDrivers.findIndex(driver => driver.name === currentDriver.name);

        let nextDriverSortedIdx;
        if (currentDriverSortedIdx === tmpDrivers.length - 1) {
            nextDriverSortedIdx = 0;
        } else {
            nextDriverSortedIdx = currentDriverSortedIdx + 1;
        }
        const nextDriverName = tmpDrivers[nextDriverSortedIdx].name;
        const nextDriverIdx = drivers.findIndex(driver => driver.name === nextDriverName);

        setDriverIdx(nextDriverIdx);
    }


    const setSpotlightMe = () => {
        //Hack to allow z-index of modal to be set
        console.log('setSpotlightMe');
        console.log(driverIdx);

        //document.getElementById('driverCardContainer')?.appendChild(carSelectorModalContentRef);

        const newDrivers = drivers.map((driver, index) => {
            return { ...driver, spotlightMe: (index === driverIdx) };
        });
        setDrivers(newDrivers);
    }

    if (cars && showMe) {
        console.log("car selector modal");
        console.dir(drivers);
        console.log(driverIdx);
        setSpotlightMe();

        return (
            <>
                <div className="fullscreenblur"></div>
                <div className="carselectormodal"
                    //isOpen={showMe}
                    //onRequestClose={onClose}
                    /*
                    //id="carselectormodal"
                    //contentLabel="Select Car"
                    //closeTimeoutMS={400}
                    //className="ReactModalContent"
                    //overlayClassName="ReactModalOverlay"
                    //ariaHideApp={false}
                    //parentSelector={() => document.querySelector('#driverCardContainer')}   //doesn't work, as the whole entourage of <div>s is moved, so still impossible to "elevate" the actual modal using zIndex
                    //contentRef={node => setCarSelectorModalContentRef(node)}
                    onAfterOpen={setSpotlightMe}
                    */
                >
                    <div className="carcontainer">
                        {cars.map((car, idx) => {
                            return <a key={idx} onClick={() => setCarImage(car)}>
                                <CarImage url={car} />
                            </a>
                        })}
                    </div>

                    <div>
                        <button onClick={skipDriver}>Skip</button>&nbsp;&nbsp;
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