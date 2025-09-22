import base64

# Path to your image file
image_path = "C:/Users/Abhishek/Desktop/New folder/HRMS-BACKEND/hrms/images/Pavan.jpg"

with open(image_path, "rb") as image_file:
    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

print(encoded_string)
