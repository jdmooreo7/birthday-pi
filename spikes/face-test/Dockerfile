# Throwaway spike: measure on-device face detection + recognition on the Pi.
FROM python:3.12-slim-bookworm

RUN pip install --no-cache-dir opencv-python-headless==4.10.0.84 numpy==2.1.3

# OpenCV Zoo models (Git LFS files, served from media.githubusercontent.com).
ADD https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx /models/yunet.onnx
ADD https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx /models/sface.onnx
# URL downloads arrive root-only (0600); let the non-root runtime user read them.
RUN chmod 0644 /models/*.onnx

COPY facetest.py /app/facetest.py
WORKDIR /app
ENTRYPOINT ["python", "-u", "facetest.py"]
