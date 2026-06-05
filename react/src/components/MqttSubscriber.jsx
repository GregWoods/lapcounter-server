import { useState, useEffect } from 'react';
import mqtt from 'mqtt';


const MqttSubscriber = ({ mqttHost, onRaceStateMessage, clientRef, debug }) => {

    const [client, setClient] = useState(null);

    useEffect(() => {
        if (debug) console.log("Attempting mqtt connection");
        const newClient = mqtt.connect(mqttHost);
        if (clientRef) clientRef.current = newClient;
        setClient(newClient);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps


    useEffect(() => {
        if (!client) return;

        client.subscribe('race_state', { qos: 0 }, (error) => {
            if (error) console.log('Subscribe error', error);
            else if (debug) console.log('Subscribed to race_state');
        });

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
            if (topic === 'race_state' && onRaceStateMessage) {
                onRaceStateMessage(JSON.parse(message.toString()));
            }
        });
    }, [client]); // eslint-disable-line react-hooks/exhaustive-deps

    return null;
}

export default MqttSubscriber;
