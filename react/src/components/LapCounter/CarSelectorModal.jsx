import { useEffect, useState } from 'react';
import CarImage from './CarImage';
import './CarSelectorModal.css';
import {driverSorter} from './lapUtils.js';


const CarSelectorModal = ({ showMe, onClose, carImgListUrl, drivers, setDrivers, driverIdx, setDriverIdx }) => {

    //holds list of car Urls fetched from server
    const [cars, setCars] = useState([]);
    //const [selectedFile, setSelectedFile] = useState(null);

    useEffect(() => {
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
        skipDriver();
    }

    const skipDriver = () => {
        //need to find the index of the next driver on screen
        //  this may not be the next driver in the array
        //  this is hampered a little by the fact that I omitted adding a unique key for each driver, and used index instead!
        const currentDriver = drivers[driverIdx];
        const tmpDrivers = [...drivers].sort(driverSorter);
        const currentDriverSortedIdx = tmpDrivers.findIndex(driver => driver.number === currentDriver.number);

        let nextDriverSortedIdx;
        if (currentDriverSortedIdx === tmpDrivers.length - 1) {
            nextDriverSortedIdx = 0;
        } else {
            nextDriverSortedIdx = currentDriverSortedIdx + 1;
        }
        const nextDriverNumber = tmpDrivers[nextDriverSortedIdx].number;
        const nextDriverIdx = drivers.findIndex(driver => driver.number === nextDriverNumber);

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

    /*
    const handleFileChange = (event) => {
        console.log('handleFileChange 1');
        const apiUri = `${import.meta.env.VITE_HTTP_PROTOCOL}://${import.meta.env.VITE_SERVER_IP_ADDR}:${import.meta.env.VITE_API_PORT}`;
        const file = event.target.files[0];
        setSelectedFile(file);

        const formData = new FormData();
        formData.append('file', file);

        fetch(`${apiUri}/api/upload`, {
            method: 'POST',
            body: formData,
        })
        .then(response => response.json())
        .then(data => {
            console.log('File uploaded successfully:', data);
            // You can add additional logic to handle the response data
        })
        .catch(error => {
            console.error('Error uploading file:', error);
        });
        // You can add additional logic to handle the selected file
    };
    */

    if (cars && showMe) {
        console.log("car selector modal");
        console.dir(drivers);
        console.log(driverIdx);
        setSpotlightMe();

        return (
            <>
            <div className="fullscreenblur"></div>
            <div className="carselectormodal">
                <div className="carcontainer">
                    {cars.map((car, idx) => {
                        return <a className="carimage" key={idx} onClick={() => setCarImage(car)}><CarImage url={car} /></a>
                    })}
                </div>

                <div className="carselectorbuttons">
                    <button onClick={skipDriver}>Skip</button>&nbsp;&nbsp;
                    {/*
                    <button onClick={() => document.getElementById('file-upload').click()}>
                        Upload
                    </button>&nbsp;&nbsp;
                    <input
                        id="file-upload"
                        type="file"
                        accept="image/*"
                        onChange={handleFileChange}
                        style={{ display: 'none' }}
                    />
                    */}

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