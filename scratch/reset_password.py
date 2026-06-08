"""Reset password for danish@gmail.com to Danish@21"""
import pymongo
import bcrypt

def reset():
    print("Connecting to MongoDB Atlas...")
    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio

    user = db.users.find_one({'email': 'danish@gmail.com'})
    if not user:
        print("User danish@gmail.com not found!")
        return

    print(f"Found user: {user.get('name')} (ID: {user['_id']})")

    # Hash the new password
    new_password = "Danish@21"
    salt = bcrypt.gensalt()
    new_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')

    # Verify the new hash works before saving
    verify = bcrypt.checkpw(new_password.encode('utf-8'), new_hash.encode('utf-8'))
    print(f"Pre-save verification: {'PASS' if verify else 'FAIL'}")

    if not verify:
        print("ERROR: Hash verification failed, aborting!")
        return

    # Update in database
    result = db.users.update_one(
        {'email': 'danish@gmail.com'},
        {'$set': {'password_hash': new_hash}}
    )
    print(f"MongoDB update: matched={result.matched_count}, modified={result.modified_count}")

    # Final verification: re-read from DB and check
    updated_user = db.users.find_one({'email': 'danish@gmail.com'})
    stored_hash = updated_user.get('password_hash', '')
    final_check = bcrypt.checkpw(new_password.encode('utf-8'), stored_hash.encode('utf-8'))
    print(f"Post-save verification from DB: {'PASS' if final_check else 'FAIL'}")
    print(f"\nSUCCESS: Password for danish@gmail.com is now 'Danish@21'")

if __name__ == '__main__':
    reset()
