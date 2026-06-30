import pandas as pd

df = pd.read_csv('C:/kdh/AX_project/backend/data/ibtracs.WP.list.v04r01.csv')

print(df.isnull())
