# dlib_custom/wrapper.py

def detect_faces_dlib(image_path):
    """
    Detect faces in an image using dlib.
    Returns a list of face rectangles.
    """
    import dlib
    import cv2

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Image not found at {image_path}")

    # Initialize detector
    detector = dlib.get_frontal_face_detector()
    
    # Detect faces
    faces = detector(image, 1)  # 1 = upsample for better accuracy

    # Return list of face rectangles
    return faces
