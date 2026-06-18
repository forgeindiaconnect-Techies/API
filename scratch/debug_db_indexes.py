import pymongo
import time

def debug_db():
    print("Connecting to MongoDB Atlas...")
    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio
    
    print("\n--- Collections ---")
    print(db.list_collection_names())
    
    for col_name in ['datasets', 'rag_indexes', 'users']:
        col = db[col_name]
        print(f"\n--- Collection: {col_name} ---")
        print(f"Document count: {col.count_documents({})}")
        print("Indexes:")
        for idx in col.list_indexes():
            print(f"  {idx['name']}: {idx['key']}")
            
    # Measure find latency
    print("\nMeasuring query latency for user '6a213b5f4f5a5a8a0249f24b'...")
    user_id = '6a213b5f4f5a5a8a0249f24b'
    
    start = time.time()
    datasets = list(db.datasets.find({"user_id": user_id}))
    print(f"db.datasets.find user_id: {len(datasets)} docs in {(time.time() - start)*1000:.2f}ms")
    
    start = time.time()
    indexes = list(db.rag_indexes.find({"user_id": user_id}))
    print(f"db.rag_indexes.find user_id: {len(indexes)} docs in {(time.time() - start)*1000:.2f}ms")

if __name__ == '__main__':
    debug_db()
