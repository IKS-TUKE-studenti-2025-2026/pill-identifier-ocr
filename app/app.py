import os
import easyocr
import numpy as np
from fuzzywuzzy import fuzz
from PIL import Image
import json
import re
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Initialize EasyOCR reader
reader = easyocr.Reader(['en'], gpu=True)

# Path to your dataset and pill names
# Path to the pill names file
pill_names_file = r'C:\Users\fedor\Documents\GitHub\bakalarska_praca\zoznam_liekov.txt'  # Ensure this is correct

# Path to your dataset
dataset_path = r'C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset'  # Ensure this is correct


# Load the pill names from the file
def read_pill_names(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        pill_names = [line.strip() for line in file.readlines()]
    return pill_names

pill_names_list = read_pill_names(pill_names_file)

# Function to clean text by removing special characters and converting to lowercase
def clean_text(text):
    return re.sub(r'[^a-zA-Z0-9\s]', '', text).lower()

# Function to perform OCR on an image
def perform_ocr(image_path):
    image = Image.open(image_path)
    image_np = np.array(image)
    result = reader.readtext(image_np)
    detected_text = " ".join([text[1] for text in result])
    return detected_text

# Function to find the folder based on matched pill name
def find_folder(detected_text, pill_names_list):
    best_match = None
    match_percentage = 0

    for pill_name in pill_names_list:
        cleaned_pill_name = clean_text(pill_name)
        current_match_percentage = fuzz.partial_ratio(cleaned_pill_name, clean_text(detected_text))

        if current_match_percentage > match_percentage:
            match_percentage = current_match_percentage
            best_match = pill_name

    return best_match, match_percentage

# Function to get pill data from the corresponding JSON file
def find_pill_data(folder_name):
    json_file_path = os.path.join(dataset_path, folder_name, 'interactions.json')
    if os.path.exists(json_file_path):
        with open(json_file_path, 'r') as f:
            pill_data = json.load(f)
            return pill_data
    return None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Check if an image file was uploaded
        file = request.files['image']
        
        if file:
            # Create the 'uploads' folder if it doesn't exist
            upload_folder = os.path.join(os.getcwd(), 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            # Save the uploaded image temporarily
            image_path = os.path.join(upload_folder, file.filename)
            file.save(image_path)

            # Perform OCR on the uploaded image
            detected_text = perform_ocr(image_path)
            print(f"Detected Text: {detected_text}")  # Debug: print detected text

            # Find the pill name that matches the detected text
            best_match, match_percentage = find_folder(detected_text, pill_names_list)
            print(f"Best Match: {best_match}, Match Percentage: {match_percentage}")  # Debug: print match details

            if best_match:
                folder_name = best_match
                pill_data = find_pill_data(folder_name)

                if pill_data:
                    return render_template('index.html', detected_text=detected_text, 
                                           best_match=best_match, 
                                           match_percentage=match_percentage, 
                                           pill_data=pill_data)
                else:
                    return render_template('index.html', detected_text=detected_text, 
                                           message="Pill data not found.")
            else:
                return render_template('index.html', detected_text=detected_text, 
                                       message="No matching pill name found.")

    return render_template('index.html')



if __name__ == '__main__':
    app.run(debug=True)
