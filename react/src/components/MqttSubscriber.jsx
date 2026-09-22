import { useState, useEffect } from 'react';
import mqtt from 'mqtt';


const MqttSubscriber = ({ mqttHost, onRaceStateMessage, onRaceControlMessage, onAdminUpdateMessage, clientRef, debug }) => {

    const [client, setClient] = useState(null);

    useEffect(() => {
        if (debug) console.log("Attempting mqtt connection");
        const newClient = mqtt.connect(mqttHost);
        if (clientRef) clientRef.current = newClient;
        setClient(newClient);

        // Every page (LapCounter, RaceControl, NextRace, Results, Admin) mounts its own
        // MqttSubscriber. Without this, navigating away leaves this WebSocket connection
        // and its listeners running forever in the background — each still-open client
        // keeps receiving every race_state/lap message, so an operator's normal page
        // hopping over the course of a meet silently stacks up duplicate live connections
        // until the tab chokes under the accumulated work.
        return () => {
            if (clientRef) clientRef.current = null;
            newClient.end(true);
        };
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

        const handleConnect = () => {
            if (debug) console.log('Mqtt Connected');
        };
        const handleError = (err) => {
            console.error('Mqtt Connection error: ', err);
            client.end();
        };
        const handleReconnect = () => {
            if (debug) console.log('Mqtt Reconnecting');
        };
        const handleMessage = (topic, message) => {
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
        };

        client.on('connect', handleConnect);
        client.on('error', handleError);
        client.on('reconnect', handleReconnect);
        client.on('message', handleMessage);

        return () => {
            client.off('connect', handleConnect);
            client.off('error', handleError);
            client.off('reconnect', handleReconnect);
            client.off('message', handleMessage);
        };
    }, [client]); // eslint-disable-line react-hooks/exhaustive-deps

    return null;
}

export default MqttSubscriber;
