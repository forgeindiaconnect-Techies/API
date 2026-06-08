import pymongo
import time

def monitor():
    print("Monitoring database for deployment startup check...")
    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio
    
    start_time = time.time()
    while time.time() - start_time < 300: # Poll for up to 5 minutes
        idx = db.rag_indexes.find_one({'dataset_id': '6a21567a49dd8906f4ff3e2b'})
        status = idx.get('status')
        error = idx.get('error')
        print(f"[{time.strftime('%H:%M:%S')}] Status: {status}, Error: {error}")
        
        if status == 'error' and 'interrupted' in str(error):
            print("SUCCESS: The new deployment has booted up and successfully reset the stale index status!")
            break
        elif status == 'ready':
            print("Index is ready!")
            break
            
        time.sleep(10)

if __name__ == '__main__':
    monitor()
