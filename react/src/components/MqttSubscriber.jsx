import { useState, useEffect } from 'react';
import mqtt from 'mqtt';


const MqttSubscriber = ({ mqttHost, onRaceStateMessage, onRaceControlMessage, onAdminUpdateMessage, clientRef, debug }) => {

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

        if (onRaceControlMessage) {
            client.subscribe('race_control', { qos: 0 }, (error) => {
                if (error) console.log('Subscribe error (race_control)', error);
                else if (debug) console.log('Subscribed to race_control');
            });
        }

        if (onAdminUpdateMessage) {
            client.subscribe('admin_update', { qos: 0 }, (error) => {
                if (error) console.log('Subscribe error (admin_update)', error);
                else if (debug) console.log('Subscribed to admin_update');
            });
        }

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
            const parsed = JSON.parse(message.toString());
            if (topic === 'race_state' && onRaceStateMessage) {
                onRaceStateMessage(parsed);
            }
            if (topic === 'race_control' && onRaceControlMessage) {
                onRaceControlMessage(parsed);
            }
            if (topic === 'admin_update' && onAdminUpdateMessage) {
                onAdminUpdateMessage(parsed);
            }
        });
    }, [client]); // eslint-disable-line react-hooks/exhaustive-deps

    return null;
}

export default MqttSubscriber;
