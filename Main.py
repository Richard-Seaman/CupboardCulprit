import time
import math
import os
import grovepi
from picamera import PiCamera
from grovepi import *
from firebase import firebase

# Digital
temp_humidity_port	= 4
led_red_port = 3
led_green_port = 2
ultasonic_port = 5

# Set the pin modes
pinMode(led_green_port, "OUTPUT")
pinMode(led_red_port, "OUTPUT")

# Return the path to the archive folder
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

#Read the temperature & humidty
def read_sensor():
	try:
                [temp,humidity] = grovepi.dht(temp_humidity_port,0)  # 0 for blue sensor
                
                return [temp,humidity]
	
	#Return -1 in case of sensor error
	except IOError as TypeError:
			return [-1,-1]

# Variable/Object definition before entering loop

# Time to wait 
time_between_checks = 5  # main loop delay
time_between_sensor_reads = 10
time_between_sensor_uploads = 40 * 0.5  

# Variables for door open/close
open_distance = 25
door_was_open = False

# Variables/Objects for images
camera = PiCamera() 
image_folder = get_folder("Images")

#Save the initial time
last_read_sensor= int(time.time())
last_uploaded_readings= int(time.time())

# Variables for average readings
# Each genuine reading between uploads will be added to this list
# The average of the values will then be determined and uploaded
# The  the list will be emptied
temperatures = []
humidities = []

# Firebase
firebase = firebase.FirebaseApplication('https://cupboard-culprit.firebaseio.com', None)  # No auth for now
#result = firebase.get('/test', 1)
#result = firebase.post('/testing', 'testValue')
#print(result)

while True:
    
    try:
        
        # Check the distance
        distant = ultrasonicRead(ultasonic_port)
        print(distant,'cm')
        
        # Determine hether door is open or closed
        door_open = False
        if distant >= open_distance:
            door_open = True
            digitalWrite(led_red_port, 1)   # red on
            digitalWrite(led_green_port, 0) # green off
        else:
            digitalWrite(led_red_port, 0)   # red off
            digitalWrite(led_green_port, 1) # green on            
        
        print("Door open: %s" % door_open)
        
        # Check if this is the first time the door was opened, since it was closed
        # If so, take a picture
        if door_open and not door_was_open:
            saved_image_name = take_picture(camera, image_folder)
            print("Image saved: " + saved_image_name)
               
        # Remember door status for next time
        door_was_open = door_open
        
        # If it is time to take the sensor reading
        curr_time_sec=int(time.time())
        curr_time = time.strftime("%Y-%m-%d:%H-%M-%S")
        if curr_time_sec - last_read_sensor > time_between_sensor_reads:
            [temp, humidity]=read_sensor()

            print(("Time:%s\nTemp: %.2f\nHumidity:%.2f %%\n" %(curr_time,temp,humidity)))
            
            # Check if readings are genuine and add to list if they are
            if temp != -1 and temp != 0:
                temperatures.append(temp)
            if humidity != -1 and humidity != 0:
                humidities.append(humidity)
            
            #Update the last read time
            last_read_sensor=curr_time_sec
        
        # Calculate and upload average if sufficient time has passed
        if curr_time_sec - last_uploaded_readings > time_between_sensor_uploads:
        
            # Calculate the averages
            avgTemp = sum(temperatures) / len(temperatures)
            avgHum = sum(humidities) / len(humidities)
            
            # Construct the data to send to Firebase
            # Use epock time as the key
            # Add the average readings, plus a human readable date string
            timeKey = int(time.time())
            data = {'timestamp': curr_time,'temperature': avgTemp, 'humidity': avgHum}
            result = firebase.put('/conditions', timeKey, data)
            
            # Log
            print(("Time:%s\nAverage Temp: %.2f\nAverage Hum: %.2f" %(curr_time,avgTemp, avgHum)))
            
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
digitalWrite(led_red_port,0)
digitalWrite(led_green_port,0)
camera.close
    

