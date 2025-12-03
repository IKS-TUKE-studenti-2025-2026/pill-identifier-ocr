import easyocr
import os
import numpy as np
from fuzzywuzzy import fuzz
from PIL import Image
import re

# Function to read pill names from the file into a list
def read_pill_names(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        pill_names = [line.strip() for line in file.readlines()]
    return pill_names

# Function to get the folder name from the path (pill name)
def get_real_pill_name(image_path):
    folder_name = os.path.basename(os.path.dirname(image_path))  # Get folder name from image path
    return folder_name

# Function to get the core part of the pill name (first word or core identifier)
def get_pill_core(pill_name):
    return pill_name.split()[0]  # The first word is typically the core part

# Function to clean text by removing special characters and converting to lowercase
def clean_text(text):
    # Remove non-alphanumeric characters except spaces and normalize text to lowercase
    return re.sub(r'[^a-zA-Z0-9\s]', '', text).lower()

# Initialize the EasyOCR reader with Slovak ('sk') and English ('en') support
reader = easyocr.Reader(['en'], gpu=True)

# Directory containing the dataset
dataset_path = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset"

# Path to the pill names file
pill_names_file = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\zoznam_liekov.txt"

# Load the pill names from the file
pill_names_list = read_pill_names(pill_names_file)

# Function to perform OCR on an image
def perform_ocr(image_path):
    image = Image.open(image_path)  # Open the image file using Pillow
    image_np = np.array(image)     # Convert the image to a numpy array
    result = reader.readtext(image_np)  # Perform OCR using EasyOCR
    detected_text = " ".join([text[1] for text in result])  # Extract text from OCR result
    return detected_text

# Function to find the folder based on matched pill name
def find_folder(detected_text, pill_names_list):
    best_match = None
    match_percentage = 0

    for pill_name in pill_names_list:
        # Clean the pill name by removing special characters
        cleaned_pill_name = clean_text(pill_name)

        # Use fuzzy matching to compare pill names with the detected text
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

# Process a single image
def process_image(image_path):
    # Perform OCR to extract text
    detected_text = perform_ocr(image_path)

    # Find the pill name that matches the detected text
    best_match, match_percentage = find_folder(detected_text, pill_names_list)

    if best_match:
        # Find the pill data in the corresponding JSON file
        folder_name = best_match  # Use the matched pill name as folder name
        pill_data = find_pill_data(folder_name)

        if pill_data:
            print(f"Detected Text: {detected_text}")
            print(f"Best Match: {best_match}")
            print(f"Match Percentage: {match_percentage}%")
            print("Pill Data:", pill_data)
        else:
            print(f"Pill data for '{folder_name}' not found.")
    else:
        print("No matching pill name found.")

# Path to the image you want to process
image_path = r'C:\path_to_your_image\image_1.jpg'  # Update with the correct path to your image

# Run the function to process the image
process_image(image_path)
