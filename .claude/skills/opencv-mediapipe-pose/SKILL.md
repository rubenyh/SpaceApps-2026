---
name: opencv-mediapipe-pose
description: Capture camera frames with OpenCV and run MediaPipe pose landmark detection to produce posture/motion readings. Use when working on camera or pose collectors.
---

# OpenCV + MediaPipe pose (planned)

Status: `opencv-python` and `mediapipe` are not dependencies yet. Add with `uv add opencv-python mediapipe` in `services/onboard-api`. Check MediaPipe wheel support for Python 3.12 on the target OS before adding; commit `uv.lock`.

## Where
- Planned: `services/onboard-api/src/onboard_api/ingestion/camera_collector.py` and `pose.py`.

## Do
- Camera index, resolution and target FPS from settings. `cv2.VideoCapture(index)`; on Windows `cv2.CAP_DSHOW` opens faster.
- Check `cap.isOpened()` and each `ok, frame = cap.read()`. Release in `finally`.
- Convert BGR to RGB before MediaPipe. Use the MediaPipe Tasks `PoseLandmarker` (model `.task` file path from settings; do not commit large models without agreement).
- Store derived values (for example trunk angle, landmark visibility), not raw frames. Raw images of crew are sensitive; do not persist them unless the user asks.
- Low landmark visibility means "no reading", not a zero value.
- Run capture in a thread started from lifespan; drop frames rather than queue unbounded.

## Verify
- Tests on still images in a fixtures dir: known pose gives landmarks; blank image gives no reading.
- Live camera checks need hardware; report if not run.

Docs: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python , https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html
