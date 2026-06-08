"""Diagnose Login 401 - Check DB user record, password hash, and bcrypt verification."""
import pymongo
import bcrypt

def diagnose():
    print("=" * 60)
    print("LOGIN 401 DIAGNOSIS")
    print("=" * 60)

    c = pymongo.MongoClient('mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0')
    db = c.personal_ai_studio

    # 1. Find user by email
    email = "danish@gmail.com"
    user = db.users.find_one({"email": email})
    if not user:
        print(f"[FAIL] User '{email}' NOT FOUND in database!")
        # Check case variants
        for u in db.users.find():
            print(f"  Found user: email='{u.get('email')}', name='{u.get('name')}'")
        return

    print(f"[OK] User found:")
    print(f"  _id:           {user['_id']}")
    print(f"  email:         '{user.get('email')}'")
    print(f"  name:          '{user.get('name')}'")
    print(f"  role:          '{user.get('role')}'")
    print(f"  disabled:      {user.get('disabled')}")
    print(f"  created_at:    {user.get('created_at')}")

    # 2. Check password hash
    pw_hash = user.get("password_hash", "")
    print(f"\n  password_hash: '{pw_hash[:20]}...' (len={len(pw_hash) if pw_hash else 0})")
    
    if not pw_hash:
        print("[FAIL] password_hash is EMPTY or missing!")
        return

    # Check if it's a valid bcrypt hash
    if pw_hash.startswith("$2b$") or pw_hash.startswith("$2a$"):
        print(f"[OK] Hash format is valid bcrypt ({pw_hash[:4]})")
    else:
        print(f"[FAIL] Hash does NOT start with $2b$ or $2a$, got: '{pw_hash[:10]}'")

    # 3. Test various password candidates
    print("\n--- Password Verification Tests ---")
    candidates = [
        "Danish@2026",
        "Danish@21",
        "danish@2026",
        "Danish2026",
        "danish@21",
        "Danish@210303",
        "password",
        "admin",
    ]

    for pw in candidates:
        try:
            result = bcrypt.checkpw(pw.encode('utf-8'), pw_hash.encode('utf-8'))
            status = "MATCH" if result else "no match"
        except Exception as e:
            status = f"ERROR: {e}"
        print(f"  '{pw}' -> {status}")

    # 4. Check if email has whitespace/case issues
    print(f"\n--- Email Analysis ---")
    print(f"  Raw email:     '{user.get('email')}'")
    print(f"  Stripped:      '{user.get('email', '').strip()}'")
    print(f"  Lowered:       '{user.get('email', '').lower().strip()}'")
    
    # Check for duplicate users with similar emails
    print(f"\n--- All Users in DB ---")
    for u in db.users.find():
        h = u.get('password_hash', '')
        print(f"  {u['_id']} | '{u.get('email')}' | hash_len={len(h)} | hash_prefix='{h[:7] if h else 'EMPTY'}'")

if __name__ == '__main__':
    diagnose()
