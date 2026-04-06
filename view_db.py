import sqlite3
import pandas as pd
import dtale

conn = sqlite3.connect("wordome_v1.db")
df = pd.read_sql_query("SELECT * FROM reviews LIMIT 10;", conn)
print(df)
conn.close()
d = dtale.show(df, subprocess=False)
d.open_browser(host='127.0.0.1')