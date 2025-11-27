import easyocr
import torch
import os
import numpy as np
from fuzzywuzzy import fuzz
from PIL import Image
import csv

# Function to get the folder name from the path (pill name)
def get_pill_name(image_path):
    folder_name = os.path.basename(os.path.dirname(image_path))  # Get folder name from image path
    return folder_name

# Function to get the core part of the pill name (first word or core identifier)
def get_pill_core(pill_name):
    return pill_name.split()[0]  # The first word is typically the core part

# Initialize the EasyOCR reader with GPU support
reader = easyocr.Reader(['en'], gpu=True)

# Directory containing the dataset
dataset_path = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset"

# Open CSV file to write results
with open('ocr_results.csv', mode='w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ['Pill Name', 'Detected Text', 'Match Percentage']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    # Write header to CSV file
    writer.writeheader()

    # Process all folders in the dataset
    for folder_name in os.listdir(dataset_path):
        folder_path = os.path.join(dataset_path, folder_name)

        # Only process folders (pill names)
        if os.path.isdir(folder_path):
            print(f"Processing folder: {folder_name}")

            # Get the core part of the pill name (e.g., "Amlodipin" from "AMLODIPIN STICHTING 5 mg")
            pill_core = get_pill_core(folder_name)

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

                    # Calculate the fuzzy match percentage between the pill name and the detected text
                    match_percentage = fuzz.partial_ratio(folder_name.lower(), detected_text.lower())

                    # Check if the core part of the pill name is in the detected text
                    pill_core_lower = pill_core.lower()
                    core_found = pill_core_lower in detected_text.lower()

                    # If the core part is found, adjust the match percentage to be at least 70%
                    if core_found and match_percentage < 70:
                        match_percentage = 70  # Boost to 70% if core is found
                        print("Core of the pill found! Boosting match percentage to 70%.")

                    # Write the results to the CSV file
                    writer.writerow({
                        'Pill Name': folder_name,
                        'Detected Text': detected_text,
                        'Match Percentage': match_percentage
                    })

print("Processing complete. Results saved to 'ocr_results.csv'.")
