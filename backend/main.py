import asyncio
import time
import json
import threading
from pathlib import Path
from contextlib import asynccontextmanager
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import cfg
from detector import detector
from state_manager import state_mgr, TrackState
from vlm_analyzer import vlm_analyzer
from notifier import notifier
from audio_engine import audio_player
from report_manager import report_mgr
from api_monitor import api_monitor

class GracefulStreamingResponse(StreamingResponse):
    """StreamingResponse that catches asyncio.CancelledError on server shutdown (Ctrl+C)."""
    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass

class VideoCaptureService:
    """Manages camera video capture, inference, and MJPEG encoding."""
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.current_frame_bytes = None
        self.lock = threading.Lock()
        self.fps = 0.0
        self.camera_index = cfg.CAMERA_INDEX
        self.use_synthetic = False

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        with self.lock:
            if self.cap and self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass
        print("[VideoCapture] Camera released cleanly.")

    def _init_camera(self):
        print(f"[VideoCapture] Opening camera index {self.camera_index}...")
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print(f"[VideoCapture] Warning: Could not open camera {self.camera_index} with CAP_DSHOW, retrying default backend...")
            self.cap = cv2.VideoCapture(self.camera_index)

        if not self.cap.isOpened():
            print(f"[VideoCapture] Warning: Camera {self.camera_index} not available. Using synthetic test generator.")
            self.use_synthetic = True
        else:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.FRAME_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, cfg.FPS)
            self.use_synthetic = False
            print("[VideoCapture] Camera successfully opened!")

    def _generate_synthetic_frame(self, t: float) -> np.ndarray:
        """Generates a test pattern if no physical camera is plugged in."""
        img = np.zeros((cfg.FRAME_HEIGHT, cfg.FRAME_WIDTH, 3), dtype=np.uint8)
        # Background gradient
        img[:, :] = (30, 30, 35)
        # Draw grid
        for y in range(0, cfg.FRAME_HEIGHT, 40):
            cv2.line(img, (0, y), (cfg.FRAME_WIDTH, y), (40, 40, 45), 1)
        for x in range(0, cfg.FRAME_WIDTH, 40):
            cv2.line(img, (x, 0), (x, cfg.FRAME_HEIGHT), (40, 40, 45), 1)

        # Draw simulated inspection zone
        cv2.rectangle(img, (340, 60), (940, 660), (0, 180, 255), 2)
        cv2.putText(img, "ZONA INSPEKSI K3 (STANDBY)", (360, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2)
        cv2.putText(img, "Kamera fisik belum terhubung - Mode Simulasi Kamera", (360, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
        return img

    def _capture_loop(self):
        self._init_camera()
        prev_time = time.time()

        try:
            while self.is_running:
                frame = None
                if not self.use_synthetic and self.cap and self.cap.isOpened():
                    ret, raw = self.cap.read()
                    if ret and raw is not None:
                        frame = raw
                    else:
                        time.sleep(0.03)
                        continue
                else:
                    frame = self._generate_synthetic_frame(time.time())
                    time.sleep(0.033)

                # Compute FPS
                now = time.time()
                dt = now - prev_time
                prev_time = now
                if dt > 0:
                    self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)

                # Run YOLO Person & Pose Detection
                detections = detector.detect_and_track(frame)

                # Update State Machine & Anti-spam logic
                state_mgr.update_frame_detections(detections)

                # Draw HUD on frame for low-latency visual stream
                annotated_frame = self._draw_hud(frame, detections)

                # Encode to JPEG
                _, buffer = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                with self.lock:
                    self.current_frame_bytes = buffer.tobytes()
        finally:
            if self.cap and self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass

    def _draw_hud(self, frame: np.ndarray, detections) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]

        # 1. Virtual Corridor Masking & Guides
        if cfg.ENABLE_CORRIDOR_FILTER:
            cx1 = int(w * cfg.CORRIDOR_LEFT_RATIO)
            cx2 = int(w * cfg.CORRIDOR_RIGHT_RATIO)

            # Darken side areas to focus subject in corridor
            overlay = out.copy()
            cv2.rectangle(overlay, (0, 0), (cx1, h), (10, 10, 15), -1)
            cv2.rectangle(overlay, (cx2, 0), (w, h), (10, 10, 15), -1)
            cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)

            # Draw vertical neon corridor boundaries
            cv2.line(out, (cx1, 0), (cx1, h), (255, 200, 0), 2)
            cv2.line(out, (cx2, 0), (cx2, h), (255, 200, 0), 2)

            # Corridor title banner
            banner_text = "=== JALUR INSPEKSI K3 (BERDIRI DI TENGAH) ==="
            t_size = cv2.getTextSize(banner_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
            banner_x = cx1 + (cx2 - cx1 - t_size[0]) // 2
            cv2.putText(out, banner_text, (banner_x, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2)

        # 2. Draw inspection horizontal boundary guidelines
        cv2.line(out, (0, cfg.BORDER_MARGIN_TOP_PX), (w, cfg.BORDER_MARGIN_TOP_PX), (0, 140, 255), 1)
        cv2.line(out, (0, h - cfg.BORDER_MARGIN_BOTTOM_PX), (w, h - cfg.BORDER_MARGIN_BOTTOM_PX), (0, 140, 255), 1)

        # 3. Draw person bounding boxes
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            is_inside = getattr(det, 'is_inside_corridor', True)

            if not is_inside:
                # Dimmed gray for people outside the corridor
                color = (130, 130, 130)
                label = f"ID #{det.track_id} | DI LUAR ZONA"
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)
                cv2.putText(out, label, (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            else:
                # Active subject inside corridor: Green if full body, Red if clipped
                color = (0, 255, 0) if det.is_full_body else (0, 69, 255)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                
                label = f"ID #{det.track_id} | {'FULL BODY' if det.is_full_body else 'MUNDUR'}"
                cv2.putText(out, label, (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                if not det.is_full_body:
                    cv2.putText(out, f"! {det.reason}", (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 69, 255), 2)

        # Header info
        cv2.putText(out, f"FPS: {self.fps:.1f} | RTX 4060", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)
        status_text = f"LIGHT: {notifier.current_state}"
        status_color = (0, 255, 0) if notifier.current_state == "GREEN" else ((0, 0, 255) if notifier.current_state == "RED" else (180, 180, 180))
        cv2.putText(out, status_text, (w - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)


        return out

    def get_latest_jpeg(self):
        with self.lock:
            return self.current_frame_bytes

video_service = VideoCaptureService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    video_service.start()
    yield
    video_service.stop()

app = FastAPI(title="PPE Detection VLM Backend", version="1.0.0", lifespan=lifespan)

# Enable CORS for decoupled frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REST ENDPOINTS ---

@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "fps": round(video_service.fps, 1),
        "is_live_gemini": vlm_analyzer.is_live_api(),
        "camera_index": video_service.camera_index,
        "is_synthetic_camera": video_service.use_synthetic
    }

@app.post("/api/reset")
async def reset_tracking():
    state_mgr.reset_all()
    return {"status": "success", "message": "State reset"}

@app.post("/api/config/gemini-key")
async def update_gemini_key(request: Request):
    data = await request.json()
    new_key = data.get("api_key", "").strip()
    if new_key:
        vlm_analyzer.update_api_key(new_key)
        return {"status": "success", "is_live": vlm_analyzer.is_live_api()}
    return {"status": "error", "message": "API key cannot be empty"}

# --- WORKER REPORT & AUDIT ENDPOINTS ---

@app.get("/api/reports")
async def get_worker_reports(limit: int = 50, offset: int = 0, status: str = "all"):
    """Returns paginated worker inspection records with global compliance statistics."""
    data = report_mgr.get_reports(limit=limit, offset=offset, status_filter=status)
    return data

@app.get("/api/reports/snapshots/{filename}")
async def get_worker_snapshot(filename: str):
    """Serves an inspection snapshot crop image for a specific worker."""
    path = report_mgr.get_snapshot_path(filename)
    if path and path.exists():
        return FileResponse(str(path), media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": "Snapshot image not found"})

@app.get("/api/reports/export")
async def export_worker_reports_csv():
    """Generates and downloads a CSV audit report for HSE/K3 compliance."""
    csv_data = report_mgr.export_csv_text()
    today_str = time.strftime("%Y-%m-%d")
    filename = f"laporan_inspeksi_apd_{today_str}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )

# --- API MONITORING & ENGINE MODE ENDPOINTS ---

@app.get("/api/monitoring/status")
async def get_monitoring_status():
    """Returns real-time Gemini Cloud API health, ping latency, and engine mode."""
    return api_monitor.get_status()

@app.post("/api/monitoring/ping")
async def ping_gemini_api():
    """Initiates an on-demand latency test to Google Gemini API."""
    res = vlm_analyzer.ping_api()
    return res

@app.post("/api/config/engine-mode")
async def set_engine_mode(request: Request):
    """Allows operator to toggle between Online (Cloud Gemini) and Offline (100% Local GPU RTX 4060)."""
    data = await request.json()
    mode = data.get("engine_mode", "HYBRID_AUTO")
    new_mode = api_monitor.set_engine_mode(mode)
    return {
        "status": "success",
        "engine_mode": new_mode,
        "is_forced_local": new_mode == "FORCE_LOCAL"
    }

@app.get("/api/stream")
async def video_stream(request: Request):
    """MJPEG streaming endpoint with graceful client disconnect handling."""
    async def frame_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                frame_bytes = video_service.get_latest_jpeg()
                if frame_bytes is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                await asyncio.sleep(0.033)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return GracefulStreamingResponse(
        frame_generator(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            telemetry = state_mgr.get_telemetry()
            telemetry["fps"] = round(video_service.fps, 1)
            await websocket.send_json(telemetry)
            await asyncio.sleep(0.05)  # 20 Hz update rate
    except (WebSocketDisconnect, asyncio.CancelledError):
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# Mount frontend directory if exists
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run("main:app", host=cfg.HOST, port=cfg.PORT, reload=False)
    except KeyboardInterrupt:
        print("\n[Server] Shutdown signal (CTRL+C) received. Server stopped cleanly.")
