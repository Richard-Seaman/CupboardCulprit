# Imports
import time, datetime, os, stat
import threading
import glob
import math
import grovepi
import logging
from grovepi import *
from grove_rgb_lcd import *
from picamera import PiCamera
from firebase.firebase import FirebaseApplication, FirebaseAuthentication  # authentication & realtime database
from google.cloud import storage  # uploading images
from PIL import Image # reducing size of images prior to upload


###########################################
# LOCAL FUNCTIONS
 
# Convenience function to both log to file and print to console
def log(message, is_error):
    if is_error:
        logger.error(message)
    else:        
        logger.info(message)
    print(message)        

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
        log(folder_name + " folder created:\n" + folder_path, False)
    # Return the path to the archive folder
    return folder_path

# For programtically creating paths within the same folder
def get_current_dir():
    # Get the full path of the current file (__file__ is module attribute)
    full_path = os.path.realpath(__file__)
    # Split between directory and file (head and tail)
    directory, filename = os.path.split(full_path)
    return directory

# Take a picture and save it in the folder specified
# Add a timestamp to ensure file name is unique
def take_picture(camera, destination_folder):
    image_file_name = str(time.strftime("%Y-%m-%d %H:%M:%S")) + ".jpg"
    camera.capture(destination_folder + "/" + image_file_name)
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
    log("Uploading to firebase:" + str(data), False)
    
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
    log("Uploading to firebase:" + str(data), False)
        
    return result

# Process the image
# - create temporary copy of image at a reduced size
# - upload smaller image to google cloud
# - delete temporary file
# - move original to archive
def process_image(imagePath):
    # Log
    log("Processing image: " + imagePath, False)
    
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
            log("Deleted old file: " + path, False)

# A function intended to be run as a background service
# Checks for images in the Images folder
# Process and archives any found
def upload_and_archive_images():
    
    # Infinite loop
    while True:
        
        if stop_daemons:
            break
        
        log("Checking for images to upload", False)
        
        # Check for image files to upload
        images = glob.glob(imageFolder + "/*.jpg")
        log("Images found: " + str(len(images)), False)
                
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

# Set the background colour of the display
# based on the number of raids today
def set_screen_background(raids):
    if raids >= alarm_count:        
        setRGB(255,0,0)  # red
    elif raids >= warning_count:    
        setRGB(255,165,0)  # orange
    else:  
        setRGB(0,255,0)  # green        

# END LOCAL FUNCTIONS
###########################################

# Set up logger
logger = logging.getLogger("CupboardCulprit")
log_file_name = "CupboardCulprit.log"
log_file_path = get_current_dir() + "/" + log_file_name
logger_handler = logging.FileHandler(log_file_path)
logger_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
logger_handler.setFormatter(logger_formatter)
logger.addHandler(logger_handler)
logger.setLevel(logging.INFO)

log("Starting up...", False)
        
# i/o definitions

# Digital
temp_humidity_port	= 4
led_red_port = 3
led_green_port = 2
ultasonic_port = 5
buzzer_port = 6
button_port = 7

# Set the pin modes
pinMode(led_green_port, "OUTPUT")
pinMode(led_red_port, "OUTPUT")
pinMode(buzzer_port, "OUTPUT")
pinMode(button_port, "INPUT")

# Variable/Object definition before entering loop

# Time to wait 
time_between_checks = 1  # main loop delay
time_between_checks_background = 60  # delay for background loops
time_between_sensor_reads = 60
time_between_sensor_uploads = 60 * 15 
time_between_image_captures = 60  # ignore multiple opens in a row
time_between_display_updates = 5  # sets minimum time each message shown for
delay_before_picture = 0  # delay between door exceeding open distance and picture being taken

# Last done times (initialised to allow some to start immediately)
last_read_sensor = int(time.time()) - time_between_sensor_reads - 1
last_uploaded_readings = int(time.time()) - time_between_sensor_uploads + 60  # wait 60s before first avg calc and upload
last_image_taken = int(time.time())
last_display_update = int(time.time()) - time_between_display_updates - 1
last_date = datetime.date.today()

# Variables for maindoor open/close
open_distance = 50  # closed distance approx 47cm from testing
door_was_open = False
door_open_count = 0
number_of_open_readings_before_action = 3

# Variables for camera
camera_working = False  # convenience flag to prevent program crashing if we know camera is not working
log("Attempting to use camera...", False)
try:
    camera = PiCamera()
    camera_working = True
    log("Camera is working!", False) 
except:
    log("Camera error, image capture and upload disabled.", True)    

# Variables for average readings
# Each genuine reading between uploads will be added to this list
# The average of the values will then be determined and uploaded
# Then the list will be emptied
temperatures = []
humidities = []
current_temperature = 0 # for displaying (init to 0, updated by avgTemp)

# Variables for tracking number of culprits / day
daily_count = 0
warning_count = 2
alarm_count = 4

# Firebase App
log("Initialising Firebase...", False)
fbApp = FirebaseApplication('https://cupboard-culprit.firebaseio.com', authentication=None) 

# Firebase Authentication
authentication = FirebaseAuthentication('kS4ytUh5wSkmMJI7s39VicMqsiDn7ghOj3gDh5TH', 'rseamanrpi@gmail.com')
fbApp.authentication = authentication

# Google Cloud
# Enable storage, using local service account json file
client = storage.Client.from_service_account_json(get_current_dir() + '/Cupboard Culprit-900bac054139.json')

# The storage bucket to upload into
bucket = client.get_bucket('cupboard-culprit.appspot.com')
log("Images will be uploaded to bucket: " + str(bucket), False)

# Local Folders
imageFolderName = "Images"  # vairable used to ensure same name used below
imageFolder = get_folder(imageFolderName)
archiveFolderName = "Archive"  # vairable used to ensure same name used below
archiveFolder = get_folder(archiveFolderName)

# Background processes
image_processor = threading.Thread(target=upload_and_archive_images)
stop_daemons = False  # if set to True, all daemons will exit their infinte loops on next cycle
image_processor.daemon = True  # won't prevent the program from terminating if still runnning 
image_processor.start()  # start the image processing function on a background thread

# Main Loop
while True:
    
    try:
        # Get the current day / time        
        curr_time_sec=int(time.time())
        curr_time = time.strftime("%Y-%m-%d:%H-%M-%S")
        curr_date = datetime.date.today()
        
        # Check the button status
        button_status = digitalRead(button_port)
        if button_status:
            daily_count = 0
            log("Reset button pressed, setting daily_count to 0.", False)
        
        # Reset the daily counter if it's the next day
        if curr_date != last_date:
            daily_count = 0
        
        # Check the distance to the cupboard door
        distant = ultrasonicRead(ultasonic_port)
        #print(distant,'cm')
        
        # Update the display
        if curr_time_sec - last_display_update > time_between_display_updates:
            setText("Raids Today: %d\nTemp:%.2f C" %(daily_count,current_temperature))
            set_screen_background(daily_count)
            last_display_update = curr_time_sec
            
        # Determine whether door is open or closed
        # Note: make sure multiple door opens in a row to rule out scanner error
        door_open = False
        if distant >= open_distance:
	    # Increment the counter and adjust the LEDs
            door_open_count += 1
            digitalWrite(led_red_port, 1)   # red on
            digitalWrite(led_green_port, 0) # green off
	    # if it's not a false reading (multiple in a row)  
            if door_open_count >= number_of_open_readings_before_action:
                door_open = True
            # Buzzer on if too many opens
            if daily_count >= alarm_count:          
                digitalWrite(buzzer_port, 1) # buzzer on            
        else:
	    # reset the door open counter
            door_open_count = 0
            digitalWrite(led_red_port, 0)   # red off
            digitalWrite(led_green_port, 1) # green on            
            digitalWrite(buzzer_port, 0) # buzzer off
        
        #print("Door open: %s" % door_open)
                
        # Check if this is the first time the door was opened, since it was closed
        # If so, take a picture and increment the daily count
        if door_open and not door_was_open:                          
            # Make sure sufficient time has passed since the previous capture
            # (also used to limit daily increments)
            if curr_time_sec - last_image_taken > time_between_image_captures:   
                # Increment the counter
                daily_count += 1             
                # Update display
                setText("Smile Fatty!\nImage captured...")
                set_screen_background(daily_count)                
                # Check if the camera is working
                if camera_working:
                    # Take the picture (after slight delya to allow door open)
                    time.sleep(delay_before_picture)
                    saved_image_name = take_picture(camera, imageFolder)
                    log("Image saved: " + saved_image_name, False)
                    # Upload the image name and timestamp
                    upload_culprit(saved_image_name) 
                else:
                    log("Image not saved as camera not working.", False)
                    # Even though no image, we still want a record of it
                    # Front end will check for "0" and handle accordingly
                    upload_culprit(0)                             
                # Remember the time 
                last_image_taken = curr_time_sec
                last_display_update = curr_time_sec                
            else:
                log("Ignoring door open, too soon after previous.", False)
               
        # Remember door status for next time
        door_was_open = door_open
        
        # If it is time to take the sensor reading
        if curr_time_sec - last_read_sensor > time_between_sensor_reads:
            [temp, humidity]=read_sensor()

            log(("Time:%s  Temp: %.2f  Humidity:%.2f %%" %(curr_time,temp,humidity)), False)
            
            # Check if readings are genuine and add to list if they are
            if temp != -1 and (temp >= 0.01 or temp <= 0.01):
                temperatures.append(temp)
            if humidity != -1 and (humidity >= 0.01 or humidity <= 0.01):
                humidities.append(humidity)            
            
            # Remember the time
            last_read_sensor = curr_time_sec
        
        # Calculate and upload average if sufficient time has passed
        if curr_time_sec - last_uploaded_readings > time_between_sensor_uploads:
        
            # Make sure we have some readings
            if len(temperatures) > 0 and len(humidities) > 0:
                
                # Calculate the averages
                avgTemp = sum(temperatures) / len(temperatures)
                avgHum = sum(humidities) / len(humidities)
                
                # Remember the average temp for dispaying
                current_temperature = avgTemp
                
                # Upload to firebase
                result = upload_sensor_readings(avgTemp, avgHum)
                
                # Reset the lists
                temperatures = []
                humidities = []
                
                # Remember the time
                last_uploaded_readings = curr_time_sec
        
        # Remember the date for next loop        
        last_date = curr_date
        
        #Slow down the loop
        time.sleep(time_between_checks)
        
    except KeyboardInterrupt:
        log("Keyboard Interrupt detected, stopping loop...", False)
        break
    
# Cleanup
log("Cleaning up and terminating...", False)
setText("")
stop_daemons = True
digitalWrite(led_red_port, 0)
digitalWrite(led_green_port, 0)
digitalWrite(buzzer_port, 0)     
setRGB(0,0,0)  
if camera_working:
    camera.close

# Archive the log
os.rename(log_file_path, archiveFolder + "/" + time.strftime("%Y-%m-%d:%H-%M-%S") + " " + log_file_name)
