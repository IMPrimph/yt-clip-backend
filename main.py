# main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
import os
from typing import Optional
from datetime import datetime
import uuid
import json
from pathlib import Path

# Import our YouTube downloader
from core import YouTubeSegmentDownloader, InvalidTimestampError, TimestampRangeError, VideoUnavailableError, FFmpegError, YouTubeDownloaderError;

app = FastAPI(title="YouTube Clipper API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create downloads directory
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Store job statuses
JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(exist_ok=True)

class ClipRequest(BaseModel):
    url: HttpUrl
    start_time: str
    end_time: str
    filename: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

def save_job_status(job_status: JobStatus):
    """Save job status to file"""
    with open(JOBS_DIR / f"{job_status.job_id}.json", "w") as f:
        json.dump(job_status.dict(), f, default=str)

def process_video_clip(job_id: str, clip_request: ClipRequest):
    """Background task to process video clip"""
    job_status = JobStatus(
        job_id=job_id,
        status="processing",
        created_at=datetime.now()
    )
    save_job_status(job_status)

    try:
        downloader = YouTubeSegmentDownloader(output_dir=str(DOWNLOAD_DIR))
        
        # Generate filename if not provided
        if not clip_request.filename:
            clip_request.filename = f"clip_{job_id}.mp4"

        output_path = downloader.download_segment(
            url=str(clip_request.url),
            start_time=clip_request.start_time,
            end_time=clip_request.end_time,
            output_filename=clip_request.filename
        )

        # Update job status
        job_status.status = "completed"
        job_status.download_url = f"/download/{clip_request.filename}"
        job_status.completed_at = datetime.now()

    except (InvalidTimestampError, TimestampRangeError, VideoUnavailableError, 
            FFmpegError, YouTubeDownloaderError) as e:
        job_status.status = "failed"
        job_status.message = str(e)
        job_status.completed_at = datetime.now()

    except Exception as e:
        job_status.status = "failed"
        job_status.message = f"Unexpected error: {str(e)}"
        job_status.completed_at = datetime.now()

    finally:
        save_job_status(job_status)

@app.post("/api/clips", response_model=JobStatus)
async def create_clip(
    clip_request: ClipRequest,
    background_tasks: BackgroundTasks
):
    """Create a new video clip"""
    job_id = str(uuid.uuid4())
    
    # Schedule the background task
    background_tasks.add_task(process_video_clip, job_id, clip_request)
    
    return JobStatus(
        job_id=job_id,
        status="queued",
        created_at=datetime.now()
    )

@app.get("/api/clips/{job_id}", response_model=JobStatus)
async def get_clip_status(job_id: str):
    """Get status of a clip job"""
    try:
        with open(JOBS_DIR / f"{job_id}.json", "r") as f:
            return JobStatus(**json.load(f))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")

@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download a processed clip"""
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="video/mp4"
    )

# Run with: uvicorn main:app --reload