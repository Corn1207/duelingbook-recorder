"""
youtube_uploader.py

Uploads a video to YouTube using OAuth 2.0.
Stores the token in credentials/youtube_token.json so the user only
authorizes once.
"""

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

BASE_DIR = Path(__file__).parent.parent
CLIENT_SECRET = BASE_DIR / "credentials" / "youtube_client_secret.json"
TOKEN_FILE    = BASE_DIR / "credentials" / "youtube_token.json"


def _get_youtube_service():
    creds = None

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES
            )
            # Opens browser for OAuth consent
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: str,
    thumbnail_path: str = None,
    privacy: str = "private",
    publish_at: str = None,
    progress_callback=None,
) -> str:
    """
    Uploads a video to YouTube.

    Args:
        video_path:      Path to the MP4 file.
        title:           Video title.
        description:     Video description.
        tags:            Comma-separated tags string.
        thumbnail_path:  Optional path to a JPEG thumbnail.
        privacy:         'private', 'unlisted', or 'public'.

    Returns:
        YouTube video URL (https://youtu.be/<id>)
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    youtube = _get_youtube_service()

    status_body = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    # publishAt requires privacyStatus="private" and an RFC 3339 datetime
    if publish_at:
        # Expects "YYYY-MM-DDTHH:MM" from the UI — Lima is UTC-5 (no DST)
        if len(publish_at) == 16:
            publish_at = publish_at + ":00-05:00"
        status_body["publishAt"] = publish_at
        status_body["privacyStatus"] = "private"

    body = {
        "snippet": {
            "title": title or "Yu-Gi-Oh! Replay",
            "description": description or "",
            "tags": tag_list,
            "categoryId": "20",  # Gaming
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status_body,
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)  # 5MB chunks

    logger.info(f"Uploading {video_path} to YouTube...")
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logger.info(f"Upload progress: {pct}%")
            if progress_callback:
                progress_callback(pct)

    video_id = response["id"]
    logger.info(f"Upload complete: {video_id}")

    # Set thumbnail if provided
    if thumbnail_path and Path(thumbnail_path).exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
        ).execute()
        logger.info("Thumbnail set.")

    return f"https://youtu.be/{video_id}"
