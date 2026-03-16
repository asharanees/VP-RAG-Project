import boto3

table = boto3.resource('dynamodb', region_name='us-east-1').Table('vp-rag-project-rag-chunks')
deleted = 0
scan = table.scan(ProjectionExpression='chunk_id')
items = scan.get('Items', [])
while True:
    for item in items:
        table.delete_item(Key={'chunk_id': item['chunk_id']})
        deleted += 1
    lek = scan.get('LastEvaluatedKey')
    if not lek:
        break
    scan = table.scan(ProjectionExpression='chunk_id', ExclusiveStartKey=lek)
    items = scan.get('Items', [])
print(f'Deleted {deleted} items')
