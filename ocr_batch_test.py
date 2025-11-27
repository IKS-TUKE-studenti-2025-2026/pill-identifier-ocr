import easyocr
import torch
import os
import numpy as np
from fuzzywuzzy import fuzz
from PIL import Image
import csv
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
    # Remove non-alphanumeric characters except spaces
    return re.sub(r'[^a-zA-Z0-9\s]', '', text).lower()

# Initialize the EasyOCR reader with GPU support
reader = easyocr.Reader(['en'], gpu=True)

# Directory containing the dataset
dataset_path = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset"

spravne = 0
nespravne = 0
total = 0

# Path to the pill names file
pill_names_file = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\zoznam_liekov.txt"

# Load the pill names from the file
pill_names_list = read_pill_names(pill_names_file)

# Open CSV file to write results
with open('ocr_results.csv', mode='w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ['Detected Text', 'Guessed Pill Name', 'Pill Core', 'Match Percentage', 'Correct Guess', 'Correct Folder']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    # Write header to CSV file
    writer.writeheader()

    # Process the first 10 folders in the dataset
    folder_count = 0
    for folder_name in os.listdir(dataset_path):
        folder_path = os.path.join(dataset_path, folder_name)

        # Only process folders (pill names)
        if os.path.isdir(folder_path):
            folder_count += 1
            if folder_count > 40:  # Process only the first 10 folders
                break

            print(f"Processing folder: {folder_name}")

            # Loop through images in the folder (assuming there are 3 images per folder)
            for image_file in os.listdir(folder_path):
                if image_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_path = os.path.join(folder_path, image_file)

                    # Open the image using Pillow (PIL)
                    image = Image.open(image_path)

                    # Convert the PIL image to a NumPy array (required by EasyOCR)
                    image_np = np.array(image)

                    # Perform OCR on the image
                    result = reader.readtext(image_np)

                    # Extract detected text
                    detected_text = " ".join([text[1] for text in result])
                    print(f"Detected Text: {detected_text}")

                    # Clean the detected text by removing special characters
                    cleaned_detected_text = clean_text(detected_text)

                    # Initialize match percentage to 0
                    match_percentage = 0
                    best_match = None

                    # Loop through the pill names from the zoznam_liekov.txt file
                    for pill_name in pill_names_list:
                        # Clean the pill name by removing special characters
                        cleaned_pill_name = clean_text(pill_name)

                        # Calculate the fuzzy match percentage between the cleaned detected text and the cleaned pill name
                        current_match_percentage = fuzz.partial_ratio(cleaned_pill_name, cleaned_detected_text)

                        # Check if this is the best match so far
                        if current_match_percentage > match_percentage:
                            match_percentage = current_match_percentage
                            best_match = pill_name

                    # Check if the core part of the pill name is in the detected text
                    pill_core = get_pill_core(best_match)
                    if pill_core.lower() in cleaned_detected_text:
                        # Add a bonus percentage if the core part is found
                        bonus_percentage = 60  # You can adjust this value
                        match_percentage += bonus_percentage
                        print(f"Core part '{pill_core}' found in detected text. Adding {bonus_percentage}% bonus.")

                    # Cap the match percentage at 100% (to avoid going over 100%)
                    if match_percentage > 100:
                        match_percentage = 100

                    # If the match percentage is at least 80%, consider it a correct match
                    correct_guess = "No"
                    if match_percentage >= 80:  # Using a higher threshold to avoid incorrect matches
                        # Check if the best match is the same as the real pill name (folder name)
                        real_pill_name = get_real_pill_name(image_path)
                        if best_match and fuzz.partial_ratio(best_match.lower(), real_pill_name.lower()) > 70:
                            correct_guess = "Yes"
                            spravne += 1

                        print(f"Match found: {best_match} with match percentage: {match_percentage}%")
                    else:
                        print("No match found above 80%")
                        nespravne += 1

                    # "Correct Folder" will always be the real folder name since it's guaranteed to be correct
                    correct_folder = folder_name  # This will always be the correct folder name

                    # Write the results to the CSV file, including the pill core
                    writer.writerow({
                        'Detected Text': detected_text,
                        'Guessed Pill Name': best_match,
                        'Pill Core': pill_core,  # Add Pill Core to CSV
                        'Match Percentage': match_percentage,
                        'Correct Guess': correct_guess,
                        'Correct Folder': correct_folder
                    })

# Calculate precision
total = spravne + nespravne
precision = (spravne / total) * 100 if total > 0 else 0

print("Processing complete. Results saved to 'ocr_results.csv'.")
print(f"Total Correct Guesses: {spravne}")
print(f"Precision: {precision:.2f}%")
