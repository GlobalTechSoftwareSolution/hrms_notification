# face_recognition_custom/wrapper.py

def detect_faces(image_path):
    """
    Detect faces in an image using face_recognition library.
    Returns a list of (top, right, bottom, left) tuples.
    """
    import face_recognition

    # Load image
    image = face_recognition.load_image_file(image_path)

    # Detect faces
    face_locations = face_recognition.face_locations(image)

    return face_locations
