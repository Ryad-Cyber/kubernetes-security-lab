from fastapi import FastAPI
import os
import socket

app = FastAPI(title="Cloud Security Lab", version="1.0.0")

@app.get("/")
def home():
    return {
        "application": "Kubernetes Security Lab",
        "service": "backend",
        "status": "running",
        "hostname": socket.gethostname()
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/info")
def info():
    return {
        "environment": os.getenv("APP_ENV", "lab"),
        "version": "1.0.0"
    }

import psycopg
from fastapi import HTTPException

@app.get("/database")
def database():
    try:
        with psycopg.connect(
            host="postgres.database.svc.cluster.local",
            port=5432,
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=5
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                result = cur.fetchone()
                return {
                    "database": result[0],
                    "connection": "successful",
                    "status": "healthy"
                }
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="Database unavailable")
