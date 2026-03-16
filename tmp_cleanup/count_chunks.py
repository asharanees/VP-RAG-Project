import boto3

table = boto3.resource('dynamodb', region_name='us-east-1').Table('vp-rag-project-rag-chunks')
scan = table.scan(Select='COUNT')
count = scan.get('Count', 0)
while 'LastEvaluatedKey' in scan:
    scan = table.scan(Select='COUNT', ExclusiveStartKey=scan['LastEvaluatedKey'])
    count += scan.get('Count', 0)
print(count)
