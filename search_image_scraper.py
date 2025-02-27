import time
import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from PIL import Image
import imagehash
import re
from itertools import permutations
import unicodedata


# Check if all required arguments are provided
def args_check(args_dict):
    for name, value in args_dict.items():
        if value is None:
            raise ValueError(f"Missing argument: {name}, make sure all required arguments are provided")
      

# In cases where we want to continue downloading images, we pick up where we left with the highest number to ensure consistency and that the images are being appended
def track_current(output_dir, query):
    pattern = re.compile(rf"{query}-(\d+)\.jpg")
    numbers = [
        int(pattern.match(file).group(1))
        for file in os.listdir(output_dir)
        if pattern.match(file)
    ]

    return max(numbers, default=0)  # Return highest number, or 0 if no matches


def unwanted_keywords_check(text, keywords):
    # Normalize both the text and keywords
    normalized_text = normalize(text.lower())
    normalized_keywords = [normalize(keyword.lower()) for keyword in keywords]

    # Create a regex pattern for matching any of the normalized keywords
    pattern = (
        r"(?<![a-zA-Z0-9])(?:"
        + "|".join(re.escape(keyword) for keyword in normalized_keywords)
        + r")(?![a-zA-Z0-9])"
    )

    return bool(re.search(pattern, normalized_text))


def query_match(text, query):
    # Normalize the text and query
    normalized_text = normalize(text.lower())
    normalized_query = normalize(query.lower())

    # Create all combinations of the words in the query
    words = normalized_query.split()  # Split normalized query
    permutations_list = [" ".join(perm) for perm in permutations(words)]

    # Check if any of the query versions matches
    for perm in permutations_list:

        # Allow chars that aren't letters
        flexible_perm = r"[^a-zA-Z0-9]*".join(map(re.escape, perm.split()))
        pattern = r"(?<![a-zA-Z0-9])" + flexible_perm + r"(?![a-zA-Z0-9])"

        if re.search(pattern, normalized_text):
            return True
    return False


# Normalize special chars to their base version
def normalize(text):
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8")


# Check if the image is larger than 100x100
def size_check(img_path):
    try:
        with Image.open(img_path) as img:
            width, height = img.size
            if width > 100 and height > 100:
                return True
            else:
                return False
    except Exception as e:
        print(f"Error checking size for {img_path}: {e}")
        return False


# See if the end of the page was reached
def end_of_page(driver):
    # Get the current page source and find if images are still being loaded
    last_height = driver.execute_script("return document.body.scrollHeight")

    # Scroll to the bottom of the page
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # Wait for new content to load
    time.sleep(6)

    # Get the new page height after scrolling
    new_height = driver.execute_script("return document.body.scrollHeight")

    # Check if the height has changed to see if it's the end
    return new_height == last_height


# Google Image search setup
def setup_driver(driver_path):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    service = Service(driver_path)
    driver = webdriver.Chrome()
    return driver


# Hash check for duplicate images
def duplicate_check(image_path, seen_hashes):
    # Check if the image is a duplicate based on its hash
    try:
        img = Image.open(image_path)
        hash_value = imagehash.phash(img)
        hash_str = str(hash_value)

        if hash_str in seen_hashes:
            return True
        seen_hashes.add(hash_str)
        return False
    except Exception as e:
        return True


# Hash to account for images already in dir, so there won't be duplicates
def previous_hashes(output_dir):
    hashes = set()
    valid = {".jpg", ".jpeg", ".png"}
    for file in os.listdir(output_dir):
        file_path = os.path.join(output_dir, file)

        if not any(file.lower().endswith(ext) for ext in valid):
            continue  # Skip non-images
        try:
            with Image.open(file_path) as img:
                hash_value = imagehash.phash(img)
                hashes.add(str(hash_value))
        except:
            continue
    return hashes


# Find the outermost wrapping div with the needed data-lpage
def find_top_div(element):
    current = element
    while current:
        if current.name == "div" and current.get(
            "data-lpage"
        ):  # Check for data-lpage attribute
            return current
        current = current.find_parent("div")  # Move up to the parent
    return None


# Download images from Google Image search
def download_images(query = None, num_images = None, output_dir = None, driver_path = None, unwanted_keywords = [], smart_mode = True):
    
    args_check({
        "query": query, 
        "num_images": num_images, 
        "output_dir": output_dir, 
        "driver_path": driver_path})
    
    driver = setup_driver(driver_path)

    # Open Google image search
    driver.get(f"https://www.google.com/search?q={query}&tbm=isch")
    time.sleep(2)

    # Track seen urls to prevent redownloading the same image
    seen_urls = set()
    # Track seen hashes to prevent duplicates
    seen_hashes = set()

    # Initialize counters
    added_count, removed_count_dup, removed_count_small, er, remember = 0, 0, 0, 0, 0
    track = track_current(output_dir, query)

    while added_count < num_images:
        image_urls = set()

        # Check if we've reached the end of the results
        if end_of_page(driver):
            print("End of image results reached or no more images to load.")
            break

        # Find all image elements and extract their URLs
        soup = BeautifulSoup(driver.page_source, "html.parser")
        images = soup.find_all("img")

        for img in images:
            alt_text = img.get("alt", "").lower()
            src = img.get("src")

            if src in seen_urls:  # Skip if we've seen this image before
                continue

            seen_urls.add(src)  # Image now seen

            # Find the outermost wrapping div with data-lpage
            outer_div = find_top_div(img)
            # Extract data-lpage
            data_lpage = outer_div.get("data-lpage", "").lower() if outer_div else ""

            # Check if unwanted keywords are in alt text
            if unwanted_keywords_check(alt_text, unwanted_keywords):
                continue
            # Check if the query is in common descriptors
            if query_match(alt_text, query) or query_match(data_lpage, query):
                image_urls.add(src)

        for i, url in enumerate(image_urls):
            try:
                img_data = requests.get(url).content
                img_path = os.path.join(output_dir, f"{query}-{i+track+1}.jpg")

                with open(img_path, "wb") as f:
                    f.write(img_data)

                # Check for image size validity
                if not size_check(img_path):
                    removed_count_small += 1
                    os.remove(img_path)
                    track -= 1
                    continue

                # Check for duplicates
                if duplicate_check(img_path, seen_hashes):
                    removed_count_dup += 1
                    os.remove(img_path)
                    track -= 1
                    continue

                added_count += 1

            except Exception as e:
                er += 1
                track -= 1
            finally:
                remember = i
                if added_count >= num_images:
                    break
        track = track + remember # If we run this loop again, remember where we left off

        # Scroll the page to load more images
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight)")
        time.sleep(2)

    print(f"Error downloading {er} samples")
    print(f"{added_count} images downloaded for {query} query")
    print(
        f"{removed_count_small} images disqualified (smaller than 100x100) and {removed_count_dup} images disqualified (duplicates) while downloading for {query} query"
    )

    driver.quit()


