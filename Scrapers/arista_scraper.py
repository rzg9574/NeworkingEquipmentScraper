import re
import sys
import os
import datetime
import wget
import PyPDF2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from fake_headers import Headers
from Scrapers import init_db

class AristaScraper:
    issues = []
    pn = []
    rawResults = []
    pressSearch = {}
    
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
            
            service = Service(log_path=os.devnull)
            options = webdriver.ChromeOptions()
            header = Headers(
                    browser="chrome",  # Generate only Chrome UA
                    os="win",  # Generate only Windows platform
                    headers=False # generate misc headers
            )
        
            options.add_argument(f"user-agent={header.generate()['User-Agent']}")
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
        productListURL = "https://www.arista.com/en/products/platforms"
        pressURL = "https://www.arista.com/en/company/news/press-release"
        endOfSaleURL = "https://www.arista.com/en/support/advisories-notices/endofsale"
        transceiversAndCablesURL = "https://www.arista.com/en/products/transceivers-cables/technical-resources"
        urlsToParse = [productListURL]
        
        for url in urlsToParse:
            print(f"Going to product list URL {url}", file=sys.stderr)
            self.productListPage(url)
                
        self.transceiversAndCablesSearch(transceiversAndCablesURL)   
            
        #start searching for dates 
        self.dateSearch(pressURL) 
        
        self.end()
        
        self.endOfSaleSearch(endOfSaleURL) 
        

    
    def transceiversAndCablesSearch(self, url):
        """
        The Transceivers and Cable part numbers are on a diffrent page that is formatted diffrently
        so this methoad handles that
        
        Args:
            url (str): the url for the page that as all the transceivers and Cables 
        """
        results = []
        
        mainSoup = self.get_soup(url)
        if mainSoup:
            ul = mainSoup.find_element(By.XPATH, "//ul[contains(@class, 'data-list')]")
            links = ul.find_elements(By.XPATH, ".//a")
            for link in links:
                if "Datasheets" in link.get_attribute("href") or "Datasheet" in link.get_attribute("href") or "Data-Sheet" in link.get_attribute("href"): 
                    results = self.getPartNumberFromPDF(link.get_attribute("href"), OpticMode=True)
                    self.pressSearch.update(results)
                    

    def endOfSaleSearch(self, url):
        """
        Searches for part numbers and dates that are on no longer supported by arista so they are not listed on the 
        product page so this meathod will search for the no longer supported products
        
        Args:
            url (str): the url for the page that as all the End of Sale Products
        """
        mainSoup = self.get_soup(url)
        while mainSoup:
            divs = mainSoup.find_elements(By.XPATH, "//div[@class = 'item']")
            if divs:
                for div in divs:
                    seriesName = div.find_element(By.XPATH, ".//h2[contains(@class, 'item-head')]").get_attribute("innerText")
                    index = seriesName.find("Arista")
                    if index !=-1 :
                        seriesName = seriesName[index + len("Arista "):] 
                    else:
                        index = seriesName.find("End of Sale")
                        if index !=-1 :
                            seriesName = seriesName[index + len("End of Sale of "):]
                    link = div.find_element(By.XPATH, ".//label[contains(@class, 'read-more')]//a")
                    if link and seriesName:
                        
                        self.parseEndOfSalesPage(link.get_attribute("href"), seriesName)
            try:
                nextLink  = mainSoup.find_element(By.XPATH, ".//a[contains(@title, 'Next')]")
            except:
                nextLink = None
                
            if nextLink:
                mainSoup = self.get_soup(nextLink.get_attribute("href"))
            else:
                mainSoup = None

    
    def parseEndOfSalesPage(self, url, seriesName):
        """
        Searches for end of sale part numbers and dates in their respected product page
        
        Args:
            url (str): url for the page for a specific end of sale product 
            seriesName (str): the series name that the part numbers on this page belong to
        """
        
        data = {"SeriesName": seriesName}
        pn = []
        pattern = r'[ ]{2,}'
        mainSoup = self.get_soup(url)
        searchingPartNumbers  = {"search": False}
        searchingDates = {"search": False}
        skipRow = ["Current Software Version", "Recommended Upgrade Software Version"]
        if mainSoup:
            rows = mainSoup.find_elements(By.XPATH, "//table[contains(@class, 'data-table')]//tr")
            for row in rows:
                splitRow = re.split(pattern, row.get_attribute("innerText"))
                splitRow = splitRow[0].split("\t")
                if splitRow:
                    if len(splitRow) == 1: 
                        continue
                    
                    if splitRow[0] in skipRow:
                        searchingPartNumbers  = {"search": False}
                        searchingDates = {"search": False}
                        continue
                    
                    if splitRow[0] in ["Affected Product", "\xa0Affected Product"]:
                        if splitRow[1] in ["Description", "Sub SKUs"]:       
                            searchingPartNumbers["search"]  = True
                            searchingDates["search"] = False
                            if splitRow[1] == "Description":
                                searchingPartNumbers["index"] = 1
                            else:
                                searchingPartNumbers["index"] = 2  
                        
                            continue
                    
                    if splitRow[0] in ["Affected Product", "\xa0Affected Product", "Milestone"]:
                        if splitRow[1] in ["Date", "Milestone"]:
                            searchingPartNumbers["search"]  = False
                            searchingDates["search"] = True
                            if splitRow[1] == "Date":
                                searchingDates["index"] = 1
                            else:
                                searchingDates["index"] = 2
                            
                            continue
                

                    if searchingPartNumbers["search"]:
                        partnumber = splitRow[0]
                        partnumber = partnumber.replace('"', "")
                        partNumberSplit = partnumber.split()
                        if partNumberSplit and len(partNumberSplit) > 1:
                            for part in partNumberSplit:
                                pn.append({"pn": part, "description": splitRow[searchingPartNumbers['index']], "url":url})
                        elif partNumberSplit:             
                            pn.append({"pn": partNumberSplit[0], "description": splitRow[searchingPartNumbers['index']], "url":url})
                    if searchingDates["search"]:
                        if searchingDates['index'] == 2:
                            if len(splitRow) > 2:
                                if splitRow[1] in ["End-of-Sale Announcement\xa0", "End-of-Sale Announcement", "End-of-Life of product"]:
                                    data[splitRow[1].replace(" ", "_")] = self.formatDate(splitRow[searchingDates['index']])
                            else:
                                if splitRow[-2] in ["End-of-Sale Announcement\xa0", "End-of-Sale Announcement", "End-of-Life of product"]:
                                    data[splitRow[-2].replace(" ", "_")] = self.formatDate(splitRow[-1])
                        else:
                            if splitRow[0] in ["End-of-Sale Announcement\xa0", "End-of-Sale Announcement", "End-of-Life of product"]:
                                data[splitRow[0].replace(" ", "_")] = self.formatDate(splitRow[searchingDates['index']])
        
        if pn:
            data["PartNumbers"] = pn
            self.postData(data)
            
    def end(self):
        """
        adds up all the part numbers found and posts them to the database 
        """
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>Done<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", file=sys.stderr)
        uniqueSeries = set()
        pnCount = 0
        for result in self.rawResults:
            for rawDate, value in result.items():
                if not rawDate:
                    pass
                for seriesPairs in value:
                    if "PartNumbers" in seriesPairs:
                        if seriesPairs["SeriesName"] not in uniqueSeries:
                            uniqueSeries.add(seriesPairs["SeriesName"])   
                            pnCount += len(seriesPairs["PartNumbers"])
                            data = {"SeriesName": seriesPairs["SeriesName"], "ReleaseDate": self.normalizeDate(rawDate), "PartNumbers": seriesPairs["PartNumbers"]}
                            print(f"posting {data}", file=sys.stderr)
                            self.postData(data)     
        print(f"found {pnCount} part number", file=sys.stderr)
    
    
    
    def formatDate(self, date):
        """
        Takes in a date in the format September 6th 2024 and returns a datetime object of that date 

        Args:
            date (str): date text in the format September 6th 2024

        Returns:
            datetime: datetime object of the passed in date
        """
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
    
    def normalizeDate(self, rawDate):
        """
        Takes in a date in the format 2Q and 1H fro the press announcements that arista posts and returns a datetime object of that date 

        Args:
            rawDate (str): date int the format 4Q or 2H 

        Returns:
            datetime: datetime object of the date passed in
        """
        if type(rawDate) == tuple:
            rawDate = list(rawDate)
            if "th" in rawDate[1]:
                return datetime.datetime.strptime(" ".join(rawDate), '%B %dth %Y')
            else:
                return datetime.datetime.strptime(" ".join(rawDate), '%B %d %Y')
            
        if 'H' in rawDate:
            if rawDate[1].isalpha():
                if rawDate[0] == "1":
                    return datetime.datetime.strptime(rawDate[-4:] + "0101", '%Y%m%d')
                elif rawDate[0] == "2":
                    return datetime.datetime.strptime(rawDate[-4:] + "0601", '%Y%m%d')
            else:
                if rawDate[1] == "1":
                    return datetime.datetime.strptime(rawDate[-4:] + "0101", '%Y%m%d')
                elif rawDate[1] == "2":
                    return datetime.datetime.strptime(rawDate[-4:] + "0601", '%Y%m%d')
        elif 'Q' in rawDate:
            if rawDate[0].isalpha():
                if rawDate[1] == "1":
                    return datetime.datetime.strptime(rawDate[-4:] + "0101", '%Y%m%d')
                elif rawDate[1] == "2":
                    return datetime.datetime.strptime(rawDate[-4:] + "0401", '%Y%m%d')
                elif rawDate[1] == "3":
                    return datetime.datetime.strptime(rawDate[-4:] + "0701", '%Y%m%d')
                elif rawDate[1] == "4":
                    return datetime.datetime.strptime(rawDate[-4:] + "1001", '%Y%m%d')
            else:
                if rawDate[0] == "1":
                    return datetime.datetime.strptime(rawDate[-4:] + "0101", '%Y%m%d')
                elif rawDate[0] == "2":
                    return datetime.datetime.strptime(rawDate[-4:] + "0401", '%Y%m%d')
                elif rawDate[0] == "3":
                    return datetime.datetime.strptime(rawDate[-4:] + "0701", '%Y%m%d')
                elif rawDate[0] == "4":
                    return datetime.datetime.strptime(rawDate[-4:] + "1001", '%Y%m%d')         
    
    def dateSearch(self, url):
        """
        Searches Aristas press realse page for any post that mentions one of the series name in order to
        find the realse date for said series 
        
        Args:
            url (str): url of the press realse page where Arista announces all its new products and other company news
        """
        pageURL = ''
        mainSoup = self.get_soup(url)
        if mainSoup:
            navBarList = mainSoup.find_elements(By.XPATH, "//div[contains(@class, 'tabSlider')]//ul[contains(@class, 'tabNav')]//a")
            for link in navBarList:
                if len(self.pressSearch) == 0:
                    break
                
                href = link.get_attribute('href')
                        
                if not href.startswith("http"):
                    pageURL = "https://www.arista.com/" + href
                else:
                    pageURL = href   
                
                foundKeyWords = set()
                page = self.get_soup(pageURL)
                foundKeyWords = self.parseRowsForRawDates(page)
                
                for foundKey in foundKeyWords:
                    self.pressSearch.pop(foundKey)
                    
                
                try:     
                    nextLink = mainSoup.find_element(By.XPATH, "//a[contains(@title='Next')]")
                    next_href = nextLink.get_attribute('href')
                except:
                    next_href = None
                
                while(next_href):
                    nextURL = ""
                    if not next_href.startswith("http"):
                        nextURL = "https://www.arista.com/" + next_href
                    else:
                        nextURL = next_href
                        
                    nextPage = self.get_soup(nextURL)
                    if nextPage:    
                        foundKeyWords = set()
                        foundKeyWords = self.parseRowsForRawDates(nextPage)
                        for foundKey in foundKeyWords:
                            self.pressSearch.pop(foundKey)

                    try:     
                        nextLink = mainSoup.find_element(By.XPATH, "//a[@title='Next')]")
                        next_href = nextLink.get_attribute('href')
                    except:
                        next_href = None            

    def parseRowsForRawDates(self, page):
        """
        Searches A web element of the page for a spsific post that contains a Series Name for the date it was realsed  

        Args:
            page (selenium.webdriver.remote.webelement.WebElement): A web element of the page for a spsific post that contains a Series Name 

        Returns:
            _type_: _description_
        """
        foundKeyWords = set()
        pattern = r'(?:[QH][0-9]|[0-9][QH])(?: [0-9]{4})'
        backupPattern = r'(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December)\b\s([0-9+th?]+)[,]\s([0-9]{4})'
        rows = page.find_elements(By.XPATH, "//div[contains(@class, 'BlogList')]//div[contains(@class, 'items-row')]")
  
        for row in rows:
            fullPressLink = row.find_element(By.XPATH, ".//a")
            fullPressURL = fullPressLink.get_attribute('href')
            fullPressPage = self.get_soup(fullPressURL)
            if fullPressPage:
                for keyWord in self.pressSearch:
                    div = fullPressPage.find_element(By.XPATH, "//div[contains(@class, 'item-page')]")
                    text = div.get_attribute('innerText')
                    text = text.replace(u'\xa0', u' ')
                    if keyWord in text:
                        result = re.findall(pattern, text)
                        if result:
                            self.rawResults.append({result[0]: self.pressSearch[keyWord]})
                            foundKeyWords.add(keyWord)
                            print(f"found key words {foundKeyWords}", file=sys.stderr)
                        
                        else:
                            if "available now" in text.lower():
                                result = re.findall(backupPattern, text)
                                if result:
                                    self.rawResults.append({result[0]: self.pressSearch[keyWord]})
                                    foundKeyWords.add(keyWord)
                                    print(f"found key words {foundKeyWords}", file=sys.stderr)
    
        return  foundKeyWords                          

    def productListPage(self, url):
        """
        Finds the link to the datasheet pdf on the product page for a Ruckus product and then 
        adds the part numbers it finds to self.pressSearch a global a variable that stores the keyword to search for the date 
        on the arista press realse page and the assiated part numbers for that key word  

        Args:
            url (str): the url of the product page 
        """
        visitedLinks = set()
        pressSearchKeyWord = ""
        pattern = r'(?:arista)\s*([a-z0-9]+)\s*(?:series)'
        backUpPattern = r'(?:arista)\s*([a-z0-9]+)'
        mainSoup = self.get_soup(url)
        if mainSoup:
            print("Looking for rows with the products", file=sys.stderr)
            rows = mainSoup.find_elements(By.XPATH, "//form//div[contains(@class, 'scroll-box-hr')]//table//tbody//tr")
            if rows:
                for row in rows:
                    seriesName = ""
                    rowLinks = []
                    firstLink = True
                    
                    links = row.find_elements(By.XPATH, ".//a")
                    if links:
                        for link in links:
                            if not link.get_attribute('href'):
                                continue
                            
                            linkText = link.get_attribute('href')
                            rowLinks.append(linkText)
                        
                        if rowLinks:
                            if rowLinks[1] not in visitedLinks:
                                seriesName = rowLinks[1].split("/")[-1].split("-")[0].upper()     
                                visitedLinks.add(rowLinks[1])
                                partNumbers = self.getPartNumberFromPDF(rowLinks[1], seriesName)
                            print(f"found these part numbers {partNumbers}\n", file=sys.stderr)
                            if partNumbers:
                                self.pn.append(partNumbers)

                    else:
                        if len(self.pn) != 0 and pressSearchKeyWord != "":
                            self.pressSearch[pressSearchKeyWord] = self.pn
                            self.pn = []
                            
                        rowText = row.get_attribute('innerText')
                        result = re.findall(pattern, rowText.lower())
                        if len(result) == 0:
                            result = re.findall(backUpPattern, rowText.lower())
                        
                        if type(result[0]) != str:
                            pressSearchKeyWord = re.sub('[^A-Za-z0-9]+', '', str(result[0]))
                        else:     
                            pressSearchKeyWord = result[0].upper()
                        self.pressSearch[pressSearchKeyWord] = self.pn                  
            
    def shortenText(self, text, keywords):
        """
        Based on the list of keywords this method will shorten the text getting rid of everything before those key words

        Args:
            text (str): text of a page of a data sheet
            keywords (list): list of keywords that could be on a datasheet page that dont matter

        Returns:
            str: shorten text
        """
        for keyword in keywords:
            index = text.find(keyword)
            if index != -1:
                return text[index + len(keyword):]
        return ""
    
    def cutDescriptionTop(self, string):
        """
        Checks the start of the description to see if it starts with text that is really the ending part of a partnumber and if so
        it deletes the found partnumber fragment from the decsription and returns that description and partnumber fragment

        Args:
            string (str): description text

        Returns:
            tuple: returns a tuple the frist index is the decription and the second index is the partnumber frangment
        """
        text = ""
        for char in string:
            if char.islower():
                break
            else:
                text += char
        
        if len(text) > 1:
            text = text[:-1]
            string = string[len(text):]
            return text, string
        return text, string

    def cutDescriptionBottom(self, string):
        """
        Checks the end of the description to see if it ends with text that is really the starting part of the previously found partnumber and if so
        it deletes the found partnumber fragment from the decsription and returns that description and partnumber fragment

        Args:
            string (str): description text

        Returns:
            tuple: returns a tuple the frist index is the decription and the second index is the partnumber frangment
        """
        text = ""
        for char in range(len(string) -1, -1, -1):
            if string[char].islower():
                break
            else:
                text += string[char]
        
        if len(text) > 1:
            string = string[:-len(text)]
            return text[::-1], string
        return text, string

    def validate(self, descriptionBuilder, partnumberBuilder, found, seriesName):
        """
        Manages werid specific cases where parts of the decriptions are seen as partnumbers or vice versa 

        Args:
            descriptionBuilder (str): decription of the partnumber
            partnumberBuilder (str): one of the partnumbers from a datasheet 
            found (list): list of part number decription pairs that were already found
            seriesName (str): the series name associated with these partnumbers and description

        Returns:
            tuple: returns a tuple where the first index is the validated description the second is the validated part number and the last index 
                    is the validated list of found pairs
        """
        pattern = r'c[0-9]{,2}-c[0-9]{,2}'

        result = re.findall(pattern, partnumberBuilder.lower())
        if result:
            index = partnumberBuilder.lower().find(result[0])
            if index != -1:
                partnumberBuilder = partnumberBuilder[index + len(result[0]):]
        
        
        if "EOS" in partnumberBuilder:
            partnumberBuilder = partnumberBuilder.replace("EOS", "")
            descriptionBuilder = "EOS" + descriptionBuilder
        elif  "5MM" in partnumberBuilder:
            descriptionBuilder += "5MM"
            partnumberBuilder = partnumberBuilder.replace("5MM", "")
        elif seriesName and partnumberBuilder.endswith(seriesName):
            tempSplit = partnumberBuilder.split("-")
            tempSplit[-1] = tempSplit[-1].replace(seriesName, "")
            partnumberBuilder = "-".join(tempSplit)
            descriptionBuilder = seriesName + descriptionBuilder
        
        if partnumberBuilder and partnumberBuilder[-1].lower() == "a" and "rista" in descriptionBuilder.lower():
            partnumberBuilder = partnumberBuilder[:-1]
            descriptionBuilder = "A" + descriptionBuilder
        
        if partnumberBuilder and partnumberBuilder[-1].lower() == "s" and "pare" in descriptionBuilder.lower():
                partnumberBuilder = partnumberBuilder[:-1]
                descriptionBuilder = "S" + descriptionBuilder
        
        if found and partnumberBuilder:
            if "1-6" in partnumberBuilder[:len(partnumberBuilder)-3] and found[-1]["description"].endswith("slots "):
                found[-1]["description"] += "1-6"
                partnumberBuilder = partnumberBuilder.replace("1-6", "")
            if "1-6" in partnumberBuilder[:len(partnumberBuilder)-3] and found[-1]["description"].endswith("slots "):
                found[-1]["description"] += "1-6"
                partnumberBuilder = partnumberBuilder.replace("1-6", "")
            elif "CPU" in partnumberBuilder[:len("CPU")] or "SSD" in partnumberBuilder[:len("SSD")] or "PSU" in partnumberBuilder[:len("PSU")]:
                partnumberBuilder = partnumberBuilder[3:]
            elif "AC" in partnumberBuilder[:len("AC")]:
                found[-1]["description"] += "AC"
                partnumberBuilder = partnumberBuilder[len("AC"):]
            elif "2400W" in partnumberBuilder[:len("2400W")]:
                found[-1]["description"] += "2400W"
                partnumberBuilder = partnumberBuilder[len("2400W"):]
            elif "1500W" in partnumberBuilder[:len("1500W")]:
                found[-1]["description"] += "1500W"
                partnumberBuilder = partnumberBuilder[len("1500W"):]
            elif "6" == partnumberBuilder[0]:
                found[-1]["description"] += "6"
                partnumberBuilder = partnumberBuilder[len("6"):]
            elif "1-5" in partnumberBuilder[:len(partnumberBuilder)-3] and found[-1]["description"].endswith("slots "):
                found[-1]["description"] += "1-5"
                partnumberBuilder = partnumberBuilder.replace("1-5", "")
            elif "2-D" in partnumberBuilder[:len(partnumberBuilder) - 3]: 
                found[-1]["description"] += "2-D"
                partnumberBuilder = partnumberBuilder.replace("2-D", "")
            elif "2" == partnumberBuilder[0] and found[-1]["description"].endswith("Sup"): 
                found[-1]["description"] += "2"
                partnumberBuilder = partnumberBuilder[1:]
            elif "BLUE" == partnumberBuilder[:len("BLUE")]: 
                found[-1]["description"] += "BLUE"
                partnumberBuilder = partnumberBuilder[len("BLUE"):]
                
        return descriptionBuilder, partnumberBuilder, found  
            
    def handlePartNumber(self, descriptionBuilder, partnumberBuilder, found, seriesName):
        """
        Manages cases where parts of the decriptions are seen as partnumbers or vice versa 

        Args:
            descriptionBuilder (str): decription of the partnumber
            partnumberBuilder (str): one of the partnumbers from a datasheet 
            found (list): list of part number decription pairs that were already found
            seriesName (str): the series name associated with these partnumbers and description

        Returns:
            tuple: returns a tuple where the first index is the validated description the second is the validated part number and the last index 
                    is the validated list of found pairs
        """
        #Gets rid of any extra spacing if there is any
        splitPn = partnumberBuilder.split()
        if len(splitPn) > 1:
            partnumberBuilder = splitPn[0]
        else:
            partnumberBuilder = "".join(splitPn)
        
        #gets rid of any text in front of Arista in the description if Arista is one 
        #of the first few chars because those chars are likely part of the partnumber  
        index = descriptionBuilder.find("Arista")
        if index != -1:
            if index != 0 and index < 6:
                oldDescriptionBuilder  = descriptionBuilder
                descriptionBuilder = oldDescriptionBuilder[index:]
                leftover = oldDescriptionBuilder[:index]
                partnumberBuilder += leftover    
            
        if partnumberBuilder[0] == "-" and found:
            text, string = self.cutDescriptionBottom(found[-1]["description"])
            partnumberBuilder = text + partnumberBuilder 
            found[-1]["description"] = string 
                
        if partnumberBuilder[-1] == "-":
            text, string = self.cutDescriptionTop(descriptionBuilder)
            partnumberBuilder += text 
            descriptionBuilder = string                                       
        
        if descriptionBuilder and descriptionBuilder[0] == "#":
            partnumberBuilder += "#"
            descriptionBuilder = descriptionBuilder[len("#"):]
            
        descriptionBuilder, partnumberBuilder, found = self.validate(descriptionBuilder, partnumberBuilder, found, seriesName)
        
        return descriptionBuilder, partnumberBuilder, found
            
    def removeEndingDuplicates(self, string):
        """
        Finds repating duplicate phrases in a part number and deletes it 
        if a part number has a duplicate phrase the duplicate is apart of the description   

        Args:
            string (str): the part number 

        Returns:
            tuple: tuple wher teh frist index is the partnumber without the duplicate and the second index is the duplicate that was found
        """
        stringBuilder = ""
        matchBuilder = ""
        i = 0
        stopSearch = False
        
        for c in range(len(string) -1, -1, -1):
            if stopSearch:
                break
            if len(stringBuilder) > 1 and string[c] == stringBuilder[i]:
                i += 1
                matchBuilder += string[c]
                for x in range(c - 1, -1, -1):
                    if i < len(stringBuilder) and string[x] == stringBuilder[i]:
                        matchBuilder += string[x]
                        i += 1
                    else:
                        if len(matchBuilder) >= 3:
                            stopSearch = True
                            break
                        else:
                            matchBuilder = ""
                            i = 0
                            stringBuilder += string[c]
                            break 
                            
            else:
                stringBuilder += string[c]
        
        
        if len(matchBuilder) >= 3:
            return string[:len(string) - len(matchBuilder)], matchBuilder[::-1]
        else:
            return string, None
    
    def getPartNumberFromPDF(self, url, seriesName=None, OpticMode= False):
        """
        Searches for the series name and associated part numbers of the data sheet pdf
        Args:
            url (str): the url of the pdf 
            seriesName (str, optional): the series name that the part numbers in this pdf belong to if not passed in it will try to find the series name in the pdf. Defaults to None.
            OPTIC_MODE (bool, optional): Since the Arista structures their pdf for their optics diffrently from everything else if optic mode is true it will handle 
                                        looking for optic part numbers. Defaults to False.

        Returns:
            dict: dictionary where the key is the series name and the value is the found part number 
        """
        print(f"looking for part numbers in this pdf file {url}", file=sys.stderr)
        finalResults = []
        finalResult = {"SeriesName":seriesName, "PartNumbers": []}
        foundPartNumberSet = set()
        found = []
        descriptionBuilder = ""
        partnumberBuilder = ""
        headerSearch = set()
        pattern = r'(?=.*[A-Z])(?=.*[-])[A-Z0-9]{2,}-[A-Z0-9\-]*'
        backUpPattern = r'(?=.*[A-Z])(?=.*[0-9])\b[A-Z0-9\-]{7,}'
        orderingInfoPattern = r'(ordering|contact)\s*(information|&\s*contact\s*information)'
        badPartNumberPattern = r'\b[1-9]{1,2}(0+)?(G)?(?:BASE)?-'
        headerPattern = r'(\n)[1-9]{1,2}0+(G)?'
        file_Path = 'TempAristaPDF.pdf'
        try:
            os.remove(file_Path)
        except:
            pass
        wget.download(url, file_Path)
        with open(file_Path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            page = None
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                orderingInfoReResults = re.findall(orderingInfoPattern, text.lower())
                if orderingInfoReResults:
                    split = self.shortenText(text, ["Description", "Bundles", "Cards", "Spares", "Licenses", "Information"]).split(" ")
                    for s in split:
                        if s:
                            match = re.search(headerPattern, s)
                            if match and OpticMode:
                                match = match.group(0).replace("\n", "")
                                if match not in headerSearch:
                                    headerSearch.add(match)
                                    if not finalResult["SeriesName"]:
                                        finalResult["SeriesName"] = match
                                    else:
                                        finalResults.append({"SeriesName":match if "g" in match.lower() else match + "G" , "PartNumbers":found})
                                        found = []
                                        finalResult["SeriesName"] = match
                                        finalResult["PartNumbers"] = []
                                else:
                                    if match != finalResult["SeriesName"]:
                                        finalResults.append({"SeriesName":match if "g" in match.lower() else match + "G" , "PartNumbers":found})
                                        found = []
                                        finalResult["SeriesName"] = match
                                        finalResult["PartNumbers"] = []       
                                
                            s = s.replace("\n", "")
                            if len(s) > 6 and "-" in s:
                                result = re.findall(pattern, s)
                                if len(result) > 0:
                                    
                                    if partnumberBuilder:
                                        badPartNumberCheck = re.search(badPartNumberPattern, partnumberBuilder)
                                        if not badPartNumberCheck:
                                            descriptionBuilder, partnumberBuilder, found = self.handlePartNumber(descriptionBuilder, partnumberBuilder, found, finalResult["SeriesName"])
                                            if partnumberBuilder and partnumberBuilder not in foundPartNumberSet:
                                                foundPartNumberSet.add(partnumberBuilder)
                                                found.append({"pn":partnumberBuilder, "description":descriptionBuilder, "url":url})
                                        
                                        descriptionBuilder = ""
                                        partnumberBuilder = ""
                                    
                                    firstPart = ""
                                    lastPart = ""
                                    index = s.find(result[0])
                                    if index != 0:
                                        firstPart = s[:index]
                                    if index + len(result[0]) != len(s):
                                        lastPart = s[s.find(result[0]) + len(result[0]):]
                                    
                                    
                                    partnumber, match = self.removeEndingDuplicates(result[0])
                                    if match:
                                        descriptionBuilder += match
                                    
                                    if firstPart and found:    
                                        found[-1]["description"] += firstPart
                                    
                                    if lastPart:
                                        descriptionBuilder += lastPart + " "   
                                            
                                    partnumberBuilder = partnumber
                                    
                                else:
                                    result = re.findall(backUpPattern, s)
                                    
                                    if len(result) > 0:
                                        if partnumberBuilder:
                                            badPartNumberCheck = re.findall(badPartNumberPattern, partnumberBuilder)
                                            if not badPartNumberCheck:
                                                descriptionBuilder, partnumberBuilder, found = self.handlePartNumber(descriptionBuilder, partnumberBuilder, found, finalResult["SeriesName"])
                                                if partnumberBuilder and partnumberBuilder not in foundPartNumberSet:
                                                    foundPartNumberSet.add(partnumberBuilder)
                                                    found.append({"pn":partnumberBuilder, "description":descriptionBuilder, "url":url})
                                            descriptionBuilder = ""
                                            partnumberBuilder = ""
                                        
                                        firstPart = ""
                                        lastPart = ""
                                        lastChar = result[0][-1]
                                        result[0] = result[0][:-1]
                                        descriptionBuilder += lastChar
                                        
                                        index = s.find(result[0])
                                        if index != 0:
                                            firstPart = s[:index]
                                        if index + len(result[0]) != len(s):
                                            lastPart = s[s.find(result[0]) + len(result[0]):]
                                        
                                        
                                        partnumber, match = self.removeEndingDuplicates(result[0])
                                        if match:
                                            descriptionBuilder += match
                                        
                                        if firstPart and found:    
                                            found[-1]["description"] += firstPart
                                        
                                        if lastPart:
                                            descriptionBuilder += lastPart + " "   
                                                
                                        partnumberBuilder = partnumber
                                    else:        
                                        descriptionBuilder += s + " "    
                            else:
                                descriptionBuilder += s + " "
        
        if finalResults and OpticMode:
            finalResult["PartNumbers"] = found    
            finalResults.append(finalResult)
            uniqueSeries = {}
            for pair in finalResults:
                if pair["SeriesName"] not in uniqueSeries:
                    uniqueSeries[pair["SeriesName"]] = [pair]
                else:
                    uniqueSeries[pair["SeriesName"]].append(pair["PartNumbers"])
            
            return uniqueSeries 
                
        finalResult["PartNumbers"] = found
        
        return finalResult
    

if __name__ == "__main__":
    db = init_db.init("DevP3Systems", "TestAristaScraper")
    #print(AristaScraper(db).getPartNumberFromPDF("https://www.arista.com/assets/data/pdf/Datasheets/7280R3-Data-Sheet.pdf", "7280R3"))
    # url =  "https://www.hpe.com/psnow/doc/c04545486.html?jumpid=in_pdp-psnow-qs"
    # seriesName, data, realaseDate = hpScraper(db).get_weird_soup(url)
    #print(hpScraper(db).parseQuickSpecsHTML(url,seriesName, data, realaseDate))
    AristaScraper("TestAristaScraper", db).start()
    #AristaScraper(db).getPartNumberFromPDF("https://www.arista.com/assets/data/pdf/Datasheets/7130B-Datasheet.pdf", "7130B-32QD")
    #AristaScraper(db).endOfSaleSearch("https://www.arista.com/en/support/advisories-notices/endofsale")