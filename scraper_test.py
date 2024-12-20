import pymongo
from dotenv import load_dotenv
import os
import pandas as pd
import sys
from ScraperCode import ScraperCode

class ScraperTester:
    srv = []
    scraperCode = ""
    collectionName = ""
    
    def __init__(self):
        load_dotenv()
        self.srv = os.environ.get('dbLogin')
    
     
    def get_known_pns(self, code):
        client = pymongo.MongoClient(self.srv)
        brandscol = client['P3Systems']['Brands']
        query = {'BRAND' :  {'$in': [ScraperCode.get(code).name]}}
        results = brandscol.find(query)
        pns = {}
        for result in results:
            if result['Partnumber'] not in pns:
                pns[result['Partnumber']] = None
        print(f"Found {len(pns)} brand partnumbers")
        return pns

    def get_release_pns(self, collectionName):
        client = pymongo.MongoClient(self.srv)
        releasescol = client['DevP3Systems'][collectionName]
        query = {'$expr' : {'$gt' : [{'$size' : '$PartNumbers'},0]}}
        results = releasescol.find(query)
        pns = {}
        for result in results:
            for part in result['PartNumbers']:
                if "pn" in part and part['pn'] not in pns:
                    if "ReleaseDate" in result and result['ReleaseDate']:
                        pns[part['pn']] = result['ReleaseDate']
                elif "PartNumber" in part and part['PartNumber'] not in pns:
                    if "ReleaseDate" in result and result['ReleaseDate']:
                        pns[part['PartNumber']] = result['ReleaseDate']
                else:
                    if "PartNumber" in part: 
                        print(f"found duplicate release for {part['PartNumber']}")
                    elif "pn" in part: 
                            print(f"found duplicate release for {part['pn']}")

        print(f"Found {len(pns)} parsed partnumbers")
        return pns


    def compare(self, brandpns, parsedpns):
        withdates = {}
        nodates = {}
        notinbrands = {}
        for pn,value in brandpns.items():
            if pn not in parsedpns:
                nodates[pn] = None
            else:
                withdates[pn] = parsedpns[pn]

        for pn,value in parsedpns.items():
            if pn not in brandpns:
                notinbrands[pn] = value

        print(f"found {len(withdates)} with dates and {len(nodates)} without dates and {len(notinbrands)} that aren't in brands")
        return (withdates,nodates,notinbrands)
        
    def write_csv(self, data_dict, filepath):
        if os.path.exists(filepath):
            os.remove(filepath)
        df = pd.DataFrame(list(data_dict.items()), columns=['partnumber', 'releasedate'])
        df.to_csv(filepath,index=False)

    
    def test(self, code, collectionName):
        knownpns = self.get_known_pns(code)
        parsedpns = self.get_release_pns(collectionName)
        (MatchedFoundPn,NotFoundKownPn,NewUnknownPn) = self.compare(knownpns,parsedpns)

        if len(MatchedFoundPn) > 0:
            self.write_csv(MatchedFoundPn,f'./exports/{ScraperCode.get(code).name}MatchedFoundPn.csv')
            self.write_csv(NewUnknownPn,f'./exports/{ScraperCode.get(code).name}NewUnknownPn.csv')
        if len(NotFoundKownPn) > 0:
            self.write_csv(NotFoundKownPn,f'./exports/{ScraperCode.get(code).name}NotFoundKownPn.csv')
        
    
