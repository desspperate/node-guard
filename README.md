## Quick Start
- Install dependencies namely: homebrew, python, docker, uv, pwgen
- Setup `.env` file by copying `.env.example` and renaming it to `.env` and set secret variables to secure values
- Run node guard by command depend on your environment: "dev" or "prod". `make $environment`

```shell
# dev
make dev
# prod
make prod
```


1. Пофиксить баг невозможности удаление
2. Написать кворум для отправки уведомлений в тг
3. Написать кворум для исключения нод из кластера 
2, 3 по сути одно и тоже потому, что через CRDT
