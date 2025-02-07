this is an image scraper from the google search page

this package takes a query,number of images,dictionary destination path,chromdriver path and unwanted keywords as arguments, searches the query, and attempts to download every valid image for the query until it reaches the required number of images.
A valid image is one that has the query in either the alt text or data lpage elements in it's html, and doesn't have any unwanted keyword in those elements, also, it must be bigger than 100x100 in size, the code uses regex to handle the filtering and checks in the elements.
To ensure no images missed, the automation scrolls down until the end of the page/until target is met, and when reaches the end, recognizes and stops.
