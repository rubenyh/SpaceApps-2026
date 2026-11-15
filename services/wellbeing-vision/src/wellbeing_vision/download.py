"""Fetch the model files into models_dir. They are not committed (about 45 MB)."""

import urllib.request
from pathlib import Path

MODEL_URLS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "face_detection_yunet_2023mar.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def download_models(models_dir: Path) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        target = models_dir / name
        if target.exists() and target.stat().st_size > 0:
            print(f"ok      {name}")
            continue
        tmp = target.with_suffix(target.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(target)
        print(f"fetched {name} ({target.stat().st_size // 1024} KiB)")


def model_path(models_dir: Path, name: str) -> Path:
    path = models_dir / name
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run: uv run wellbeing-vision models")
    return path
