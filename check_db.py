import sqlite3

conn = sqlite3.connect("test.db")
cursor = conn.cursor()

cursor.execute("SELECT * FROM user")

rows = cursor.fetchall()

for r in rows:
    print(r)

conn.close()