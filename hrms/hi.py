import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://194.238.19.109:9000',
    aws_access_key_id='djangouser',
    aws_secret_access_key='django_secret_key',
    region_name='us-east-1'
)

# List buckets
print(s3.list_buckets())

# Upload a file
s3.upload_file('code.png', 'hrms-media', 'images/code.png')

# List objects
print(s3.list_objects(Bucket='hrms-media'))
