import requests
import json
import time
from jose import jwt
from datetime import datetime, timedelta
import pymongo
from bson import ObjectId

def run():
    # 1. Generate access token
    secret = "a421a8c63cfbc647ce5c88bdcea2199d802ee8e617da5304e578ebfdb39ee648"
    payload = {
        "sub": "6a213b5f4f5a5a8a0249f24b",
        "type": "access",
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Connect to database
    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio

    # Find the latest dialogs.txt dataset ID
    dataset_doc = db.datasets.find_one({"name": "dialogs.txt"}, sort=[("created_at", -1)])
    if not dataset_doc:
        print("Dataset dialogs.txt not found!")
        return
    dataset_id = str(dataset_doc["_id"])
    print(f"Found dialogs.txt dataset ID: {dataset_id}")

    # Delete existing index(es) for this dataset
    for idx_doc in db.rag_indexes.find({"dataset_id": dataset_id}):
        index_id = str(idx_doc["_id"])
        del_url = f"https://d-ai-7k8h.onrender.com/api/v1/rag/indexes/{index_id}"
        print(f"Deleting existing index {index_id}...")
        res = requests.delete(del_url, headers=headers)
        print("Delete Response:", res.status_code, res.text)

    # 3. Trigger new index creation
    create_url = "https://d-ai-7k8h.onrender.com/api/v1/rag/index"
    body = {
        "name": "dialogs.txt index",
        "dataset_id": dataset_id,
        "embedding_model": "all-MiniLM-L6-v2",
        "chunk_size": 512,
        "chunk_overlap": 50,
        "index_type": "chroma"
    }
    print("Creating new index...")
    res = requests.post(create_url, headers=headers, json=body)
    print("Create Response:", res.status_code, res.text)
    
    if res.status_code != 200:
        print("Failed to trigger indexing!")
        return

    new_index_id = res.json()["id"]
    print(f"New Index ID: {new_index_id}")

    # 4. Monitor DB for status
    print("Waiting for indexing to complete...")
    start_time = time.time()
    while time.time() - start_time < 300:
        idx = db.rag_indexes.find_one({'_id': ObjectId(new_index_id)})
        if not idx:
            print("Index document not found in DB yet...")
            time.sleep(5)
            continue
            
        status = idx.get('status')
        chunk_count = idx.get('chunk_count', 0)
        error = idx.get('error')
        print(f"[{time.strftime('%H:%M:%S')}] Status: {status}, Chunks: {chunk_count}, Error: {error}")
        
        if status == 'ready':
            print("SUCCESS: Index is ready!")
            break
        elif status == 'error':
            print(f"FAILED: Index build failed: {error}")
            break
            
        time.sleep(5)

if __name__ == '__main__':
    run()
