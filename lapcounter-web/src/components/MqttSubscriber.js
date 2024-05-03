import { useState, useEffect } from 'react';
import mqtt from 'mqtt';


const MqttSubscriber = ({ mqttHost, onIncomingMessage, debug }) => {

    const [client, setClient] = useState(null);
    //might want to useRef instead of useState... see websockets code

    useEffect(() => {
        if (debug) { console.log("!!! mqtt_CONNECT"); }

        // do we need to check if client is already connected?
        setClient(mqtt.connect(host));  //mqttOption can be optional second argument

        //return () => {
        //    client.close();
        //};    // no idea of something like this is needed
    }, []);


    useEffect(() => {
        if (client) {
            console.log(client)
            client.on('connect', () => {
                if (debug) { console.log('Connected') };
            });
            client.on('error', (err) => {
                console.error('Connection error: ', err);
                client.end();
            });
            client.on('reconnect', () => {
                if (debug) { console.log('Reconnecting') };
            });
            client.on('message', (topic, message) => {
                const payload = { topic, message: message.toString() };
                if (debug) { console.log(payload) };
            });
        }
    }, [client]);

}

export default MqttSubscriber;
