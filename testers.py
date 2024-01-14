import pymongo
import os
os.environ["MONGOKEY"] = "l6ws7zM0vFplKeTc"
database_key = os.environ["MONGOKEY"]
MCString = "mongodb+srv://salmonkarp:" + database_key + "@cookieskingdomdb.gq6eh6v.mongodb.net/"
print(MCString)
MClient = pymongo.MongoClient(MCString)['CK']
MClient['POs'].delete_many({})