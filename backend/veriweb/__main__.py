import uvicorn

from veriweb.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run("veriweb.app:app", host=settings.api_host, port=settings.api_port, access_log=False)


if __name__ == "__main__":
    main()
