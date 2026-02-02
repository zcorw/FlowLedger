from fastapi import FastAPI
from dotenv import load_dotenv
from .routers import currency, custom, deposit, expense, file, user, scheduler


# Load environment variables from .env if present
load_dotenv()

app = FastAPI(title="Flow-Ledger API (Baseline)")


@app.get("/v1/healthz")
def healthz():
    return {"ok": True}


app.include_router(currency.router)
app.include_router(custom.router)
app.include_router(user.router)
app.include_router(expense.router)
app.include_router(deposit.router)
app.include_router(file.router)
app.include_router(scheduler.router)
