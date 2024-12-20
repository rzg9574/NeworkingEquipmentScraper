from pymongo import MongoClient
from dotenv import load_dotenv 
import os

def init(dataBaseName, collection = None):
    """
    Initlizes the database 
    Args:
        dataBaseName (str): the name of the database you want to initlize
        collection (str, optional): if you pass in a collection name the program will empty 
                                    that collection before returing the database . Defaults to None.

    Returns:
        pymongo.database.Database: the initlized database 
    """
    load_dotenv()
    dbLogin = os.environ.get('dbLogin')
    client = MongoClient(dbLogin)
    db = client[dataBaseName]
    if collection:
        db.get_collection(collection).delete_many({})
    
    print("DataBase Initalized")

    return db


def clearCollection(db, collection):
    """
    Clears a specific collection
    Args:
        db (pymongo.database.Database): database that has the collection you want to clear
        collection (str): the name of the collection you want to clear
    """
    db.get_collection(collection).delete_many({})
    
     