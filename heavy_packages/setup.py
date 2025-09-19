from setuptools import setup, find_packages

setup(
    name="heavy_packages",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "dlib==20.0.0",
        "face-recognition==1.3.0",
        "face_recognition_models==0.3.0",
        "numpy==2.2.6",
        "pillow==11.3.0",
        "opencv-python==4.9.0.76",  # optional, if using cv2
    ],
)
