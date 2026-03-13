import sqlite3

conn = sqlite3.connect("test.db")
cursor = conn.cursor()

cursor.execute("SELECT id, email, hashed_password FROM user")

rows = cursor.fetchall()

for r in rows:
    print(r)

conn.close()