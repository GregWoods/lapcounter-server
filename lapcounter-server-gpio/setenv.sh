# run using 'source' command (alias '.')
#    . ./setenv.sh
# ordinarily these environment variables are not available to commands run as sudo.
#   so we must run our script with the "-E" parameter, to preserve these variables

export MQTT_HOSTNAME=127.0.0.1
export MINIMUM_LAP_TIME=3.0

