# Import gcloud
from google.cloud import storage

# Enable storage, using local service account json file
client = storage.Client.from_service_account_json('Cupboard Culprit-900bac054139.json')

# The storage bucket to upload into
bucket = client.get_bucket('cupboard-culprit.appspot.com')
#print(bucket)

# Upload the file
imageBlob = bucket.blob('2018-04-28 10:58:01.jpg')
print(imageBlob)
imageBlob.upload_from_filename(filename='Images/2018-04-28 10:58:01.jpg')