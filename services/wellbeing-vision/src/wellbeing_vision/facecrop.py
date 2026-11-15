"""Keep a square crop around the face so the Face Landmarker always sees a large face.

Its internal detector shrinks the whole frame to 128x128: a face under ~15 % of a 1280x720 frame
is not found at all (measured: 0/60 at 130 px, 60/60 with this crop down to 40 px).
YuNet seeds the crop when there is no face yet; afterwards the crop follows the landmarks."""

from pathlib import Path

import cv2
import numpy as np

CROP_PX = 384
MARGIN = 1.6  # crop side = 1.6 x landmark box


class FaceCrop:
    def __init__(self, yunet_path: Path) -> None:
        self.detector = cv2.FaceDetectorYN.create(str(yunet_path), "", (320, 320), 0.6)
        self.box: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 in frame pixels

    def crop(self, frame: np.ndarray) -> tuple[np.ndarray, float, float, float] | None:
        """Return (crop, ox, oy, k): frame (x, y) = crop (u, v) / k + (ox, oy). None if no face."""
        if self.box is None:
            h, w = frame.shape[:2]
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(frame)
            if faces is None:
                return None
            x, y, fw, fh = max(faces, key=lambda f: f[-1])[:4]
            self.box = (x, y, x + fw, y + fh)
        x0, y0, x1, y1 = self.box
        side = max(x1 - x0, y1 - y0) * MARGIN
        ox, oy, k = (x0 + x1 - side) / 2, (y0 + y1 - side) / 2, CROP_PX / side
        # One affine warp: scales and pads with black where the crop leaves the frame.
        crop = cv2.warpAffine(frame, np.float32([[k, 0, -ox * k], [0, k, -oy * k]]), (CROP_PX, CROP_PX))
        return crop, ox, oy, k

    def follow(self, xy: np.ndarray | None) -> None:
        """Track the landmarks (frame pixels); None forces YuNet to search again."""
        self.box = None if xy is None else (*xy.min(axis=0), *xy.max(axis=0))
