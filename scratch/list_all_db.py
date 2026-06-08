import pymongo

def list_all():
    print("Connecting to MongoDB Atlas...")
    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio
    
    print("\n--- DATASETS ---")
    for d in db.datasets.find():
        print(f"ID: {d['_id']}, Name: {d.get('name')}, File Path: {d.get('file_path')}, Status: {d.get('status')}")
        
    print("\n--- RAG INDEXES ---")
    for idx in db.rag_indexes.find():
        print(f"ID: {idx['_id']}, Dataset ID: {idx.get('dataset_id')}, Status: {idx.get('status')}, Error: {idx.get('error')}")

if __name__ == '__main__':
    list_all()
