from fastapi import FastAPI

app = FastAPI(title="Space Apps Ground API")


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


