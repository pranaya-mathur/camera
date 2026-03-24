
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio, json

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

clients=set()
alerts=[]

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/alerts")
def get_alerts(): return {"alerts": alerts[-100:]}

@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except:
        clients.discard(ws)

async def broadcast(event: dict):
    dead=[]
    for c in clients:
        try:
            await c.send_text(json.dumps(event))
        except:
            dead.append(c)
    for d in dead: clients.discard(d)
