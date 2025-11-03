from fastapi import FastAPI
from dotenv import load_dotenv


# Load environment variables from .env if present
load_dotenv()

app = FastAPI(title="Flow-Ledger API (Baseline)")


@app.get("/healthz")
def healthz():
    return {"ok": True}

