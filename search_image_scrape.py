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


def unwanted_keywords_check(text, keywords):
    # Normalize both the text and keywords
    normalized_text = normalize()(text.lower())
    normalized_keywords = [normalize()(keyword.lower()) for keyword in keywords]

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
        # Allow signs between words
        flexible_perm = r"\s*[\s\-_!.,;?\'\":/&\~\+()<>{}\[\]\|@#$%^=]*\s*".join(
            map(re.escape, perm.split())
        )
        # Allow signs before and after the entire combination
        pattern = (
            r"[\b\s\-_!.,;?\'\":/&\~\+()<>{}\[\]\|@#$%^=]*"
            + flexible_perm
            + r"[\b\s\-_!.,;?\'\":/&\~\+()<>{}\[\]\|@#$%^=]*"
        )
        if re.search(pattern, normalized_text):
            return True
    return False


# Normalize special chars to their base version
def normalize(text):
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8")


def size_check(img_path):
    # Check if the image is larger than 100x100
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
    # Check if the image is a duplicate based on its hash.
    try:
        img = Image.open(image_path)
        hash_value = imagehash.average_hash(img)
        hash_str = str(hash_value)

        if hash_str in seen_hashes:
            return True
        seen_hashes.add(hash_str)
        return False
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return True


# List of unwanted keywords to filter out
unwanted_keywords = []


def find_top_div(element):
    current = element
    while current:
        if current.name == "div" and current.get(
            "data-lpage"
        ):  # Check for data-lpage attribute
            return current
        current = current.find_parent("div")  # Move up to the parent
    return None  # If no matching div is found


# Download images from Google Image search
def download_images(query, num_images, dic, driver_path, unwanted_keywords):

    output_dir = os.path.join(dic, query)

    driver = setup_driver(driver_path)

    # Open Google Image search
    driver.get(f"https://www.google.com/search?q={search_query}&tbm=isch")
    time.sleep(2)

    image_urls = set()
    while len(image_urls) < num_images:
        # Check if we've reached the end of the results
        if end_of_page()(driver):
            print("End of image results reached or no more images to load.")
            break

        # Find all image elements and extract their URLs
        soup = BeautifulSoup(driver.page_source, "html.parser")
        images = soup.find_all("img")

        for img in images:
            alt_text = img.get("alt", "").lower()
            src = img.get("src")

            # Find the outermost wrapping div with data-lpage
            outer_div = find_top_div(img)
            data_lpage = (
                outer_div.get("data-lpage", "").lower() if outer_div else ""
            )  # Extract data-lpage

            if not src:
                continue
            # Check if unwanted keywords are in alt text
            if unwanted_keywords_check()(alt_text, unwanted_keywords):
                continue
            # Check if the query is in common descriptors
            if query_match()(alt_text, query) or query_match()(data_lpage, query):
                image_urls.add(src)
                continue

        # Scroll the page to load more images
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight)")
        time.sleep(2)

    seen_hashes = set()

    added_count, removed_count_dup, removed_count_small, er = 0

    # Download the images
    for i, url in enumerate(image_urls):
        if i >= num_images:
            break
        try:
            img_data = requests.get(url).content
            img_path = os.path.join(output_dir, f"{query}-{i+1}.jpg")
            with open(img_path, "wb") as f:
                f.write(img_data)

            # Check for image size validity
            if not size_check()(img_path):
                os.remove(img_path)
                removed_count_small += 1
                continue

            # Check for duplicates
            if duplicate_check()(img_path, seen_hashes):
                os.remove(img_path)
                removed_count_dup += 1
            else:
                added_count += 1

        except Exception as e:
            er += 1
    print(f"Error downloading {er} samples")
    print(f"{added_count} images downloaded for {query} query")
    print(
        f"{removed_count_small} images disqualified (smaller than 100x100) and another {removed_count_dup} images disqualified (duplicates) before download for {query} query"
    )

    driver.quit()
