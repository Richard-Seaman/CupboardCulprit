# Imports
import time, os, stat
import threading
import glob
import math
import grovepi
from grovepi import *
from picamera import PiCamera
from firebase.firebase import FirebaseApplication, FirebaseAuthentication  # authentication & realtime database
from google.cloud import storage  # uploading images
from PIL import Image # reducing size of images prior to upload

# i/o definitions

# Digital
temp_humidity_port	= 4
led_red_port = 3
led_green_port = 2
ultasonic_port = 5

# Set the pin modes
pinMode(led_green_port, "OUTPUT")
pinMode(led_red_port, "OUTPUT")

###########################################
# LOCAL FUNCTIONS

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


# Take a picture and save it in the folder specified
# Add a timestamp to ensure file name is unique
def take_picture(camera, destination_folder):
    image_file_name = str(time.strftime("%Y-%m-%d %H:%M:%S")) + ".jpg"
    camera.capture(destination_folder + image_file_name)
    return image_file_name

# Read the temperature & humidty
def read_sensor():
    try:
        [temp,humidity] = grovepi.dht(temp_humidity_port,0)  # 0 for blue sensor
        
        return [temp,humidity]
    
    #Return -1 in case of sensor error
    except IOError as TypeError:
        return [-1,-1]

# Upload Sensor readings
def upload_sensor_readings(temperature, humidity):
    # Construct the data to send to Firebase
    # Use epock time as the key
    # Add the average readings, plus a human readable date string
    curr_time_sec=int(time.time())
    timeKey = int(time.time())
    data = {'timestamp': curr_time,'temperature': temperature, 'humidity': humidity}
    result = fbApp.put('/conditions', timeKey, data)
    
    # Log
    print("Uploading to firebase:" + str(data))
    #print(data)
    
    return result

# Upload Culboard Culprits
def upload_culprit(imageName):
    # Construct the data to send to Firebase
    # Use epock time as the key
    # Add the image name, plus a human readable date string
    curr_time_sec=int(time.time())
    timeKey = int(time.time())
    data = {'timestamp': curr_time,'imageName': imageName}
    result = fbApp.put('/culprits', timeKey, data)
    
    # Log
    print("Uploading to firebase:")
    print(data)
    
    return result

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

# A function intended to be run as a background service
# Checks for images in the Images folder
# Process and archives any found
def upload_and_archive_images():
    
    # Infinite loop
    while True:
        
        if stop_daemons:
            break
        
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
        time.sleep(time_between_checks_background)

# END LOCAL FUNCTIONS
###########################################

# Variable/Object definition before entering loop

# Time to wait 
time_between_checks = 1  # main loop delay
time_between_checks_background = 60  # delay for background loops
time_between_sensor_reads = 5
time_between_sensor_uploads = 30  
time_between_image_captures = 10  # ignore multiple opens in a row

# Last done times
last_read_sensor = int(time.time())
last_uploaded_readings = int(time.time())
last_image_taken = int(time.time())
last_background_check = int(time.time())

# Variables for maindoor open/close
open_distance = 25
door_was_open = False

# Variables for camera
camera = PiCamera() 

# Variables for average readings
# Each genuine reading between uploads will be added to this list
# The average of the values will then be determined and uploaded
# Then the list will be emptied
temperatures = []
humidities = []

# Firebase App
fbApp = FirebaseApplication('https://cupboard-culprit.firebaseio.com', authentication=None) 

# Firebase Authentication
authentication = FirebaseAuthentication('kS4ytUh5wSkmMJI7s39VicMqsiDn7ghOj3gDh5TH', 'rseamanrpi@gmail.com')
fbApp.authentication = authentication
print (authentication.extra)

# Google Cloud
# Enable storage, using local service account json file
client = storage.Client.from_service_account_json('Cupboard Culprit-900bac054139.json')

# The storage bucket to upload into
bucket = client.get_bucket('cupboard-culprit.appspot.com')
print("Images will be uploaded to bucket:")
print(bucket)

# Folders
imageFolderName = "Images"  # vairable used to ensure same name used below
imageFolder = get_folder(imageFolderName)
archiveFolderName = "Archive"  # vairable used to ensure same name used below
archiveFolder = get_folder(archiveFolderName)

# Background processes
image_processor = threading.Thread(target=upload_and_archive_images)
stop_daemons = False  # if set to True, all daemons will exit their infinte loops on next cycle
image_processor.daemon = True  # won't prevent the program from terminating if still runnning 
image_processor.start()  # start the image processing function on a background thread

while True:
    
    try:
        # Get the current time        
        curr_time_sec=int(time.time())
        
        # Check the distance
        distant = ultrasonicRead(ultasonic_port)
        #print(distant,'cm')
        
        # Determine whether door is open or closed
        door_open = False
        if distant >= open_distance:
            door_open = True
            digitalWrite(led_red_port, 1)   # red on
            digitalWrite(led_green_port, 0) # green off
        else:
            digitalWrite(led_red_port, 0)   # red off
            digitalWrite(led_green_port, 1) # green on            
        
        #print("Door open: %s" % door_open)
                
        # Check if this is the first time the door was opened, since it was closed
        # If so, take a picture
        if door_open and not door_was_open:
            # Make sure sufficient time has passed since the previous capture
            if curr_time_sec - last_image_taken > time_between_image_captures:
                saved_image_name = take_picture(camera, imageFolderName)
                print("Image saved: " + saved_image_name)
                upload_culprit(saved_image_name)
            else:
                print("Image not taken as previous image was too recent.")
               
        # Remember door status for next time
        door_was_open = door_open
        
        # If it is time to take the sensor reading
        curr_time = time.strftime("%Y-%m-%d:%H-%M-%S")
        if curr_time_sec - last_read_sensor > time_between_sensor_reads:
            [temp, humidity]=read_sensor()

            print(("Time:%s  Temp: %.2f  Humidity:%.2f %%" %(curr_time,temp,humidity)))
            
            # Check if readings are genuine and add to list if they are
            if temp != -1 and (temp >= 0.01 or temp <= 0.01):
                temperatures.append(temp)
            if humidity != -1 and (humidity >= 0.01 or humidity <= 0.01):
                humidities.append(humidity)
            
            #Update the last read time
            last_read_sensor=curr_time_sec
        
        # Calculate and upload average if sufficient time has passed
        if curr_time_sec - last_uploaded_readings > time_between_sensor_uploads:
        
            # Make sure we have some readings
            if len(temperatures) > 0 and len(humidities) > 0:
                
                # Calculate the averages
                avgTemp = sum(temperatures) / len(temperatures)
                avgHum = sum(humidities) / len(humidities)
                
                # Upload to firebase
                result = upload_sensor_readings(avgTemp, avgHum)
                
                # Reset the lists
                temperatures = []
                humidities = []
                
                #Update the last read time
                last_uploaded_readings=curr_time_sec
        
        
        #Slow down the loop
        time.sleep(time_between_checks)
        
    except KeyboardInterrupt:
        print("Keyboard Interrupt detected, stopping loop...")
        break
    
# Cleanup
stop_daemons = True
digitalWrite(led_red_port,0)
digitalWrite(led_green_port,0)
camera.close
