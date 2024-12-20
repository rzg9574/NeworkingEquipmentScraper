import urllib.request
import requests
from bs4 import BeautifulSoup
import re
import sys
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from fake_headers import Headers
import datetime
import PyPDF2
import subprocess
from Scrapers import init_db



class RuckusScraper:
    seriesParsed = []
    pn = []
    db_collection = None
    def __init__(self, collection, db=None):
        self.db = db
        self.db_collection = collection
        
    def get_soup(self, url):
        """
        returns the beautiful soup output of the url
        """
        issue = {}
        try:
            if 'xlsx' in url:
                return None
            
            service = Service(log_path=subprocess.DEVNULL)
            options = webdriver.ChromeOptions()
            header = Headers(
                    browser="chrome",  # Generate only Chrome UA
                    os="win",  # Generate only Windows platform
                    headers=False # generate misc headers
                )
            customUserAgent = header.generate()['User-Agent']

            options.add_argument(f"user-agent={customUserAgent}")
            #needs to be run in headless mode to work on docker 
            options.add_argument('headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)
            return driver
        
        except:
            return None


    def postData(self, data):
        """
        Posts the data to the mongodb and resets the parser variable 
        """
        if data:
            collection = self.db.get_collection(self.db_collection)
            print("posting to db", file=sys.stderr)
            id = collection.insert_one(data).inserted_id

            return id   


    def start(self):
        """
        Starts the scraper by setting up starting links and looks through the starting pages for peoduct links 
        """
        print(">>>>>>>>>>>>>>>>>>>>>>>>>Starting<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", file=sys.stderr)
        data = []
        ruckusProductURL = "https://www.ruckusnetworks.com/products/"
        pressRealseURL = "https://www.commscope.com/press-releases/?category=RUCKUS&newstype=&desiredYear="
        opticURL = "https://www.ruckusnetworks.com/products/optical-transceivers/"
        urlList = ['https://www.ruckusnetworks.com/products/ethernet-switches/', 'https://www.ruckusnetworks.com/products/wireless-access-points/']
        linkset = set()
        for url in urlList:
            mainSoup = self.get_soup(url)
            while mainSoup:
                links = mainSoup.find_elements(By.XPATH, '//div[@class = "Products-layout"]//a')
                for link in links:
                    url = link.get_attribute('href') 
                    if url not in linkset and url != 'javascript:void(0);' and "page" not in url:
                        linkset.add(url)
                        data.append(self.productPage(url))
                
                try:
                    nextPageButton = mainSoup.find_element(By.XPATH, '//div[@class = "Products-layout"]//li[@class = "next"]//a')
                except:
                    nextPageButton = None 
                
                if nextPageButton:
                    url = nextPageButton.get_attribute('href')
                    if url and url != 'javascript:void(0);':
                        mainSoup = self.get_soup(url)
                        continue

                mainSoup = None 
        
        
        data.extend(self.opticSearch(opticURL))
        
        if data:
            self.dateSearch(pressRealseURL, self.condenseRawResults(data))
        
    def condenseRawResults(self, rawData):
        """
        Mutiple of the same series can be in rawdata with diffrent partnumbers so this fuction will combined their part numbers so there
        is only unique series name   

        Args:
            rawData (list): a list of dictionaries were the key is the series name and the value is list of part numbers 

        Returns:
            list: a list of dictionaries were the key is the series name and the value is list of part numbers 
        """
        names = set()
        data = {}
        
        for pair in rawData:
            if pair:
                series, pns = next(iter(pair.items()))
                series = series.replace("ruckus ", "")
                if pns:
                    if series not in names:
                        names.add(series)
                        data[series] = pns
                    else:
                        data[series].extend(pns)       
                    
        return [{seriesName:pn} for seriesName, pn in data.items()]
        
    
    def dateSearch(self, url, data):
        """
        Searches the Commscope press realse page for all posts and checks each post to check if there is any mention
        of any of the found series names and if ther series name is metion is will search for the date this posted
        and takes that as the realse date  

        Args:
            url (str): url of the Commscope press realse page fillterd to only show Ruckus products
            data (list): a list of dictionaries were the key is the series name and the value is list of part numbers
        """
        datePattern = r"(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December)\b\s([0-9+th?]+)[,]\s([0-9]{4})"
        mainSoup = self.get_soup(url)
        while mainSoup:
            links  = mainSoup.find_elements(By.XPATH, "//div[@class = 'press-release-item']//h5[@class = 'press-title']//a")
            for link in links:
                pressPage = self.get_soup(link.get_attribute("href"))
                if pressPage:
                    pressPageText = pressPage.find_element(By.XPATH, "//div[@class = 'press-release']").get_attribute("innerText")
                    for i in range(len(data)):
                        if i < len(data) and data[i]:
                            key, pn = next(iter(data[i].items()))
                            if "-" in key:
                                index = key.find("-")
                                if index != -1:
                                    tempKey = key[:-index]
                                    if tempKey in pressPageText.lower():
                                        dateSearch = re.findall(datePattern, pressPageText)
                                        self.postData({"SeriesName": key.upper(), "ReleaseDate":self.formatDate(dateSearch[0]), "PartNumbers": pn})
                                        data.pop(i) 
                            
                            else:
                                if key in pressPageText.lower():
                                    dateSearch = re.findall(datePattern, pressPageText)
                                    self.postData({"SeriesName": key.upper(), "ReleaseDate":self.formatDate(dateSearch[0]), "PartNumbers": pn})
                                    data.pop(i)                           
            
            try:
                nextButton = mainSoup.find_element(By.XPATH, "//li[@class = 'next']//a")
            except:
                nextButton = None
                
            if nextButton:
                mainSoup = self.get_soup(nextButton.get_attribute("href"))
            else:
                mainSoup = None
        
    
    def formatDate(self, date):
        """
        Takes a date in the format May 5th, 2004 and returns a datetime object fo the same date 
    
        Args:
            date (string): string of a date in the format May 5th, 2004

        Returns:
            datetime: datetime object of the passed in date 
        """
        date = " ".join(date)
        day = ""
        year = ""
        month = ""
        if "-" in date:
            if "\xa0" in date:
                date = date.replace("\xa0", "-")
            
            splitDate = date.split("-")
        else:
            if "\xa0" in date:
                date = date.replace("\xa0", " ")    
        
            splitDate = date.split(" ")
        
        if not splitDate:
            return None
        
        if len(splitDate[0]) <= 2:
            splitDate[0] = splitDate[0].replace("st", "")     
            day = splitDate[0]
            month = splitDate[1]
            year = splitDate[2]
        else:
            splitDate[1]  = splitDate[1].replace(",", "")
            day = splitDate[1]
            month = splitDate[0]
            year = splitDate[2]
            
            
        if day and month and year:
            try:
                return datetime.datetime.strptime(year + month + day, '%Y%B%d')    
            except:
                try:
                    return datetime.datetime.strptime(year + month + day, '%Y%b%d')    
                except:
                    return None
    
      
    def opticSearch(self, url):
        """
        Ruckus has their optic and cables part numbers on a diffrent page instead of the main page this method will
        search for the optic and cables partnumbers 

        Args:
            url (str): url of the ruckus optic page 

        Returns:
            list: a list of dictionaries were the key is the series name and the value is list of part numbers
        """
        data = None
        mainSoup = self.get_soup(url)
        if mainSoup:
            links = mainSoup.find_elements(By.XPATH,  "//div[@class = 'card']//a")
            for link in links:  
                if "Download data sheet" == link.get_attribute("innerText"):
                    data = self.parsePDF(link.get_attribute("href"), OPTIC_MODE=True)
     
        return data
            
    
    
    def productPage(self, url):
        """
        Finds the link to the datasheet pdf on the product page for a Ruckus product and then 
        returns the part numbers it finds  

        Args:
            url (str): the url of the product page 

        Returns:
            dict: returns a dictiary the key the series name and the value is a list of dictarries pairs storing 
                    part numbers and their decription 
        """
        seriesNamePattern = r'RUCKUS\s[A-Z0-9\-\s]+'
        mainSoup = self.get_soup(url)
        if mainSoup:
            title = mainSoup.find_element(By.XPATH, "//h1[@class = 'title']").get_attribute("innerText")
            match = re.findall(seriesNamePattern, title)
            if match:
                seriesName = match[0]
                if  " " in seriesName[-2:]:
                    seriesName = seriesName[:-2].lower()
                else:
                    seriesName = seriesName.lower()
                    
                print(seriesName)
            try:
                link = mainSoup.find_element(By.XPATH,  "//div[@class = 'specs-section']//a[text()='Download Data Sheet']")
            
                if link and seriesName:
                    data = self.parsePDF(link.get_attribute("href"), seriesName = seriesName)
                    if data:
                        return data
                    
            except:
                pass     

    def parsePDF(self, url, seriesName = None, OPTIC_MODE = False):
        """
        Searches for the series name and associated part numbers of the data sheet pdf
        Args:
            url (str): the url of the pdf 
            seriesName (str, optional): the series name that the part numbers in this pdf belong to if not passed in it will try to find the series name in the pdf. Defaults to None.
            OPTIC_MODE (bool, optional): Since the Ruckus structures their pdf for their optics diffrently from everything else if optic mode is true it will handle 
                                        looking for optic part numbers. Defaults to False.

        Returns:
            dict: dictionary where the key is the series name and the value is the found part number 
        """
        pn = []
        foundPartNumberSet = set()
        count = 0
        partNumberBuilder = ""
        descriptionBuilder = ""
        pastSeries = ""
        text = ""
        seriesBuilder = ""
        descriptionAdded = False
        collectSeriesName = False
        opticPairs = []
        stopSearchingDec = False
        skipNextPn = [False, 0]
        orderingInfoPattern = r'(ordering|contact)\s*(information|&\s*contact\s*information)'
        partNumberPattern = r'(?=.*[A-Z])(?=.*[-])[A-Z0-9]{2,}-[A-Z0-9\-]*'
        file_Path = 'TempRuckusPDF.pdf'
        try:
            os.remove(file_Path)
        except:
            pass
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            with open(file_Path, 'wb') as pdf_file:
                #1024 = 1kb 
                for chunk in response.iter_content(chunk_size=1024):
                    pdf_file.write(chunk)
        
        with open(file_Path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            page = None
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                try:
                    text = page.extract_text()
                except:
                    text = None
                if text:        
                    orderingInfoReResults = re.findall(orderingInfoPattern, text.lower())
                    if orderingInfoReResults:
                        text = self.shortenPDFText(text)
                        splitText = text.split(" ")
                        for i in range(len(splitText)):
                            word = splitText[i]
                            
                            if "\npart" in word.lower() or word.lower().endswith("part") or "part" == word.lower():
                                stopSearchingDec = True
                                if OPTIC_MODE:
                                    if "number" in splitText[i + 1].lower():
                                        collectSeriesName = True   
                                continue
                            
                            tempWord = word.replace("\n", "")
                            if 'requires' == tempWord.lower():
                                skipNextPn = [True, 0]
                                descriptionBuilder += word + " "
                                if len(splitText) > i+8:
                                    sentence = " ".join(splitText[i+2:i+8])
                                    if sentence in ["to use advanced Layer 3 features", "to use advanced L3 features and"]:
                                        skipNextPn = [True, 1]
                                continue
                            
                            match = re.findall(partNumberPattern, word)
                            if match and len(match[0]) > 6:
                                if not skipNextPn[0]:
                                    stopSearchingDec = False
                                    
                                    if collectSeriesName and OPTIC_MODE:
                                        if not opticPairs and seriesBuilder:
                                            opticPairs.append({seriesBuilder:[]})
                                            pastSeries = seriesBuilder
                                            seriesBuilder = ""
                                        else:
                                            if pastSeries:
                                                opticPairs[-1][pastSeries] = pn
                                            else:
                                                opticPairs[-1][next(iter(opticPairs[-1]))].extend(pn)
                                            
                                            if seriesBuilder: 
                                                opticPairs.append({seriesBuilder:[]})
                                                pastSeries = seriesBuilder
                                                seriesBuilder = ""
                                            
                                            pn = []
                                    
                                    if partNumberBuilder and descriptionBuilder and not collectSeriesName:
                                        if len(descriptionBuilder) > 7 and partNumberBuilder not in foundPartNumberSet:
                                            pn.append({"pn":partNumberBuilder, "description":descriptionBuilder, "url":url})
                                            print({"pn":partNumberBuilder, "description":descriptionBuilder})
                                            count += 1
                                            partNumberBuilder = ""
                                            descriptionBuilder = ""
                                            foundPartNumberSet.add(partNumberBuilder)
                                        else:
                                            descriptionBuilder += word + " "
                                            continue
                                            
                                    partNumberBuilder += match[0]
                                    #add leftovers from part number match to descriptions
                                    index = word.find(match[0])
                                    if index != -1:
                                        leftover = word[:index] + " " + word[index + len(match[0]):]
                                        if pn:
                                            pn[-1]["description"] += leftover
                                    
                                    collectSeriesName = False
                                else:
                                    if skipNextPn[1] > 0:
                                        skipNextPn[1] -= 1
                                    else:
                                        skipNextPn[0] = False
                                    if collectSeriesName and OPTIC_MODE:
                                        seriesBuilder += word + " "
                                    else:
                                        if not stopSearchingDec and partNumberBuilder:
                                            descriptionBuilder += word + " "
                            else:
                                if collectSeriesName and OPTIC_MODE:
                                    if "number" not in word.lower():
                                        seriesBuilder += word + " "
                                else:
                                    if not stopSearchingDec and partNumberBuilder:
                                        descriptionBuilder += word + " "
        
                        
                        if OPTIC_MODE:
                            if opticPairs and pn:
                                if partNumberBuilder and partNumberBuilder not in foundPartNumberSet:
                                    pn.append({"pn":partNumberBuilder, "description":descriptionBuilder})
                                    print({"pn":partNumberBuilder, "description":descriptionBuilder})
                                    count += 1
                                    partNumberBuilder = ""
                                    descriptionBuilder = ""
                                    foundPartNumberSet.add(partNumberBuilder)

                                opticPairs[-1][pastSeries].extend(pn)
                                pn = []
                                seriesBuilder = ""
                        else:
                            if partNumberBuilder and partNumberBuilder not in foundPartNumberSet:
                                pn.append({"pn":partNumberBuilder, "description":descriptionBuilder})
                                print({"pn":partNumberBuilder, "description":descriptionBuilder})
                                count += 1
                                partNumberBuilder = ""
                                descriptionBuilder = ""
                                foundPartNumberSet.add(partNumberBuilder)
                                
        if OPTIC_MODE:
            return opticPairs
        else:
            return {seriesName : pn}                
    
    def shortenPDFText(self, text):
        """
        Pages from the datasheet may contain info that is not related to the partnumbers or decreption this meathod will take out all the not important info just leaving text aboout
        the partnumbers and description 

        Args:
            text (str): raw text from a page of the data sheet pdf

        Returns:
            str: shorten text only containing the partnumbers and description
        """
        partNumberPattern = r'(?=.*[A-Z])(?=.*[-])[A-Z0-9]{2,}-[A-Z0-9\-]*'
        index = text.find("Ordering Information")
        
        beforeMatch = re.search(partNumberPattern, text[:index])
        x = text[index + len("Ordering Information"):]
        afterMatch = re.search(partNumberPattern, text[index + len("Ordering Information"):])
        if beforeMatch and not afterMatch:
            text = text[:index]
        elif afterMatch and not beforeMatch:
            text = text[index + len("Ordering Information"):]
        
        
        index = text.find("OPTICS")
        if index == -1:
            index = text.find("Warranty")   
        
        if index != -1:
            beforeMatch = re.match(partNumberPattern, text[index:])
            afterMatch = re.match(partNumberPattern, text[:index])
            if beforeMatch and not afterMatch:
                text = text[index:]
            elif afterMatch and not beforeMatch:
                text = text[:index]
        
        return text 
            

                    
if __name__ == "__main__":
    db = init_db.init("DevP3Systems", "TestRuckusScraper")
    RuckusScraper("TestRuckusScraper", db).start()
