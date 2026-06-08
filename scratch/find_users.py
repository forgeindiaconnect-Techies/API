import pymongo

def run():
    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio
    print("--- USERS ---")
    for u in db.users.find():
        print(f"ID: {u['_id']}, Email: {u.get('email')}, Name: {u.get('name')}, Role: {u.get('role')}")

if __name__ == '__main__':
    run()
