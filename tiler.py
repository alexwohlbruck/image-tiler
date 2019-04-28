from PIL import Image, ImageFilter
import time
import pyimgur
import colorgram
import math
import os
import glob
import collections

import config

# Setup imgur client
CLIENT_ID = config.imgur_client_id
imgur = pyimgur.Imgur(CLIENT_ID)

SCALE_FACTOR = 4
SUBDIVISIONS = (90, 80)
MAX_DIST_THRESHOLD = 38
COLOR_SAMPLES = 2
IMAGES_PER_PAGE = 100
MAX_IMAGE_DOWNLOADS = IMAGES_PER_PAGE * 20

# OrderedDict with filenames as keys and array of dominant colors as values
dominant_colors = collections.OrderedDict()

subreddit_page_number = 0
num_images_downloaded = 0

def download_images(subreddit, page=0):

    global subreddit_page_number, num_images_downloaded

    # Use imgur api to retrieve lots of images
    gallery = imgur.get_subreddit_gallery(subreddit, page=subreddit_page_number, sort='top', window='all', limit=IMAGES_PER_PAGE)
    subreddit_page_number += 1

    # Save images to tile-images directory
    for image in gallery:
        if callable(getattr(image, "download", None)) and not image.is_animated:

            filename = image.download(name=image.id, path='./tile-images', overwrite=True, size='small_thumbnail')
            
            print(f'Downloaded {num_images_downloaded + 1} {image.id} {image.title[:75] + ("" if len(image.title) <= 75 else "...")}')

            # Extract dominant color from image
            colors = colorgram.extract(filename, COLOR_SAMPLES)
            
            dominant_colors[filename] = colors

            num_images_downloaded += 1

# Find "distance" between rgb values between both colors
# c1: rgb tuple from pixel
# c2: rgb tuple from color extraction
def distance(c1, c2):
    r1,g1,b1 = c1
    r2,g2,b2 = c2
    return math.sqrt((r1 - r2)**2 + (g1 - g2)**2 + (b1 - b2)**2)


# https://gist.github.com/sigilioso/2957026
def resize_and_crop(img, size, crop_type='top'):
    """
    Resize and crop an image to fit the specified size.

    args:
    img: the image to resize.
    size: `(width, height)` tuple.
    crop_type: can be 'top', 'middle' or 'bottom', depending on this
    value, the image will cropped getting the 'top/left', 'middle' or
    'bottom/right' of the image to fit the size.
    raises:
    Exception: if can not open the file in img_path of there is problems
    to save the image.
    ValueError: if an invalid `crop_type` is provided.
    """
    # If height is higher we resize vertically, if not we resize horizontally
    # Get current and desired ratio for the images
    img_ratio = img.size[0] / float(img.size[1])
    ratio = size[0] / float(size[1])
    #The image is scaled/cropped vertically or horizontally depending on the ratio
    if ratio > img_ratio:
        img = img.resize((size[0], int(round(size[0] * img.size[1] / img.size[0]))),
            Image.ANTIALIAS)
        # Crop in the top, middle or bottom
        if crop_type == 'top':
            box = (0, 0, img.size[0], size[1])
        elif crop_type == 'middle':
            box = (0, int(round((img.size[1] - size[1]) / 2)), img.size[0],
                int(round((img.size[1] + size[1]) / 2)))
        elif crop_type == 'bottom':
            box = (0, img.size[1] - size[1], img.size[0], img.size[1])
        else :
            raise ValueError('ERROR: invalid value for crop_type')
        img = img.crop(box)
    elif ratio < img_ratio:
        img = img.resize((int(round(size[1] * img.size[0] / img.size[1])), size[1]),
            Image.ANTIALIAS)
        # Crop in the top, middle or bottom
        if crop_type == 'top':
            box = (0, 0, size[0], img.size[1])
        elif crop_type == 'middle':
            box = (int(round((img.size[0] - size[0]) / 2)), 0,
                int(round((img.size[0] + size[0]) / 2)), img.size[1])
        elif crop_type == 'bottom':
            box = (img.size[0] - size[0], 0, img.size[0], img.size[1])
        else :
            raise ValueError('ERROR: invalid value for crop_type')
        img = img.crop(box)
    else :
        img = img.resize((size[0], size[1]),
            Image.ANTIALIAS)
    # If the scale is the same, we do not need to crop
    return img


def process_tiles(original_filename, subreddit):

    global num_images_downloaded

    original_img = Image.open('./inputs/' + original_filename)

    OUTPUT_SIZE = tuple([SCALE_FACTOR * x for x in original_img.size])
    TILE_SIZE = (int(OUTPUT_SIZE[0] / SUBDIVISIONS[0]), int(OUTPUT_SIZE[1] / SUBDIVISIONS[1]))

    # Scale image to desired size
    original_img = original_img.resize(OUTPUT_SIZE, Image.NEAREST)

    # Scale a smaller version to "pixelated" size
    small_img = original_img.resize(SUBDIVISIONS, Image.NEAREST)

    # Download images and get dominant colors from them
    download_images(subreddit)

    # Iterate through pixels of thumbnail image and find closest matching color from tile colors
    width, height = small_img.size

    for x in range(width):
        image_id_row = []

        for y in range(height):
            # Get pixel color as tuple
            c1 = small_img.getpixel((x,y))

            minimum_filename = list(dominant_colors.keys())[0] # The image filename of first dominant color
            minimum_dist = distance(c1, list(dominant_colors.values())[0][0].rgb) # Initial minimum as first value (Distance of first dominant color)

            for image_filename, colors in dominant_colors.items():
                # Find closest dominant color (minimum distance)

                for c2 in colors:
                    dist = distance(c1, c2.rgb)

                    if (dist < minimum_dist):
                        # TODO:
                        # If there is no match close enough, load more images from imgur
                        # If there are no suitable images after a certain limit, return error to user

                        # Found new closest value
                        minimum_dist = dist
                        minimum_filename = image_filename
            
            if (minimum_dist > MAX_DIST_THRESHOLD and not num_images_downloaded >= MAX_IMAGE_DOWNLOADS):
                # Get more photos
                print('Distance too large, getting more photos')
                return process_tiles(original_filename, subreddit) # Try again with more images
            else:
                # Paste the tile on the final image
                print(f'Color distance is good, adding {minimum_filename} to mosiac - {int(100 * ((x * width + y + 1) / (width * height)))}% progress')
                tile = Image.open(minimum_filename)
                tile = resize_and_crop(tile, TILE_SIZE, 'middle') # Crop each tile image to square
                original_img.paste(tile, (TILE_SIZE[0] * x, TILE_SIZE[1] * y)) # Create resultant image out of cropped tiles

    print('Finished')
    return original_img

def init():
    # Take file name from user
    filename = input('Enter file name: ')
    subreddit = input('Enter subreddit name: ')
    mosaic = process_tiles(filename, subreddit)

    mosaic.show()
    mosaic.save(f'./outputs/{filename}-{subreddit}')

    # Delete downloaded images
    files = glob.glob('./tile-images/*')
    for f in files:
        os.remove(f)

init()
    