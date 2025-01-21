# For developer use. Generates mock data for testing
#   No sudo here, this is being run in Windows
docker compose --file compose.dev.yaml up --pull always --build --detach
