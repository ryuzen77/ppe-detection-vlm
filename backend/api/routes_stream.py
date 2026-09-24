"""Aliran video MJPEG."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..config import cfg
from ..shutdown import SHUTTING_DOWN
from ..video.capture import video_service

router = APIRouter()


class GracefulStreamingResponse(StreamingResponse):
    """StreamingResponse that catches asyncio.CancelledError on server shutdown (Ctrl+C)."""
    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass


@router.get("/api/stream")
async def video_stream(request: Request):
    """MJPEG streaming endpoint with graceful client disconnect handling."""
    async def frame_generator():
        try:
            while not SHUTTING_DOWN.is_set():
                if await request.is_disconnected():
                    break
                frame_bytes = video_service.get_latest_jpeg()
                if frame_bytes is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                await asyncio.sleep(cfg.STREAM_INTERVAL_SECONDS)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return GracefulStreamingResponse(
        frame_generator(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
