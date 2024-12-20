from enum import Enum
from Scrapers import arista_scraper
from Scrapers import ruckus_scraper
from Scrapers import cisco_scraper
from Scrapers import hp_scraper
from Scrapers import init_db
import threading
from ScraperCode import ScraperCode
from scraper_test import ScraperTester


class ScraperController: 
    aristaScraper = None
    aristaCollectionName = ""
    ruckusScraper = None
    ruckusCollectionName = ""
    ciscoScraper = None
    ciscoCollectionName = ""
    hpScraper = None
    hpCollectionName = ""
    allScrapers = []
    db = None
    tester = None
    
    def __init__(self, dataBaseName, aristaCollectionName="TestAristaScraper", ruckusCollectionName="TestRuckusScraper", hpCollectionName="TestHPWebScraper", ciscoCollectionName="TestCiscoWebScrapper"):
        """
        Args:
            dataBaseName (str): name of the Database you want to store the results on
            aristaCollectionName (str, optional): name of the collection you want to store the arista results on. Defaults to "TestAristaScraper".
            ruckusCollectionName (str, optional): name of the collection you want to store the ruckus results on. Defaults to "TestRuckusScraper".
            hpCollectionName (str, optional): name of the collection you want to store the hp results on. Defaults to "TestHPWebScraper".
            ciscoCollectionName (str, optional): name of the collection you want to store the cisco results on. Defaults to "TestCiscoWebScrapper".
        """
        self.db = init_db.init(dataBaseName)
        self.aristaScraper = arista_scraper.AristaScraper(aristaCollectionName, self.db)
        self.allScrapers.append(self.aristaScraper)
        self.aristaCollectionName = aristaCollectionName
        self.ruckusScraper = ruckus_scraper.RuckusScraper(ruckusCollectionName, self.db)
        self.allScrapers.append(self.ruckusScraper)
        self.ruckusCollectionName = ruckusCollectionName
        self.ciscoScraper = cisco_scraper.CiscoScraper(ciscoCollectionName, self.db)
        self.allScrapers.append(self.ciscoScraper)
        self.ciscoCollectionName = ciscoCollectionName
        self.hpScraper = hp_scraper.hpScraper(hpCollectionName, self.db)
        self.allScrapers.append(self.hpScraper)
        self.hpCollectionName = hpCollectionName
        
        self.tester = ScraperTester()
        
    def run_all_one_at_a_time(self):
        """
        Runs all the scrapers one at a time 
        """
        for scraper in self.allScrapers:
            print(f"Running {scraper.db_collection}.")
            try:
                scraper.start()
            except Exception as e:
                print(f"Error running {scraper.db_collection}: {e}")
            
    def run_all_threads(self):
        """
        Runs all the scrapers on diffrent threads so you can run all the scrappers at the same time
        """
        threads = []
        for scraper in self.allScrapers:
            init_db.clearCollection(self.db, scraper.db_collection)
            thread = threading.Thread(target=scraper.start, daemon=True)
            threads.append(thread)
            thread.start()
            print(f"Thread for scraper {scraper.db_collection} started.")
        
        for thread in threads:
            thread.join()    
            
    def run_scraper(self, code):
        """
        Runs a spesific scraper based on the code passed in the code is based on the ScrapperCode enum in the ScrapperCode.py file
        
        Args:
            code (str): The string code for the scraper that you want run
        """
        try:
            if code == ScraperCode.ARISTA.value:
                init_db.clearCollection(self.db, self.aristaCollectionName)
                self.aristaScraper.start()
            elif code == ScraperCode.RUCKUS.value:
                init_db.clearCollection(self.db, self.ruckusCollectionName)
                self.ruckusScraper.start()
            elif code == ScraperCode.CISCO.value:
                init_db.clearCollection(self.db, self.ciscoCollectionName)
                self.ciscoScraper.start()
            elif code == ScraperCode.HPE.value:
                init_db.clearCollection(self.db, self.hpCollectionName)
                self.hpScraper.start()
            else:
                print(f"Scraper not found.")
        except Exception as e:
            print(f"Error running {ScraperCode.get(code)}: {e}")
            
    
    def test_scraper(self, code):
        """
        Tests a spesific scraper based on the code passed in the code is based on the ScrapperCode enum in the ScrapperCode.py file
        the Test will create 3 csv files for the respected scraper in the exports folder the
        
        -MatchedFoundPn csv are all the part numbers that the scraper found that are in the Brands database that have known part numbers
        
        -NewUnknowPn csv are all the part numbers that were found by the scraper that were not in the Brands database 
        
        -NotFoundKnownPn csv are all the part numbers that are in the Brands database but were not found by the scraper  
        
        Args:
            code (str): The string code for the scraper that you want run
        """
        try:
            if code == ScraperCode.ARISTA.value:
                self.tester.test(code, self.aristaCollectionName)
            elif code == ScraperCode.RUCKUS.value:
                self.tester.test(code, self.ruckusCollectionName)
            elif code == ScraperCode.CISCO.value:
                self.tester.test(code, self.ciscoCollectionName)
            elif code == ScraperCode.HPE.value:
                self.tester.test(code, self.hpCollectionName)
            else:
                print(f"Scraper not found.")
        except Exception as e:
            print(f"Error Testing {ScraperCode.get(code)}: {e}")
    

if __name__ == "__main__":
    """    
    ARISTA = "A"
    RUCKUS = "R"
    CISCO = "C"
    HPE = "H"
    """
    controller = ScraperController("DevP3Systems")
    controller.run_scraper("R")
    