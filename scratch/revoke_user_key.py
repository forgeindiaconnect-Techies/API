import pymongo
import hashlib

def run():
    client = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = client.personal_ai_studio
    key = 'sk-zz_7W1gwjlYyM2hYpoNo7qaQWI5j35CqSyqlfGiMAUE'
    h = hashlib.sha256(key.encode()).hexdigest()
    
    res = db.api_keys.update_one(
        {'key_hash': h},
        {'$set': {'is_active': False, 'status': 'revoked'}}
    )
    print(f"Key revocation status: matched={res.matched_count}, modified={res.modified_count}")

if __name__ == '__main__':
    run()
