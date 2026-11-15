import cv2


def open_camera(index: int, width: int = 1280, height: int = 720) -> cv2.VideoCapture:
    """Open a camera asking for width x height and print what it actually delivers."""
    # CAP_DSHOW opens much faster than the default backend on Windows.
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Camera {index} not available (in use by another process or not connected).")
    # Many webcams only reach 720p at 30 fps in MJPG; the default YUY2 drops to 5-10 fps.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    got = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    print(f"Camera {index}: {got[0]}x{got[1]} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps (asked {width}x{height})")
    return cap
