import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config.settings import settings
from src.pipeline import AutoPostPipeline, PipelineResult
from src.tiktok.publisher import TikTokPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger("autopost")

app = FastAPI(title="AutoPost AI Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
OUTPUT_DIR = settings.output_path

# Mount static files and output files
app.mount("/static/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output_files")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static_assets")

# In-memory job state & event queues
jobs: Dict[str, Dict] = {}
job_queues: Dict[str, asyncio.Queue] = {}

class GenerateRequest(BaseModel):
    prompt: str
    tone: Optional[str] = "Mysterious & Hook-Driven"
    voice: Optional[str] = "en-US-ChristopherNeural"
    max_scene_duration: Optional[float] = 4.0
    max_scenes: Optional[int] = 5
    max_video_duration: Optional[float] = 30.0
    auto_publish: Optional[bool] = False

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Index file not found</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy():
    p_path = STATIC_DIR / "privacy.html"
    if p_path.exists():
        return HTMLResponse(p_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Privacy Policy</h1><p>AutoPost AI Studio respects your privacy.</p>")

@app.get("/terms", response_class=HTMLResponse)
async def serve_terms():
    t_path = STATIC_DIR / "terms.html"
    if t_path.exists():
        return HTMLResponse(t_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Terms of Service</h1><p>Standard personal terms apply.</p>")

@app.get("/api/status")
async def get_system_status():
    has_gemini = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip() not in ("", "your_gemini_api_key_here"))
    has_tiktok = bool(settings.TIKTOK_ACCESS_TOKEN and settings.TIKTOK_ACCESS_TOKEN.strip() not in ("", "your_user_oauth_access_token_here"))

    # Look up latest completed video if any
    latest_video = None
    if settings.output_path.exists():
        # Find all *_final.mp4 in output subdirectories
        final_mp4s = sorted(
            settings.output_path.glob("*/vid_*_final.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if final_mp4s:
            latest_path = final_mp4s[0]
            folder_id = latest_path.parent.name
            latest_video = {
                "video_id": folder_id,
                "video_url": f"/api/video/{folder_id}",
                "filename": latest_path.name,
                "size_mb": round(latest_path.stat().st_size / (1024 * 1024), 2),
            }

    return {
        "gemini_configured": has_gemini,
        "gemini_model": settings.GEMINI_MODEL,
        "video_model": settings.GOOGLE_VIDEO_MODEL,
        "tiktok_configured": has_tiktok,
        "tiktok_dry_run": settings.TIKTOK_DRY_RUN,
        "tiktok_post_mode": settings.TIKTOK_POST_MODE,
        "default_voice": settings.VOICE_NAME,
        "latest_video": latest_video,
    }

async def run_pipeline_task(job_id: str, req: GenerateRequest):
    queue = job_queues.get(job_id)

    async def progress_callback(stage: str, percent: int, msg: str, meta: Optional[Dict] = None):
        payload = {
            "job_id": job_id,
            "stage": stage,
            "percent": percent,
            "message": msg,
            "meta": meta or {},
        }
        if job_id in jobs:
            jobs[job_id]["stage"] = stage
            jobs[job_id]["percent"] = percent
            jobs[job_id]["last_message"] = msg
            if meta:
                jobs[job_id]["meta"].update(meta)

        if queue:
            await queue.put(payload)

    try:
        pipeline = AutoPostPipeline()
        if req.voice:
            pipeline.tts.voice = req.voice

        prompt_with_tone = f"{req.prompt}. (Tone: {req.tone})"
        result: PipelineResult = await pipeline.run(
            prompt=prompt_with_tone,
            auto_publish=req.auto_publish or False,
            max_scene_duration=req.max_scene_duration or 4.0,
            max_scenes=req.max_scenes or 5,
            max_video_duration=req.max_video_duration or 30.0,
            progress_cb=progress_callback,
        )

        jobs[job_id]["status"] = "COMPLETED"
        jobs[job_id]["result"] = result.model_dump()

        if queue:
            await queue.put({
                "job_id": job_id,
                "stage": "COMPLETED",
                "percent": 100,
                "message": "Complete! Video rendered.",
                "result": result.model_dump(),
            })
    except Exception as e:
        logger.error(f"Pipeline error for job {job_id}: {e}", exc_info=True)
        jobs[job_id]["status"] = "FAILED"
        jobs[job_id]["error"] = str(e)
        if queue:
            await queue.put({
                "job_id": job_id,
                "stage": "FAILED",
                "percent": 100,
                "message": f"Error: {str(e)}",
                "error": str(e),
            })

@app.post("/api/generate")
async def start_generation(req: GenerateRequest, background_tasks: BackgroundTasks):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    import time
    job_id = f"job_{int(time.time())}"
    jobs[job_id] = {
        "job_id": job_id,
        "prompt": req.prompt,
        "status": "PROCESSING",
        "stage": "INITIALIZING",
        "percent": 0,
        "last_message": "Starting pipeline...",
        "meta": {},
        "result": None,
    }
    job_queues[job_id] = asyncio.Queue()

    background_tasks.add_task(run_pipeline_task, job_id, req)
    return {"job_id": job_id, "status": "PROCESSING"}

@app.get("/api/progress/{job_id}")
async def stream_progress(job_id: str):
    if job_id not in job_queues:
        raise HTTPException(status_code=404, detail="Job queue not found")

    queue = job_queues[job_id]

    async def event_generator():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=45.0)
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("stage") in ("COMPLETED", "FAILED"):
                    break
            except asyncio.TimeoutError:
                yield f": heartbeat\n\n"

@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/api/video/{video_id}")
async def stream_video(video_id: str, request: Request):
    """
    Direct video streaming endpoint supporting byte-range requests (HTTP 206) for HTML5 video players.
    """
    target_video = None

    # Check 1: Job ID lookup from in-memory jobs
    if video_id in jobs and jobs[video_id].get("result"):
        vpath = Path(jobs[video_id]["result"].get("video_path", ""))
        if vpath.exists():
            target_video = vpath

    # Check 2: Direct folder lookup in output directory
    if not target_video:
        vid_dir = settings.output_path / video_id
        if vid_dir.exists() and vid_dir.is_dir():
            finals = list(vid_dir.glob("*_final.mp4"))
            if finals:
                target_video = finals[0]
            else:
                mp4s = list(vid_dir.glob("*.mp4"))
                if mp4s:
                    target_video = mp4s[0]

    # Check 3: Look for direct file match in output directory
    if not target_video:
        direct_file = settings.output_path / f"{video_id}.mp4"
        if direct_file.exists():
            target_video = direct_file

    if not target_video or not target_video.exists():
        raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

    file_size = target_video.stat().st_size
    range_header = request.headers.get("Range")

    if range_header:
        # Parse range header: e.g. "bytes=0-1024"
        try:
            byte_range = range_header.replace("bytes=", "").split("-")
            start = int(byte_range[0]) if byte_range[0] else 0
            end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
            start = max(0, min(start, file_size - 1))
            end = max(start, min(end, file_size - 1))
            content_length = (end - start) + 1

            def iterfile():
                with open(target_video, mode="rb") as f:
                    f.seek(start)
                    bytes_left = content_length
                    chunk_size = 1024 * 512  # 512KB chunks
                    while bytes_left > 0:
                        chunk = f.read(min(chunk_size, bytes_left))
                        if not chunk:
                            break
                        bytes_left -= len(chunk)
                        yield chunk

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "video/mp4",
                "Cache-Control": "no-cache",
            }
            return StreamingResponse(iterfile(), status_code=206, headers=headers)
        except Exception as e:
            logger.warning(f"Range streaming fallback: {e}")

    return FileResponse(
        path=str(target_video),
        media_type="video/mp4",
        filename=target_video.name,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        },
    )

@app.post("/api/publish/{job_id}")
async def publish_existing_video(job_id: str):
    if job_id not in jobs or not jobs[job_id].get("result"):
        raise HTTPException(status_code=404, detail="Completed video job not found")

    res = jobs[job_id]["result"]
    video_path = Path(res["video_path"])
    plan = res["plan"]

    publisher = TikTokPublisher()
    pub_result = await publisher.publish_video(
        video_path=video_path,
        title=plan["tiktok_title"],
        caption=plan["tiktok_caption"],
        hashtags=plan["hashtags"],
    )

    jobs[job_id]["result"]["publish_result"] = pub_result.model_dump()
    return pub_result.model_dump()

@app.delete("/api/output/{job_id}")
async def delete_job_output(job_id: str):
    import shutil
    target_dir = None

    # Check if job_id directly matches a folder in output directory
    direct_path = settings.output_path / job_id
    if direct_path.exists() and direct_path.is_dir():
        target_dir = direct_path
    elif job_id in jobs and jobs[job_id].get("result"):
        # Look up via pipeline video_id
        vid_id = jobs[job_id]["result"].get("video_id")
        if vid_id and (settings.output_path / vid_id).exists():
            target_dir = settings.output_path / vid_id

    deleted_count = 0
    if target_dir and target_dir.exists():
        file_count = sum(1 for _ in target_dir.rglob("*") if _.is_file())
        shutil.rmtree(target_dir, ignore_errors=True)
        deleted_count = file_count
        logger.info(f"[CLEANUP] 🗑️ Deleted output directory {target_dir.name} ({file_count} files removed)")

    # Clean in-memory references
    jobs.pop(job_id, None)
    job_queues.pop(job_id, None)

    return {
        "success": True,
        "message": f"Successfully deleted output files ({deleted_count} files removed)",
        "job_id": job_id,
    }

@app.post("/api/output/clean-all")
async def clean_all_outputs():
    import shutil
    total_deleted = 0
    if settings.output_path.exists():
        for item in settings.output_path.iterdir():
            if item.is_dir():
                file_count = sum(1 for _ in item.rglob("*") if _.is_file())
                shutil.rmtree(item, ignore_errors=True)
                total_deleted += file_count
            elif item.is_file():
                item.unlink(missing_ok=True)
                total_deleted += 1

    jobs.clear()
    job_queues.clear()
    logger.info(f"[CLEANUP] 🧹 Cleared entire output directory ({total_deleted} total files removed)")
    return {
        "success": True,
        "message": f"Purged all generated outputs ({total_deleted} files removed)",
    }
