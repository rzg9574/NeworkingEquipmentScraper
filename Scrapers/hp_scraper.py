import requests
from bs4 import BeautifulSoup
import re
from Scrapers import init_db
import sys
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from fake_headers import Headers
import calendar
from datetime import datetime
import subprocess


class hpScraper:
    seriesParsed = []
    issues = []
    reloadCount = 0
    partNumberCount = 0
    db_collection = None
    
    def __init__(self, collection,  db):
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
            response = requests.get(url)
            if response.status_code==200:
                return BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.TooManyRedirects:
            return None
        
    def get_weird_soup(self, url):
        """
        Gets the info from the quickspec pages this method uses Selenium since the quickspec pages 
        are dynamically loaded 

        returns a tuple of (seriesName, rows, date) the rows are the rows from the tables containing part numbers 
        """
        date = None
        rows = []
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
        if ".html" not in url:
            url = url + ".html"
        driver.get(url)
        try:
            #switching frame to see the html
            try:
                frame = WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body .with-download-selectors > .frame > iframe')))
                driver.switch_to.frame(frame)
            except:
                return (None, None, None)
            # give some time for the page to load 
            driver.implicitly_wait(4)
            
            #tries to find a series name which is the title of the page if 
            #it cant find the series name it means the page probably did not load 
            #so it will re call this method 4 times to see if it can load the page properly 
            try:
                seriesName = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH,  '//body//h1[@id="htmlContentTitle"]'))).get_attribute("innerText")
                if self.seriesParsed:
                    if seriesName in self.seriesParsed:
                        return (None, None, None)
            except:
                if self.reloadCount <= 3:
                    self.reloadCount += 1
                    print(f"Reloading page: attempt {self.reloadCount}", file=sys.stderr)
                    driver.quit()
                    return self.get_weird_soup(url)
                else:
                    self.reloadCount = 0
                    self.issues.append({"URL": url, "P": "couldn't find the series name"})
                    driver.quit()
                    return (None, None, None)
            
            self.reloadCount = 0
            print(f"here is the series name {seriesName}", file=sys.stderr)

            #tries to find the date but if it cant find the date from this path it is probably 
            #because the way they formatted this page is different than usual so it does an in-depth search 
            #on the url to find the date and part numbers 
            try:
                dateDiv = driver.find_element(By.XPATH,  "//body//div[contains(@id, 'Summary_of_Changes') and contains(@class, 'contentDiv')]//tbody//tr[position()=last()]//td//p")
                date = dateDiv.get_attribute("innerText")
                date = self.dateValidation(date)
                try:
                    if "-" in date:
                        date = datetime.strptime(date, '%d-%b-%Y')
                    elif "/" in date:
                        date = datetime.strptime(date, '%d/%b/%Y')
                    else:
                        date = None

                except ValueError:
                    spiltDate = date.split("-")
                    if  int(spiltDate[0]) <= 0:
                        spiltDate[0] = 1
                    else:
                        n, lastday = calendar.monthrange(int(spiltDate[2]), datetime.strptime(spiltDate[1], '%b').month)
                        spiltDate[0] = str(lastday)
                        date = "-".join(spiltDate)
                        date = datetime.strptime(date, '%d-%b-%Y')
              
                print(date, file=sys.stderr)           
            except:
                tables = driver.find_elements(By.XPATH, "//body//div[contains(@class, 'section')]//table")
                self.indepthSearch(tables, url, seriesName)
                driver.quit()
                return (None, None, None)
            

            #tries to find the part numbers
            selectors = [
                "//body//div[contains(@id, 'Configuration_Information')]//div[contains(@class, 'section')]//table//tbody//tr",
                "//body//div[contains(@id, 'Core_Options')]//div[contains(@class, 'section')]//table//tbody//tr",
                "//body//div[contains(@id, 'Platform_Information')]//div[contains(@class, 'section')]//table//tbody//tr"
                
            ]

            rows = self.extract_table_rows(driver, selectors)

            #if no rows with part numbers were not found then try searching by a different name
            if len(rows) == 0:
            #if no rows with part numbers were still not found then try searching to see if a group of links to where the part numbers are exist
                quickSpecLinks = driver.find_elements(By.CLASS_NAME, "hpeQSLink")
                if quickSpecLinks:
                    print(f"found group of quick spec links", file=sys.stderr)
                    self.parseQuickSpecGroup(quickSpecLinks)
                driver.quit()
                return(None, None, None)   
        finally:
            driver.quit()
        return (seriesName, rows, date)

    def extract_table_rows(self, driver, selectors):
        """
        Gets and returns the rows from the tables with part numbers 
        """
        rows = []
        for selector in selectors:
            tr_list = driver.find_elements(By.XPATH, selector)
            if tr_list:
                for tr in tr_list:
                    spans = tr.find_elements(By.XPATH, './/p')
                    cols = [span.get_attribute("innerText") for span in spans if span.get_attribute("innerText") != ""]
                    if cols:
                        rows.append(cols)
        return rows

    def parseQuickSpecGroup(self, links):
        """
        parses and handles posting data from a group of quick spec page links 
        """
        for link in links:
            if link:
                try: 
                    link = link.get_attribute('href') + ".html"
                    if "www.hpe.com" not in link or "enw" not in link:
                        continue
                except:
                    continue
                seriesName, rows, date = self.get_weird_soup(link)
                if seriesName and rows and date:
                    result = self.parseQuickSpecsHTML(link, seriesName, rows, date)
                    if result["PartNumbers"][0]["pn"] != "":
                        self.seriesParsed.append(result["SeriesName"])
                        self.postData(result)
                    else:
                        self.issues.append({"URL": link, "I":"couldn't find Part numbers in the link"})


    def indepthSearch(self, tables, url, seriesName):
        """
        when the page looks really weird and is not formatted how it should this method will 
        look through all tables in the page for part numbers 
        """
        rows = []
        date = None
        tableHasDate =  False
        for table in tables:
            possibleTables = table.find_elements(By.CSS_SELECTOR, 'table')

            if len(possibleTables) != 0:
                for tempTable in  possibleTables:
                    tempTrList = tempTable.find_elements(By.CSS_SELECTOR, 'tr')
                    for tr in tempTrList:
                        spans = tr.find_elements(By.CSS_SELECTOR,  'span')
                        cols  = []
                        for span in spans:
                            cols.append(span.get_attribute("innerHTML"))
                
                        if len(cols) > 0:
                            rows.append(cols)

            trList = table.find_elements(By.CSS_SELECTOR, 'tr')
            for tr in trList:
                spans = tr.find_elements(By.CSS_SELECTOR,  'span')
                if not spans:
                    continue

                if spans[0].get_attribute("innerText") == "Date" and not tableHasDate:
                    date = table.find_element(By.CSS_SELECTOR, 'tbody tr:last-child .hpeQSSpan').get_attribute("innerText")
                    date = self.dateValidation(date)
                    try:
                        if "-" in date:
                            date = datetime.strptime(date, '%d-%b-%Y')
                        elif "/" in date:
                            date = datetime.strptime(date, '%d/%b/%Y')
                        else:
                            date = None
                        
                    except ValueError:
                        spiltDate = date.split("-")
                        if int(spiltDate[0]) <= 0:
                            spiltDate[0] = '1'
                        else:
                            n, lastday = calendar.monthrange(spiltDate[2], datetime.strptime(spiltDate[1], '%b').month)
                            spiltDate[1] = lastday
                            date = "".join(spiltDate)
                            date = datetime.strptime(date, '%d-%d-%Y')
                    tableHasDate = True
                    print(date, file=sys.stderr)
                    break

                if len(spans) > 3: 
                    continue

                cols = [span.get_attribute("innerText") for span in spans]
                
                if len(cols) > 0:
                    rows.append(cols)

        if len(rows) > 0:
            self.parseRows(url, seriesName, rows, date, True, True) 
            


    def postData(self, data):
        """
        Posts the data to the mongodb and resets the parser variable 
        """
        if data:
            if data["PartNumbers"][-1]["pn"] == "":
                data["PartNumbers"] = data["PartNumbers"][:-1]
            self.partNumberCount += len(data["PartNumbers"])
            collection = self.db.get_collection(self.db_collection)
            print("posting to db", file=sys.stderr)
            id = collection.insert_one(data).inserted_id

            return id
    
    def dateValidation(self, date):
        """_summary_

        Args:
            date (_type_): _description_

        Returns:
            _type_: _description_
        """
        dateSplit = []
        newDate = ""
        if "-" in date:
            dateSplit = date.split("-")
        elif "/" in date:
            dateSplit = date.split("/")
            
        if dateSplit:
            newDate = date    
            if len(dateSplit[1]) > 3:
                dateSplit[1] = dateSplit[1][:3]
                newDate = "-".join(dateSplit)
            
            if len(dateSplit[2]) < 4:
                if int(dateSplit[2]) < 60:
                    dateSplit[2] = "20" + dateSplit[2]
                else:
                    dateSplit[2] = "19" + dateSplit[2]
                
                newDate = "-".join(dateSplit)
                
        return newDate 
    
    def formatIssues(self):
        formatted_content = []
        for pair in self.issues:
            key, value = next(iter(pair))
            formatted_content.append(
                f"Failed at this link----->{key} ---For this reason: {value}\n\n"
            )

        # Join the formatted content back into a string
        formatted_content_str = "\n".join(formatted_content)
        
        if os.path.exists("HPIssuesOutput.txt"):
            os.remove("HPIssuesOutput.txt")
        with open("HPIssuesOutput.txt", "w") as text_file:
            text_file.write(formatted_content_str)


    def start(self):
        print(">>>>>>>>>>>>>>>>>>>>>>>>>Starting<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", file=sys.stderr)
        networkURL = "https://buy.hpe.com/us/en/networking"
        serversURL = "https://buy.hpe.com/us/en/servers-systems"
        storageURL = "https://buy.hpe.com/us/en/storage"
        urlsToParse = [networkURL, serversURL, storageURL]

        for url in urlsToParse:
            print(f"Going to Starting URL {url}", file=sys.stderr)
            self.parseStartingPage(url)
            
        self.end()
        print(self.issues)
        self.formatIssues()

    def end(self):
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>Done<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", file=sys.stderr)
        print(self.partNumberCount)  
    
    def parseStartingPage(self, url):
        mainSoup = self.get_soup(url)
        if mainSoup:
            links = mainSoup.find_all('a', {"class": "hpe-card__link"})
            for link in links:
                href = link['href']
                full_url = 'https://buy.hpe.com/' +  href
                print(f"Going to shopping page URL {full_url}", file=sys.stderr)
                self.parseBuyingPage(full_url)      
        else:
            self.issues.append({"URL": url, "I":"Cant Open The Starting Page Link"})
        
    def parseBuyingPage(self, url):
        found = False
        visitedSite = []
        mainSoup = self.get_soup(url)
        if mainSoup:
            products = mainSoup.find_all('h2')
            for product in products:  
                links = product.find_all('a')
                for link in links:
                    href = link['href']
                    full_url = 'https://buy.hpe.com/' +  href
                    if full_url not in visitedSite:
                        visitedSite.append(full_url)
                        productPage = self.get_soup(full_url)
                        if productPage:
                            print(f"Found Buying Page {full_url}", file=sys.stderr)
                            productPageLinks = productPage.find_all('a')
                            foundQuickSpecsPage = False
                            for  productPageLink  in productPageLinks:
                                if not productPageLink.string:
                                    continue
                                if "PDF" in productPageLink.string:
                                    continue
                                if "Quick" in productPageLink.string or "Specs" in productPageLink.string:
                                    productPageHref = productPageLink['href']
                                    quickSpecsURL =  productPageHref
                                    print(f"Found Quick Specs at {quickSpecsURL}", file=sys.stderr)
                                    found = True
                                    seriesName, data, realaseDate = self.get_weird_soup(quickSpecsURL)
                                    if seriesName and data and realaseDate:
                                        result = self.parseQuickSpecsHTML(quickSpecsURL, seriesName, data, realaseDate, False, False)    
                                        if result["PartNumbers"][0]["pn"] !=  "":
                                            self.seriesParsed.append(result["SeriesName"])
                                            self.postData(result)
                                            break
                                        else:
                                            self.issues.append({"URL": quickSpecsURL, "I":"couldn't find Part numbers in the link"})
                                    
            nextPageLink  = mainSoup.find_all('a', class_="hpe-pagination__link")
            for link in nextPageLink:
                try: 
                    href = link['href']
                    nextPageLink = link 
                    break
                except:
                    nextPageLink = None
                
            if nextPageLink:
                full_url = 'https://buy.hpe.com/' +  href
                productPage = self.get_soup(full_url)
                products = productPage.find_all('h2')
                for product in products:
                    links = product.find_all('a')
                    for link in links:
                        href = link['href']
                        full_url = 'https://buy.hpe.com/' +  href
                        productPage = self.get_soup(full_url)
                        if productPage:
                            print(f"Found Buying Page {full_url}", file=sys.stderr)
                            productPageLinks = productPage.find_all('a')
                            foundQuickSpecsPage = False
                            for  productPageLink  in productPageLinks:
                                if not productPageLink.string:
                                    continue
                                if "PDF" in productPageLink.string:
                                    continue
                                if "Quick" in productPageLink.string or "Specs" in productPageLink.string:
                                    productPageHref = productPageLink['href']
                                    quickSpecsURL =  productPageHref
                                    print(f"Found Quick Specs at {quickSpecsURL}", file=sys.stderr)
                                    found = True
                                    seriesName, data, realaseDate = self.get_weird_soup(quickSpecsURL)
                                    if seriesName and data and realaseDate:
                                        result = self.parseQuickSpecsHTML(quickSpecsURL, seriesName, data, realaseDate, False, False)    
                                        if result["PartNumbers"][0]["pn"] !=  "":
                                            self.seriesParsed.append(result["SeriesName"])
                                            self.postData(result)
                                            break
                                        else:
                                            self.issues.append({"URL": quickSpecsURL, "I":"couldn't find Part numbers in the link"})
            if not found:
                self.issues.append({"URL": url, "I":"didn't find quick spec link"})
        else:
            self.issues.append({"URL": url, "I":"Cant Open The Buying Page Link"})



    def parseRows(self,  url, seriesName, data, realaseDate, hasSeenDescriptionText=False, hasSeenPartNumberText=False):
        """
        Parses nicely formatted rows of part numbers
        returns True if part numbers were found and False if no part numbers are found
        """
        indexTracker = 0
        order = "P"
        found = {
            'SeriesName': seriesName,
            'ReleaseDate': realaseDate,
            'PartNumbers': [{"pn": '', "description": "", "url": url}]
        }

        part_number_regex = re.compile(r"^(?=[A-Z0-9\-\.#]{6,}$)[A-Z0-9]+([-\.#][A-Z0-9]+)*=?(\s\(Spare\))?$")
        description_regex = re.compile(r"^(?=.*[a-zA-Z])([^\s]+\s+){2,}[^\s]+$")

        if data:
            print(f"found some part numbers", file=sys.stderr)
            for row in data:
                
                if len(row) == 1:
                    if part_number_regex.match(row[0]):
                        found['PartNumbers'][indexTracker]["pn"] = row[0]
                        print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                        found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                        indexTracker += 1
                    continue

                if len(row) == 2:
                    partNumber = row[1]
                    description = row[0]
                    if description_regex.match(description) and part_number_regex.match(partNumber):
                        found['PartNumbers'][indexTracker]["description"] = description                
                        found['PartNumbers'][indexTracker]["pn"] = partNumber
                        print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                        found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                        indexTracker += 1
                    continue

                for col in row:
                    if hasSeenPartNumberText and hasSeenDescriptionText:
                        if order == "D" and description_regex.match(col):
                            found['PartNumbers'][indexTracker]["description"] = col
                            order = "P"
                            if found['PartNumbers'][indexTracker]["pn"] != "":
                                print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                                found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                                indexTracker += 1
                                
                            continue
                        
                        if order == "P"  and part_number_regex.match(col):
                            found['PartNumbers'][indexTracker]["pn"] = col
                            order = "D"
                            if found['PartNumbers'][indexTracker]["description"] != "":
                                print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                                found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                                indexTracker += 1
                                
                            continue
                            
                    if "Description" in col or "description" in col:
                        hasSeenDescriptionText = True

                    if order == "":
                        order = "D"
                        continue
                    
                    if "SKU" in col or "sku" in col:
                        hasSeenPartNumberText = True    
                        if order == "":
                            order = "P"
                        continue

        if found["PartNumbers"][0]["pn"] != "":
            self.seriesParsed.append(found["SeriesName"])
            self.postData(found)
            return True
        
        return False            


    def parseQuickSpecsHTML(self, url, seriesName, data, realaseDate, hasSeenDescriptionText=False, hasSeenPartNumberText=False, order='D'):
        """
        Parses not nicely formatted rows of part numbers 
        """
        indexTracker = 0
        found = {
            'SeriesName': seriesName,
            'ReleaseDate': realaseDate,
            'PartNumbers': [{"pn": '', "description": "", "url": url}]
        }
        
        if not data:
            return found
        
        part_number_regex = re.compile(r"^(?=[A-Z0-9\-\.#]{6,}$)[A-Z0-9]+([-\.#][A-Z0-9]+)*=?(\s\(Spare\))?$")
        description_regex = re.compile(r"^(?=.*[a-zA-Z])([^\s]+\s+){2,}[^\s]+$")

        for row in data:
            
            row = list(set(row))
            
            if 'Description' in row or 'description' in row:
                hasSeenDescriptionText = True
            
            if  'SKU' in row or 'sku' in row:
                hasSeenPartNumberText = True  
            
            if len(row) > 3:
                continue
            
            if len(row) == 1:
                if part_number_regex.match(row[0]):
                    found['PartNumbers'][indexTracker]["pn"] = row[0]
                    
                    print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                    found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                    indexTracker += 1
                continue

            if len(row) == 2:
                partNumber = row[1]
                description = row[0]
                if description_regex.match(description) and part_number_regex.match(partNumber):
                    found['PartNumbers'][indexTracker]["description"] = description                
                    found['PartNumbers'][indexTracker]["pn"] = partNumber
                    print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                    found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                    indexTracker += 1
                continue

            for col in row:
                if hasSeenPartNumberText and hasSeenDescriptionText:
                    if order == "D" and description_regex.match(col):
                        found['PartNumbers'][indexTracker]["description"] = col
                        order = "P"
                        if found['PartNumbers'][indexTracker]["pn"] != "":
                            print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                            found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                            indexTracker += 1
                            
                        continue
                    
                    if order == "P"  and part_number_regex.match(col):
                        found['PartNumbers'][indexTracker]["pn"] = col
                        order = "D"
                        if found['PartNumbers'][indexTracker]["description"] != "":
                            print(f" found pair {found['PartNumbers'][indexTracker]} ", file=sys.stderr)
                            found['PartNumbers'].append({"pn": '', "description": "",  "url": url})
                            indexTracker += 1
                            
                        continue
                        
                if "Description" in col or "description" in col:
                    hasSeenDescriptionText = True

                if order == "":
                    order = "D"
                    continue
                
                if "SKU" in col or "sku" in col:
                    hasSeenPartNumberText = True    
                    if order == "":
                        order = "P"
                    continue

        return found            

if __name__ == "__main__":
    db = init_db.init("DevP3Systems", "TestHPWebScraper")
    # url =  "https://www.hpe.com/psnow/doc/c04545486.html?jumpid=in_pdp-psnow-qs"
    # seriesName, data, realaseDate = hpScraper(db).get_weird_soup(url)
    # print(hpScraper(db).parseQuickSpecsHTML(url,seriesName, data, realaseDate))
    hpScraper("TestHPWebScraper", db).start()
    