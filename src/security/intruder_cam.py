"""
CRAVE Security — Intruder Camera
Save to: D:\\CRAVE\\src\\security\\intruder_cam.py

Captures a photo on failed authentication and sends it to Telegram.
Photo is deleted from disk immediately after upload.
Telegram message is tracked for Ghost Protocol 30-minute auto-deletion.

Usage:
    from src.security.intruder_cam import capture_and_alert
    capture_and_alert(level="L2", attempt=2, token="...", chat_id="...", ghost_tracker=fn)
"""

import os
import sys
import time
import tempfile
import logging
import threading

logger = logging.getLogger("crave.security.intruder_cam")

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    logger.warning("[IntruderCam] opencv-python not installed. Camera capture disabled.")

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


def _capture_frame() -> str | None:
    """
    Opens camera, grabs a single frame, saves to temp JPEG, releases camera.
    Returns the temp file path or None if capture failed.
    Total camera open time: ~500ms.
    """
    if not _CV2_AVAILABLE:
        return None

    cap = None
    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # DirectShow for Windows speed
        if not cap.isOpened():
            logger.error("[IntruderCam] Cannot open camera.")
            return None

        # Give camera 300ms to warm up auto-exposure
        time.sleep(0.3)

        ret, frame = cap.read()
        if not ret or frame is None:
            logger.error("[IntruderCam] Failed to capture frame.")
            return None

        # Save to temp file
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", prefix="crave_intruder_")
        temp_path = temp.name
        temp.close()

        cv2.imwrite(temp_path, frame)
        logger.info(f"[IntruderCam] Frame captured to {temp_path}")
        return temp_path

    except Exception as e:
        logger.error(f"[IntruderCam] Capture error: {e}")
        return None

    finally:
        if cap is not None:
            cap.release()
        try:
            cv2.destroyAllWindows()
        except:
            pass


def _send_photo_telegram(
    photo_path: str,
    caption: str,
    token: str,
    chat_id: str,
    ghost_tracker=None,
) -> bool:
    """
    Sends photo to Telegram via Bot API sendPhoto.
    Tracks the message_id for Ghost Protocol 30-min auto-delete.
    Deletes the local file immediately after successful upload.
    Returns True if sent successfully.
    """
    if not _REQUESTS_AVAILABLE:
        logger.error("[IntruderCam] requests not available.")
        return False

    if not token or not chat_id:
        logger.error("[IntruderCam] Missing Telegram token or chat_id.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    try:
        with open(photo_path, "rb") as photo_file:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": ("intruder.jpg", photo_file, "image/jpeg")},
                timeout=15,
            )

        data = resp.json()
        if data.get("ok"):
            msg_id = data["result"]["message_id"]
            logger.info(f"[IntruderCam] Photo sent to Telegram (msg_id={msg_id})")

            # Track for Ghost Protocol 30-min auto-delete
            if ghost_tracker:
                ghost_tracker(chat_id, msg_id)

            return True
        else:
            logger.error(f"[IntruderCam] Telegram API error: {data}")
            return False

    except Exception as e:
        logger.error(f"[IntruderCam] Failed to send photo: {e}")
        return False

    finally:
        # ALWAYS delete the local file — even if upload fails
        try:
            os.remove(photo_path)
            logger.info(f"[IntruderCam] Local photo deleted: {photo_path}")
        except:
            pass


def capture_and_alert(
    level: str = "L2",
    attempt: int = 1,
    token: str = "",
    chat_id: str = "",
    ghost_tracker=None,
):
    """
    Main entry point. Captures photo + sends to Telegram in a background thread.
    Non-blocking so it doesn't slow down the auth retry loop.

    Args:
        level: Which auth level failed ("L2", "L3", "L4")
        attempt: Which attempt number this is
        token: Telegram bot token
        chat_id: Telegram chat ID
        ghost_tracker: Callable(chat_id, message_id) for Ghost Protocol tracking
    """
    def _worker():
        from datetime import datetime

        photo_path = _capture_frame()
        if not photo_path:
            # Camera unavailable — send text-only alert
            if _REQUESTS_AVAILABLE and token and chat_id:
                try:
                    text_url = f"https://api.telegram.org/bot{token}/sendMessage"
                    caption = (
                        f"🚨 *INTRUDER ALERT* 🚨\n\n"
                        f"Failed {level} authentication\n"
                        f"Attempt: {attempt}\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"⚠️ Camera unavailable — no photo captured"
                    )
                    resp = requests.post(
                        text_url,
                        json={"chat_id": chat_id, "text": caption, "parse_mode": "Markdown"},
                        timeout=10,
                    )
                    data = resp.json()
                    if data.get("ok") and ghost_tracker:
                        ghost_tracker(chat_id, data["result"]["message_id"])
                except:
                    pass
            return

        caption = (
            f"🚨 *INTRUDER ALERT* 🚨\n\n"
            f"Failed {level} authentication\n"
            f"Attempt: {attempt}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📸 Photo captured and will auto-delete in 30 minutes"
        )

        _send_photo_telegram(photo_path, caption, token, chat_id, ghost_tracker)

    thread = threading.Thread(target=_worker, daemon=True, name="IntruderCapture")
    thread.start()
