## Quick Start
- Install dependencies namely: homebrew, python, docker, uv, pwgen
- Setup `.env` file by copying `.env.example` and renaming it to `.env` and set secret variables to secure values
- Run heartbeat monitor by command depend on your environment: "dev" or "prod". `make $environment`

```shell
# dev
make dev
# prod
make prod
```

### Secret Variables
- PG_PASSWORD
