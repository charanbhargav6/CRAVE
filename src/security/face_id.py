"""
CRAVE Security — Face ID (L1.5)
Save to: D:\\CRAVE\\src\\security\\face_id.py

Adaptive face recognition using LBPH (Local Binary Patterns Histograms).
Uses `opencv-contrib-python` natively, NO C++ compile required.
ZERO VRAM impact.

Enrollment:  python -m src.security.face_id --enroll
Verify:      python -m src.security.face_id --verify
"""

import os
import sys
import time
import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger("crave.security.face_id")

# ── Ensure project root in sys.path ──────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
MODEL_PATH = os.path.join(CRAVE_ROOT, "data", "face_lbph_model.yml")
CONFIG_PATH = os.path.join(CRAVE_ROOT, "config", "hardware.json")

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    _CV2 = False
    logger.warning("[FaceID] opencv-contrib-python not installed.")

def _load_config() -> dict:
    defaults = {
        "enabled": True,
        "tolerance": 55.0,  # For LBPH, lower is better. 0 is perfect, >60 is mismatch.
        "adaptive_update_threshold": 35.0,
        "recheck_interval_minutes": 120,
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        face_cfg = cfg.get("face_id", {})
        for k, v in defaults.items():
            face_cfg.setdefault(k, v)
        return face_cfg
    except Exception:
        return defaults


def _get_face_cascade():
    """Load default Haar Cascade for face detection."""
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    return cv2.CascadeClassifier(cascade_path)


def _preprocess_face(face_crop):
    """Normalize size and apply histogram equalization to fix lighting issues."""
    face_norm = cv2.resize(face_crop, (200, 200))
    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    face_eq = clahe.apply(face_norm)
    return face_eq


# ── Enrollment ────────────────────────────────────────────────────────────────

def enroll() -> bool:
    """Manual face enrollment. Captures 60 frames for robust LBPH model."""
    if not _CV2:
        print("❌ Required package missing: opencv-contrib-python")
        return False

    print("\n" + "=" * 50)
    print("  🔐 CRAVE Face ID Enrollment (LBPH)")
    print("=" * 50)
    print("\n  Position your face ~50cm from the camera.")
    print("  Slowly move your head slightly (up/down/left/right).")
    print("  Capturing 60 high-quality frames for maximum accuracy...\n")

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("❌ Cannot open camera.")
        return False

    face_cascade = _get_face_cascade()
    faces_data = []
    labels = []
    
    attempts = 0
    max_attempts = 150

    try:
        time.sleep(1.0)  # Warm up camera

        while len(faces_data) < 60 and attempts < max_attempts:
            ret, frame = cap.read()
            if not ret:
                attempts += 1
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detected_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(100, 100))

            if len(detected_faces) == 1:
                x, y, w, h = detected_faces[0]
                face_crop = gray[y:y+h, x:x+w]
                
                # Apply advanced lighting normalization
                face_ready = _preprocess_face(face_crop)
                
                faces_data.append(face_ready)
                labels.append(1)  # ID 1 is the Master user
                
                # Simple progress bar
                progress = int((len(faces_data) / 60) * 20)
                bar = "█" * progress + "-" * (20 - progress)
                print(f"\r  [{bar}] {len(faces_data)}/60", end="")
                
                time.sleep(0.05)
            elif len(detected_faces) > 1:
                print("\n  ⚠️ Multiple faces detected! Keep it to just you.")

            attempts += 1

    finally:
        cap.release()

    if len(faces_data) < 30:
        print(f"\n❌ Only {len(faces_data)} frames captured (need at least 30). Try again.")
        return False

    print("\n\n  Training the biometric model...")
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces_data, np.array(labels))
    
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    recognizer.save(MODEL_PATH)

    print(f"\n✅ Enrollment complete! Model securely encoded to disk.")
    return True


# ── Verification ──────────────────────────────────────────────────────────────

def verify_face() -> tuple[bool, float]:
    """Single-shot face verification -> (match, confidence)."""
    if not _CV2:
        return False, 100.0

    if not os.path.exists(MODEL_PATH):
        logger.info("[FaceID] Model not found. Run --enroll.")
        return False, 100.0

    config = _load_config()
    tolerance = config["tolerance"]  # Max distance to consider a match

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(MODEL_PATH)
    face_cascade = _get_face_cascade()

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        logger.warning("[FaceID] Cannot open camera.")
        return False, 100.0

    match = False
    best_confidence = 100.0

    try:
        time.sleep(0.3)
        ret, frame = cap.read()
        if not ret or frame is None:
            return False, 100.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detected_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(100, 100))

        if len(detected_faces) == 0:
            return False, 100.0

        # We take the largest face found in the single frame
        largest_face = max(detected_faces, key=lambda f: f[2]*f[3])
        x, y, w, h = largest_face
        face_crop = gray[y:y+h, x:x+w]
        face_ready = _preprocess_face(face_crop)

        label, confidence = recognizer.predict(face_ready)

        # confidence in LBPH is distance (0 = perfect, >60 usually mismatch)
        if label == 1 and confidence <= tolerance:
            match = True
            best_confidence = confidence
            logger.info(f"[FaceID] ✅ Face matched (distance={confidence:.2f}, limit={tolerance})")
            
            # Note: For LBPH adaptive updating, you'd use recognizer.update(new_face_array, labels)
            # but it is more sensitive to poor lighting ruinings models. We omit it for safety.
        else:
            logger.info(f"[FaceID] ❌ Face rejected (distance={confidence:.2f}, limit={tolerance})")

    except Exception as e:
        logger.error(f"[FaceID] Verification error: {e}")

    finally:
        cap.release()

    return match, best_confidence


def preview_camera():
    """Real-time streaming preview to check camera framing, lighting, and live threshold scores."""
    if not _CV2:
        print("❌ OpenCV not installed.")
        return

    config = _load_config()
    tolerance = config["tolerance"]
    
    recognizer = None
    if os.path.exists(MODEL_PATH):
        try:
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.read(MODEL_PATH)
        except Exception as e:
            print(f"Warning: Model could not be loaded for preview: {e}")

    face_cascade = _get_face_cascade()
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print("❌ Cannot open camera.")
        return

    print("\n  ========================================")
    print("  👁️ CRAVE Vision — Live Preview Mode")
    print("  Press 'q' or 'ESC' on the video window to exit.")
    print("  ========================================\n")

    while True:
        ret, frame = cap.read()
        if not ret: break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detected_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(100, 100))

        for (x, y, w, h) in detected_faces:
            color = (0, 0, 255) # Red (Unknown)
            text = "Unknown"
            
            if recognizer:
                face_crop = gray[y:y+h, x:x+w]
                face_ready = _preprocess_face(face_crop)
                label, confidence = recognizer.predict(face_ready)
                
                if label == 1 and confidence <= tolerance:
                    color = (0, 255, 0) # Green (Verified)
                    text = f"Master (Dist: {confidence:.1f})"
                else:
                    text = f"Unknown (Dist: {confidence:.1f})"
                    
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            cv2.putText(frame, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imshow('CRAVE Face ID Preview', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


# ── Background Recheck Daemon ─────────────────────────────────────────────────

class FaceIDDaemon:
    def __init__(self, rbac=None):
        self._rbac = rbac
        self._running = False
        self._thread = None
        self._config = _load_config()

    def start(self):
        if not self._config.get("enabled", True):
            return

        if not _CV2 or not os.path.exists(MODEL_PATH):
            return

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="FaceIDDaemon")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        interval_sec = self._config.get("recheck_interval_minutes", 120) * 60
        self._do_check()

        while self._running:
            for _ in range(int(interval_sec)):
                if not self._running:
                    return
                time.sleep(1)
            self._do_check()

    def _do_check(self):
        matched, distance = verify_face()
        if matched and self._rbac:
            self._rbac.auth_level = max(self._rbac.auth_level, 2)
            self._rbac.touch()
            logger.info(f"[FaceID] Auto-elevated to L2 (distance={distance:.2f})")
        elif not matched and self._rbac:
            if self._rbac.auth_level <= 1:
                self._alert_unknown_face()

    def _alert_unknown_face(self):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id: return
        try:
            import requests
            from datetime import datetime
            text = (f"👁️ *Face ID Alert*\n\nUnknown face detected during periodic check.\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nAuth remains at L1.")
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        except:
            pass


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="CRAVE Face ID Management")
    parser.add_argument("--enroll", action="store_true", help="Enroll your face to the LBPH Model")
    parser.add_argument("--verify", action="store_true", help="Test face verification once")
    parser.add_argument("--status", action="store_true", help="Check enrollment status")
    parser.add_argument("--preview", action="store_true", help="Live camera stream with bounding boxes and thresholds")
    args = parser.parse_args()

    if args.enroll:
        enroll()
    elif args.preview:
        preview_camera()
    elif args.verify:
        matched, dist = verify_face()
        if matched:
            print(f"✅ Face recognized (distance: {dist:.2f})")
        else:
            print(f"❌ Face not recognized (distance: {dist:.2f})")
    elif args.status:
        if os.path.exists(MODEL_PATH):
            print(f"✅ Enrolled: LBPH Model stored at {MODEL_PATH}")
        else:
            print("❌ Not enrolled. Run: python -m src.security.face_id --enroll")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
