# face_recognition_models/models.py

def get_model(model_name="hog"):
    """
    Return a face recognition model type.
    'hog' = faster, CPU friendly
    'cnn' = more accurate, GPU recommended
    """
    import face_recognition_models

    if model_name not in ["hog", "cnn"]:
        raise ValueError("Model name must be 'hog' or 'cnn'")
    
    return face_recognition_models.__dict__.get(model_name)
