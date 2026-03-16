import boto3
from collections import Counter

t = boto3.resource('dynamodb', region_name='us-east-1').Table('vp-rag-project-rag-chunks')
scan = t.scan(ProjectionExpression='chunk_id, major_section, section_title, section_header, parent_section_header, week', FilterExpression='attribute_not_exists(chunk_text) = :f', ExpressionAttributeValues={':f': False})
items = scan.get('Items', [])
while 'LastEvaluatedKey' in scan:
    scan = t.scan(ProjectionExpression='chunk_id, major_section, section_title, section_header, parent_section_header, week', FilterExpression='attribute_not_exists(chunk_text) = :f', ExpressionAttributeValues={':f': False}, ExclusiveStartKey=scan['LastEvaluatedKey'])
    items.extend(scan.get('Items', []))

maj = Counter((i.get('major_section') or 'MISSING') for i in items)
print('MAJOR SECTION COUNTS')
for k,v in maj.most_common():
    print(f'{k}: {v}')

print('\nSAMPLE CHUNKS (first 20):')
for i in items[:20]:
    print(i.get('week',''), '|', i.get('major_section',''), '|', i.get('section_title',''), '|', i.get('section_header',''))
