import time, os, stat
import glob
from google.cloud import storage  # for uplaoding images
from PIL import Image # for reducing size of images prior to upload

print("Starting ImageUploader...")

# Enable storage, using local service account json file
client = storage.Client.from_service_account_json('Cupboard Culprit-900bac054139.json')

# The storage bucket to upload into
bucket = client.get_bucket('cupboard-culprit.appspot.com')
print("Images will be uploaded to bucket:")
print(bucket)


# Return the path to the folder
# And create it if it doesn't exist
# os.path methods used from https://docs.python.org/2/library/os.path.html
def get_folder(folder_name):
    # Get the full path of the current file (__file__ is module attribute)
    full_path = os.path.realpath(__file__)
    #print(full_path + "\n")
    # Split between directory and file (head and tail)
    directory, filename = os.path.split(full_path)
    #print("Dir: " + directory + "\nFile: " + filename + "\n")
    # Define folder path
    folder_path = directory + "/" + folder_name + "/"
    #print(folder_path + "\n")
    # Create it if it doesn't exist
    if not os.path.isdir(folder_path):
        os.makedirs(folder_path)
        print(folder_name + " folder created:\n" + folder_path)
    # Return the path to the archive folder
    return folder_path

# Process the image
# - create temporary copy of image at a reduced size
# - upload smaller image to google cloud
# - delete temporary file
# - move original to archive
def process_image(imagePath):
    # Log
    print("Processing image: " + imagePath)
    
    # Create a path for the redcued image
    extension = imagePath.split(".")[1]
    fileName = imagePath.split("/")[-1]
    imageSmallPath = imagePath.split(".")[0] + "-small." + extension
    
    # Make a copy of the image which is smaller
    image = Image.open(imagePath)
    image.thumbnail([500, 500], Image.ANTIALIAS)  # thumbnail maintains aspect ratio                     
    image.save(imageSmallPath, "JPEG")
    #print("image resized")
    
    # Upload the smaller file
    imageBlob = bucket.blob(fileName)
    imageBlob.upload_from_filename(filename=imageSmallPath)
    #print("image uploaded")    
    
    # Move original to archive folder
    os.rename(imagePath, imagePath.replace(imageFolderName, archiveFolderName))
    #print("image moved to archive folder")
    
    # Delete the smaller copy just created
    if os.path.isfile(imageSmallPath):
        os.remove(imageSmallPath)
        #print("temporary image (smaller) deleted")

# Check if the given file is older than the maximum age
# if so, delete it
def delete_file_if_old(path):
    # Get the age of the file (since modified)
    age_in_seconds = time.time() - os.stat(path)[stat.ST_MTIME]
    # Check if older than a week
    delete_after_seconds = 60 * 60 * 24 * 7
    if age_in_seconds > delete_after_seconds:
        if os.path.isfile(path):
            os.remove(path)
            print("Deleted old file: " + path)

# Folders
imageFolderName = "Images"  # vairable used to ensure same name used below
imageFolder = get_folder(imageFolderName)
archiveFolderName = "Archive"  # vairable used to ensure same name used below
archiveFolder = get_folder(archiveFolderName)

# Time to wait between checks
time_between_checks = 30

# Infinite loop
while True:
    
    try:
        print("Checking for images to upload")
        
        # Check for image files to upload
        images = glob.glob(imageFolder + "/*.jpg")
        print("Images found: " + str(len(images)))
                
        # Cycle through all of the images in the image folder
        for imagePath in images:
            
            # Make sure we don't process any of the converted images
            if "-small" in imagePath:
                continue
            
            # Process the image
            process_image(imagePath)            
        
        # Delete any old files in the archive folder        
        archivedImages = glob.glob(archiveFolder + "/*.jpg")
        for archivedImage in archivedImages:
            delete_file_if_old(archivedImage)
        
        #Slow down the loop
        time.sleep(time_between_checks)
        
    except KeyboardInterrupt:
        print("Keyboard Interrupt detected, stopping loop...")
        break
