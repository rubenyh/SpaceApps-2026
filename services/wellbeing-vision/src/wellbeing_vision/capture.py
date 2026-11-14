import cv2


def open_camera(index: int) -> cv2.VideoCapture:
    # CAP_DSHOW opens much faster than the default backend on Windows.
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Camera {index} not available (in use by another process or not connected).")
    return cap
