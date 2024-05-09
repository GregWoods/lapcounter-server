
docker compose --profile dev up --build --detach






# Ditch this... Use a custom docker compose for local use so we don't end up with several identical container running


#cd lapcounter-server-gpio
#docker build -f ./Dockerfile.Mock --platform linux/amd64 -t gregkwoods/lapcounter-server-mocked-gpio:latest .
#docker run --detach --env-file ../.env.local lapcounter-server-mocked-gpio
#cd ..

#cd lapcounter-server-lapdata
#docker build --platform linux/amd64 -t gregkwoods/lapcounter-server-lapdata:latest .
#docker run --detach --env-file ../.env.local lapcounter-server-lapdata
#cd ..
