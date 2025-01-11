import yt_dlp
import subprocess
import os
from datetime import datetime
import logging
from typing import Optional

class YouTubeDownloaderError(Exception):
    """Base exception class for YouTubeSegmentDownloader"""
    pass

class InvalidTimestampError(YouTubeDownloaderError):
    """Raised when timestamp format is invalid"""
    pass

class TimestampRangeError(YouTubeDownloaderError):
    """Raised when timestamps are invalid or out of range"""
    pass

class VideoUnavailableError(YouTubeDownloaderError):
    """Raised when video is unavailable or cannot be accessed"""
    pass

class FFmpegError(YouTubeDownloaderError):
    """Raised when FFmpeg encounters an error"""
    pass

class YouTubeSegmentDownloader:
    def __init__(self, output_dir: str = "downloads"):
        """
        Initialize the downloader with an output directory.
        
        Args:
            output_dir (str): Directory where videos will be saved
        """
        self.output_dir = output_dir
        self._setup_logging()
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Verify FFmpeg installation
        self._check_ffmpeg()

    def _setup_logging(self):
        """Configure logging for the application"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('youtube_downloader.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _check_ffmpeg(self):
        """Verify FFmpeg is installed and accessible"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except subprocess.SubprocessError:
            raise FFmpegError("FFmpeg is not installed or not accessible")
        except FileNotFoundError:
            raise FFmpegError("FFmpeg is not installed or not in system PATH")

    def _time_to_seconds(self, time_str: str) -> int:
        """
        Convert time string (HH:MM:SS or MM:SS or SS) to seconds.
        
        Args:
            time_str (str): Time in HH:MM:SS, MM:SS, or SS format
            
        Returns:
            int: Total seconds
            
        Raises:
            InvalidTimestampError: If time format is invalid
        """
        try:
            # Handle empty or invalid input
            if not time_str or not isinstance(time_str, str):
                raise InvalidTimestampError("Timestamp must be a non-empty string")

            time_parts = list(map(int, time_str.split(':')))
            
            if len(time_parts) == 3:
                return time_parts[0] * 3600 + time_parts[1] * 60 + time_parts[2]
            elif len(time_parts) == 2:
                return time_parts[0] * 60 + time_parts[1]
            elif len(time_parts) == 1:
                return time_parts[0]
            else:
                raise InvalidTimestampError("Invalid time format")
                
        except ValueError:
            raise InvalidTimestampError("Invalid time format. Use HH:MM:SS, MM:SS, or SS")
        except Exception as e:
            raise InvalidTimestampError(f"Error parsing timestamp: {str(e)}")

    def _validate_timestamps(self, start_seconds: int, end_seconds: int, duration: float):
        """
        Validate timestamp ranges.
        
        Args:
            start_seconds (int): Start time in seconds
            end_seconds (int): End time in seconds
            duration (float): Video duration in seconds
            
        Raises:
            TimestampRangeError: If timestamps are invalid or out of range
        """
        if start_seconds >= end_seconds:
            raise TimestampRangeError("End time must be greater than start time")
            
        if start_seconds < 0:
            raise TimestampRangeError("Start time cannot be negative")
            
        if end_seconds > duration:
            raise TimestampRangeError(
                f"End time ({end_seconds}s) exceeds video duration ({duration}s)"
            )

    def download_segment(self, url: str, start_time: str, end_time: str, 
                        output_filename: Optional[str] = None) -> str:
        """
        Download a segment of a YouTube video.
        
        Args:
            url (str): YouTube video URL
            start_time (str): Start time in HH:MM:SS, MM:SS, or SS format
            end_time (str): End time in HH:MM:SS, MM:SS, or SS format
            output_filename (str, optional): Custom output filename
            
        Returns:
            str: Path to the downloaded video segment
            
        Raises:
            VideoUnavailableError: If video cannot be accessed
            InvalidTimestampError: If timestamp format is invalid
            TimestampRangeError: If timestamps are out of range
            FFmpegError: If FFmpeg encounters an error
            YouTubeDownloaderError: For other download-related errors
        """
        full_video_path = None
        
        try:
            # Convert time strings to seconds
            start_seconds = self._time_to_seconds(start_time)
            end_seconds = self._time_to_seconds(end_time)
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
            }
            
            # Get video information
            self.logger.info(f"Extracting information from: {url}")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        raise VideoUnavailableError("Could not retrieve video information")
                    
                    video_title = info.get('title')
                    video_ext = info.get('ext')
                    duration = info.get('duration')
                    
                    if not all([video_title, video_ext, duration]):
                        raise VideoUnavailableError("Missing video metadata")
                    
                    # Validate timestamps against video duration
                    self._validate_timestamps(start_seconds, end_seconds, duration)
                    
                    full_video_path = os.path.join(self.output_dir, f"{video_title}.{video_ext}")
                    
                    # Download the full video
                    self.logger.info("Downloading video...")
                    ydl.download([url])
                    
            except yt_dlp.utils.DownloadError as e:
                raise VideoUnavailableError(f"Failed to access video: {str(e)}")
            
            # Generate output filename if not provided
            if not output_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{video_title}_{timestamp}_segment.{video_ext}"
            
            output_path = os.path.join(self.output_dir, output_filename)
            
            # Cut the video using ffmpeg
            self.logger.info("Creating segment with FFmpeg...")
            command = [
                'ffmpeg',
                '-i', full_video_path,
                '-ss', str(start_seconds),
                '-t', str(end_seconds - start_seconds),
                '-c', 'copy',
                '-y',
                output_path
            ]
            
            try:
                result = subprocess.run(command, capture_output=True, check=True, text=True)
                self.logger.info("Segment created successfully")
            except subprocess.CalledProcessError as e:
                raise FFmpegError(f"FFmpeg error: {e.stderr}")
            
            return output_path
            
        except (InvalidTimestampError, TimestampRangeError, VideoUnavailableError, FFmpegError):
            raise
        except Exception as e:
            raise YouTubeDownloaderError(f"Error downloading video segment: {str(e)}")
        finally:
            # Clean up the full video
            if full_video_path and os.path.exists(full_video_path):
                try:
                    os.remove(full_video_path)
                except Exception as e:
                    self.logger.error(f"Error cleaning up temporary file: {str(e)}")

    def __call__(self, url: str, start_time: str, end_time: str, 
                 output_filename: Optional[str] = None) -> str:
        """
        Allow the class to be called directly.
        """
        return self.download_segment(url, start_time, end_time, output_filename)


# # Create a downloader instance
# downloader = YouTubeSegmentDownloader(output_dir="my_downloads")

# # Download a video segment
# try:
#     output_path = downloader.download_segment(
#         url="https://www.youtube.com/watch?v=qGAPokt6Buo",
#         start_time="122:30",  # 1 minute 30 seconds
#         end_time="2:45",    # 2 minutes 45 seconds
#         output_filename="my_clip.mp4"  # Optional
#     )
#     print(f"Video segment downloaded to: {output_path}")
# except InvalidTimestampError as e:
#     print(f"Invalid timestamp format: {e}")
# except TimestampRangeError as e:
#     print(f"Invalid timestamp range: {e}")
# except VideoUnavailableError as e:
#     print(f"Video unavailable: {e}")
# except FFmpegError as e:
#     print(f"FFmpeg error: {e}")
# except YouTubeDownloaderError as e:
#     print(f"Download error: {e}")