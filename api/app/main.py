from fastapi import FastAPI
from dotenv import load_dotenv
from .routers import currency


# Load environment variables from .env if present
load_dotenv()

app = FastAPI(title="Flow-Ledger API (Baseline)")


@app.get("/healthz")
def healthz():
    return {"ok": True}


app.include_router(currency.router)
