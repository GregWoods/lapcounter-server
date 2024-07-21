import { useState, useEffect } from 'react';
import mqtt from 'mqtt';


const MqttSubscriber = ({ mqttHost, onIncomingLapMessage, debug }) => {

    const [client, setClient] = useState(null);
    //might want to useRef instead of useState... see websockets code

    useEffect(() => {
        if (debug) { console.log("Attempting mqtt connection"); }
        /*
        const mqttOptions = {
            clientId,
            username,
            password,
            clean: true,
            reconnectPeriod: 1000, // ms
            connectTimeout: 30 * 1000, // ms
        }
        */
        //const mqtthost = `${protocol}://${host}:${port}/mqtt`

        // do we need to check if client is already connected?
        setClient(mqtt.connect(mqttHost));  //mqttOptions can be optional second argument

        //return () => {
        //    client.close();
        //};    // no idea of something like this is needed
    }, []);


    useEffect(() => {
        if (client) {

            const topic = "lap";
            const qos = 0;
    
            client.subscribe(topic, { qos }, (error) => {
                if (error) {
                  console.log('Subscribe to topics error', error)
                  return
                }
                console.log(`Subscribe to topics: ${topic}`)
                //setIsSub(true)
            })

            client.on('connect', () => {
                if (debug) console.log('Mqtt Connected');
            });
            client.on('error', (err) => {
                console.error('Mqtt Connection error: ', err);
                client.end();
            });
            client.on('reconnect', () => {
                if (debug) console.log('Mqtt Reconnecting');
            });
            client.on('message', (topic, message) => {
                const payload = { topic, message: message.toString() };
                console.log(`message: ${payload.message}`);
                //if (topic == 'lap') {
                onIncomingLapMessage(JSON.parse(payload.message));
                //}
            });
        }
    }, [client, debug, onIncomingLapMessage]);

    return null;
}

export default MqttSubscriber;
