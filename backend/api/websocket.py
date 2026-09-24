"""Telemetri real-time lewat WebSocket."""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import cfg
from ..shutdown import SHUTTING_DOWN
from ..state_manager import state_mgr
from ..audio_engine import audio_player
from ..video.capture import video_service

router = APIRouter()


# --- WEBSOCKET FOR REAL-TIME TELEMETRY (<10ms) ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        text_data = json.dumps(data)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text_data)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while not SHUTTING_DOWN.is_set():
            telemetry = state_mgr.get_telemetry()
            telemetry["fps"] = round(video_service.fps, 1)
            telemetry["audio_muted"] = audio_player.is_muted
            # Dimensi sebenarnya, supaya overlay canvas sejajar walau kamera
            # mengabaikan resolusi yang diminta di config.
            telemetry["frame_width"] = video_service.frame_width
            telemetry["frame_height"] = video_service.frame_height
            telemetry["camera"] = video_service.get_camera_status()
            await websocket.send_json(telemetry)
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_SECONDS)
        # Server sedang berhenti: tutup rapi agar uvicorn tidak menunggu
        await websocket.close()
    except (WebSocketDisconnect, asyncio.CancelledError):
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
