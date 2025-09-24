import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_string

# Usage
base64_image = image_to_base64("C:/Users/Abhishek/Desktop/New_folder/HRMS-BACKEND/hrms/images/abhi.jpg")
print(base64_image)