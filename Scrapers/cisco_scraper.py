# %%
import requests
from bs4 import BeautifulSoup
import re
from Scrapers import init_db
import os
from datetime import datetime
# %%



class CiscoScraper:
    parsedData = {}
    db_collection = None
    
    def __init__(self, collection, db):
        self.parsedData = {
            'SeriesName': '',
            'ReleaseDate': None,
            "EndOfSupportDate": None,
            "EndOfSaleDate": None,
            'PartNumbers': []
        }
        self.db = db
        self.db_collection = collection
        
        
    def formatIssues(self, issues):
        """
        Makes a txt file with issues that came up during the parse issues like bad links or not describe lists for the series not there
        """
        formatted_content = []
        for key, value in issues.items():
            formatted_content.append(
                f"Failed at this link----->{key} ---For this reason: {value}\n\n"
            )

        # Join the formatted content back into a string
        formatted_content_str = "\n".join(formatted_content)
        
        if os.path.exists("./IssueOutputs/CiscoIssuesOutput.txt"):
            os.remove("./IssueOutputs/CiscoIssuesOutput.txt")
        with open("./IssueOutputs/CiscoIssuesOutput.txt", "w") as text_file:
            text_file.write(formatted_content_str)
        

    def get_soup(self, url):
        try:
            if 'xlsx' in url:
                return None
            response = requests.get(url)
            if response.status_code==200:
                return BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.TooManyRedirects:
            return None

    def postData(self):
        """
        Posts the data to the mongodb and resets the parser varible 
        """
        collection = self.db.get_collection(self.db_collection)
        print("posting to db")
        id = collection.insert_one(self.parsedData).inserted_id

        self.parsedData = {
            'SeriesName': '',
            'ReleaseDate': None,
            "EndOfSupportDate": None,
            "EndOfSaleDate": None,
            'PartNumbers': []
        }
        return id
    

    def start(self):
        base_url = 'https://www.cisco.com'
        main_url = f'{base_url}/c/en/us/support/all-products.html'
        main_soup = self.get_soup(main_url)
        data_sheet_counter = 0
        issue = {}
        
        if main_soup:
            #print(main_soup.prettify())

            # Find all category links in the "All Product and Technology Categories" section
            section = main_soup.find(string="All Product and Technology Categories")
            
            #print(section)
            if section:
                #print("found")
                # Find the <table> element following the all product tag
                table_element = section.find_next('table')

                if table_element:
                    #extract all <a> tag in the table
                    links = table_element.find_all('a', href = True)
                    #get the links
                    print(len(links))
                    for link in links:
                        #print(link)
                        href = link['href']
                        text = link.text.strip()
                        full_url = 'https:' + href if href.startswith("//") else href
                        print(f"{text}: {full_url}")
                        try:
                            counter , issue_dict = self.get_product_support_page(full_url, base_url)
                            data_sheet_counter += counter
                            issue = {**issue, **issue_dict}
                        except requests.exceptions.TooManyRedirects:
                            print(f"Too many redirects at {full_url}")
                else:
                    print("Table element not found.")
                    # breakpoint()
            else:
                print("Section with 'All Product and Technology Categories' not found.")
                # breakpoint()
        else:
            print(f'Failed to retrieve the page, status code: {main_soup}')
            # breakpoint()
            
        self.formatIssues(issue)    
        
        return data_sheet_counter
  
    def get_product_support_page(self, url, base_url):
        data_sheet_counter = 0
        issue = {}
        
        soup = self.get_soup(url)

        if soup:
            #print(soup.prettify())

            section = soup.find('div', id = 'allSupportedProducts')
            if section:
                # Find all <a> tags within this div
                links = section.find_all('a', href=True)
                
                for link in links:
                    href = link['href']
                    text = link.text.strip()
                    full_url = base_url + href if href.startswith('/') else href
                    print(f"{text}: {full_url}")
                    try:
                        counter , issue_dict = self.get_series_release_date(full_url, base_url)
                        data_sheet_counter += counter
                        issue = {**issue, **issue_dict}
                    except requests.exceptions.TooManyRedirects:
                        print(f"Too many redirects at {full_url}")
                        # breakpoint()
            else:
                print("Div with id 'allSupportedProducts' not found.")
                # breakpoint()
        else:
            print(f'Failed to retrieve the product category page.')
            # breakpoint()
        return data_sheet_counter, issue
    # %%
    def get_series_release_date(self, url,base_url):
        print("looking for date")
        data_sheet_counter = 0
        issue = {}      
        soup = self.get_soup(url)
        if soup:
            seriesName = soup.find('h1')
            if seriesName:
                if seriesName.get_text(strip = True) == "Cisco Compact Nodes":
                    print("hi")
                self.parsedData['SeriesName'] = seriesName.get_text(strip = True)
            else:
                self.parsedData['SeriesName'] = ''
            # Locate the element containing the "Series Release Date"
            tables = soup.find_all('table', class_=lambda value: value and 'birth-cert-table' in value)
            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    header = row.find('th')
                    data = row.find('td')

                    if header and data:
                        header_text = header.get_text(strip = True)
                        data_text = data.get_text(strip = True)
                        if any(keyword in header_text.lower() for keyword in ['date','release','end' ]):
                            print(f'{header_text} : {data_text}')
                            if data_text == "Pre-1999":
                                self.parsedData['ReleaseDate'] = datetime.strptime('1960-1-1', '%Y-%m-%d')
                            else: 
                                if any(keyword in header_text.lower() for keyword in ['release']):   
                                    self.parsedData['ReleaseDate'] = datetime.strptime(data_text, '%d-%b-%Y')
                                elif any(keyword in header_text.lower() for keyword in ['sale']):   
                                    self.parsedData['EndOfSaleDate'] = datetime.strptime(data_text, '%d-%b-%Y')
                                elif any(keyword in header_text.lower() for keyword in ['support']):   
                                    self.parsedData['EndOfSupportDate'] = datetime.strptime(data_text, '%d-%b-%Y')
                    
                if 'ReleaseDate' not in self.parsedData:
                    self.parsedData['ReleaseDate'] = None
                if 'EndOfSaleDate' not in self.parsedData:
                    self.parsedData['EndOfSaleDate'] = None
                if 'EndOfSupportDate' not in self.parsedData:
                    self.parsedData['EndOfSupportDate'] = None

            describe_list = soup.find('dl')
            if describe_list:
                info_documents_section = soup.find('dd', {'id':'info-documents'})

                if info_documents_section:
                    # Find all <a> tags within this section
                    links = info_documents_section.find_all('a')
                    
                    # Filter the links to find those containing 'data sheet' in their text or id
                    for link in links:
                        link_text = link.get_text(strip=True).lower()
                        link_id = link.get('id', '').lower()
                        if 'data sheet' in link_text or 'data sheet' in link_id or self.parsedData['SeriesName'] in link_text or self.parsedData['SeriesName'] in link_id or 'end-of-sale' in link_text or 'end-of-sale' in link_id:
                            # Print the link URL
                            href = link['href']
                            if href.endswith('.pdf'):
                                print('datasheet is pdf, skip now and wait for future implementation.')
                                # breakpoint()
                                continue

                            if href.startswith('#') :
                                continue
                            full_url = base_url + href if href.startswith('/') else href
                            print(f"Found datasheet link: {full_url}")
                            
                            try:
                                issue_dict = self.get_partnum_descrip_pair(full_url)
                                data_sheet_counter += 1
                                issue = {**issue, **issue_dict}
                                
                            except requests.exceptions.RequestException:
                                continue

                    if len(self.parsedData["PartNumbers"]) != 0:
                        self.postData()     
                else:
                    print("The 'info-documents' section was not found.")
                    issue[url]='No describe List'
            else:
                print(f"The page {url} doesn't contain describe list")
                issue[url]='No describe List'
        else:
            print(f'No Support Page for this url: {url}')
            issue[url]='Bad Link'

        return data_sheet_counter, issue
    
    def get_partnum_descrip_pair(self, url):
        print("looking for part number")
        found = False
        issue={}
        soup = self.get_soup(url)
        # Find the "Ordering Information" section
        if soup:
            # Step 1: Find all elements containing "Ordering information" (case-insensitive)
            ordering_info_elements = soup.find_all(string=re.compile(r'(ordering information|ordering|order information|support)', re.IGNORECASE))
            # Step 2: Filtere to find the cpTableCaptionCMT class
            for element in ordering_info_elements:
                p_element = element.find_parent('p', class_='pTableCaptionCMT')
                if p_element:
                    # Step 3: Locate all tables following the p element
                    tables = p_element.find_all_next('table')

                    for table in tables:
                        # Step 4: Check the column name part
                        thead = table.find('thead')
                        if thead:
                            data = self.handleTHead(thead, table, url)
                            if data != [] and data is not None:
                                found = True 
                                self.parsedData['PartNumbers'].extend(data)
    
                        else:
                            tdata = table.find_all('td')
                            if tdata:
                                data = self.handleTData(tdata, url)
                                if data != [] and data is not None:
                                    found = True 
                                    self.parsedData['PartNumbers'].extend(data)
               
                                   
            if found == False:
                ordering_info_elements = soup.find_all(string=re.compile(r'(part numbers|part|product part numbers)', re.IGNORECASE))
                # Step 2: Filtere to find the cpTableCaptionCMT class
                for element in ordering_info_elements:
                    p_element = element.find_parent('p', class_='pTableCaptionCMT')
                    if p_element:
                        # Step 3: Locate all tables following the p element
                        tables = p_element.find_all_next('table')

                        for table in tables:
                            # Step 4: Check the column name part
                            thead = table.find('thead')
                            if thead:
                                data = self.handleTHead(thead, table, url)
                                if data != [] and data is not None:
                                    found = True 
                                    self.parsedData['PartNumbers'].extend(data)
                            else:
                                tdata = table.find_all('td')
                                if tdata:
                                    data = self.handleTData(tdata, url)
                                    if data != [] and data is not None:
                                        found = True 
                                        self.parsedData['PartNumbers'].extend(data)

                    if 'PartNumbers' not in self.parsedData:
                        self.parsedData['PartNumbers'] = []                
        else:
            print('Soup is None, url not valid')    
            issue[url]='Soup is None, url not valid'
            # breakpoint()
        return issue
    




    def handleTHead(self, thead, table, url):
        #check if the table has the column names I want
        headers = [header.get_text(strip=True).lower() for header in thead.find_all('td')]
        # also handle situation when cisco switch the order of part number and description
        # CISCO!!!!!!
        partnumber_idx = None
        description_idx = None
        foundDiscription = False
        foundPartNumber = False
        partNumberSet = set()

        for index, header in enumerate(headers):
            if any(keyword in header for keyword in ['part number', 'product number', 'product id', 'end-of-sale', 'model', 'partnumber']):
                if not any(exclude in header for exclude in ['replacement', 'accessories', 'specifications']):
                    if not foundPartNumber and not foundDiscription:
                        partnumber_idx = 0
                        description_idx = 1
                        foundPartNumber = True
                    elif foundDiscription and not foundPartNumber:
                        foundPartNumber = True

                    
            if any(keyword in header for keyword in ['description', 'product description', 'product name', 'productname']):
                if not any(exclude in header for exclude in ['replacement', 'accessories', 'specifications']):
                    if not foundDiscription and not foundPartNumber:
                        description_idx = 0
                        partnumber_idx = 1
                        foundDiscription = True
                    elif foundPartNumber and not foundDiscription:
                        foundDiscription = True

            if foundDiscription and foundPartNumber:
                break        

        if foundPartNumber:
            # Step 5: if the column name found, find the tbody to extract data
            tbody = table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                partNumbersList = []
                partNumberSplit = []
                for row in rows:
                    columns = row.find_all('td')
                    if len(columns) > max(partnumber_idx, description_idx):
                        partnumber = columns[partnumber_idx].get_text(strip = True)
                        if len(partnumber) <= 3:
                            continue
                        if "●" in partnumber:
                            partNumberSplit = partnumber.split("●")
                        description = columns[description_idx].get_text(strip = True)

                        if len(partNumberSplit) == 0:
                            if "CON-SNT" in partnumber or "BULK" in partnumber or partnumber == "":
                                continue   
                            print(f"Part Number: {partnumber}, Description: {description}")
                            if partnumber.strip() != "":
                                partNumbersList.append({"PartNumber" : partnumber, "Description": description, "URL": url})
                                partNumberSet.add(partnumber)
                        else:
                            for part in partNumberSplit:
                                if len(part) <= 3:
                                    continue
                                if part not in partNumberSet:
                                    if "CON-SNT" in part or "BULK" in part or part == "":
                                        continue   
                                    print(f"Part Number: {part}, Description: {description}")
                                    if part.strip() != "":
                                        partNumbersList.append({"PartNumber" : part, "Description": description, "URL": url})
                                        partNumberSet.add(part)

                return partNumbersList
            else:
                print('No tbody found')
                return []
            
                        # breakpoint()
     

    def handleTData(self, tdata, url):
        partNumbersList = []
        partnumber_idx = None
        description_idx = None
        hasPartNumber = False
        hasDiscription = False
        skipNextDiscripton = False
        tdSplit = []

        partNumberSet = set()

        """
        Loops through once just to establish where the PN and Discription indexs are 
        """
        for index, td in enumerate(tdata):
            td = td.get_text(strip=True).lower()
            
            if any(keyword in td for keyword in ['part number', 'product number', 'product id', 'end-of-sale', 'model', 'partnumber']):
                if not any(exclude in td for exclude in ['replacement', 'accessories', 'specifications']):
                    if not hasPartNumber:
                        hasPartNumber = True
                        partnumber_idx = index
            if any(keyword in td for keyword in ['description', 'product description', 'product name', 'productname']):
                if not any(exclude in td for exclude in ['replacement', 'accessories', 'specifications']):
                    if not hasDiscription:
                        hasDiscription = True
                        description_idx = index

            if hasPartNumber and hasDiscription:
                break
            
        
        """
        If We Found A PN we dont care if there is discription or not
        """
        if hasPartNumber:

            """
            Loop Through again and parse the PN and discriptions  based on the indexs 
            set before 
            """
            for index, td in enumerate(tdata):
                td = td.get_text(strip=True)
                if td == "" or td.strip() == "":
                    continue
                if index == partnumber_idx or index == description_idx:
                    continue

                if "part number" in td.lower():
                    skipNextDiscripton = True
                    continue
                    
                if "●" in td:
                    tdSplit = td.split("●")

                if len(tdSplit) == 0:
                    data = self.validatePartNumbers(td, tdata, index, skipNextDiscripton, hasDiscription, url)
                    if data:
                        if data[0]["PartNumber"] != "": 
                            partNumbersList.extend(data)

                else:
                    for tempTD in tdSplit:
                        data = self.validatePartNumbers(tempTD, tdata, index, skipNextDiscripton, hasDiscription, url)
                        if data:
                            if data[0]["PartNumber"] != "": 
                                partNumbersList.extend(data)             
            else:    
                for pn in partNumbersList:
                    if pn["PartNumber"].strip() == "":
                        partNumbersList.remove(pn)
                        continue
                    if pn["PartNumber"] in partNumberSet:
                        partNumbersList.remove(pn)
                        continue
                    if len(pn["PartNumber"]) <= 3:
                        partNumbersList.remove(pn)
                        continue
                    partNumberSet.add(pn["PartNumber"])
                    partNumberPrint = pn["PartNumber"]
                    discriptionPrint = pn["Description"]
                    print(f"Part Number: {partNumberPrint}, Description: {discriptionPrint}")
                return partNumbersList 
        return partNumbersList           
  



    def validatePartNumbers(self, td, tdata, index, skipNextDiscripton, hasDiscription, url):
        partNumbersList = [{"PartNumber" : "", "Description": "", "URL": url}]
        indexTracker = 0
        isPartNumber = re.search(r"^(?=[A-Z0-9\-\.]{6,}$)*[A-Z0-9]+([-\.][A-Z0-9]+)*=?(\s\(Spare\))?$", td)
        isDiscription = re.search(r"^([^\s]+\s+){2,}[^\s]+$", td)
        if hasDiscription == False:
                #if there is no discription tag but there is a part number tag the discription tag is
                # probably called somthing else so it should skip the first disrciption LIKE tag it sees
                # beacuse that will be the header
                hasDiscription = True
                skipNextDiscripton = True

        #if part number like text was found
        if isPartNumber:
            if "CON-SNT" in td or "BULK" in td or td == "":
                skipNextDiscripton = True
                return None     
            
            if partNumbersList[indexTracker]["PartNumber"] == "":
                partNumbersList[indexTracker]["PartNumber"] = td
            else:
                #found two partnumbers without finding a discription so
                # loop through to find next discription 
                found = False
                for tempIndex, tempTd in enumerate(tdata):
                    tempTd = tempTd.get_text(strip=True)
                    if tempIndex <= index:
                        continue
                    if re.search("^([^\s]+\s+){2,}[^\s]+$", tempTd):
                        partNumbersList[indexTracker]["Description"] = tempTd
                        partNumbersList.append({"PartNumber" : "", "Description": "", "URL": url})
                        indexTracker += 1
                        found = True
                        break
                if found == False:
                    partNumbersList[indexTracker]["Description"] = "Couldnt find discription"
                    partNumbersList.append({"PartNumber" : "", "Description": "", "URL": url})
                    indexTracker += 1
                partNumbersList[indexTracker]["PartNumber"] = td
                
            if partNumbersList[indexTracker]["Description"] != "":
                partNumbersList.append({"PartNumber" : "", "Description": "", "URL": url})
                indexTracker += 1
            return partNumbersList 
        elif isDiscription:
            
            if skipNextDiscripton or td == "":
                skipNextDiscripton = False
                return [] 
            if partNumbersList[indexTracker]["Description"] == "":
                partNumbersList[indexTracker]["Description"] = td
            else:
                #loop through to find next part number
                found = False
                for tempIndex, tempTd in enumerate(tdata):
                    tempTd = tempTd.get_text(strip=True)
                    if tempIndex <= index:
                        continue 
                    if re.search("^(?=[A-Z0-9\-\.]{6,}$)*[A-Z0-9]+([-\.][A-Z0-9]+)*=?(\s\(Spare\))?$", tempTd):
                        partNumbersList[indexTracker]["PartNumber"] = tempTd
                        partNumbersList.append({"PartNumber" : "", "Description": "", "URL": url})
                        indexTracker += 1
                        found = True
                        break
                if found == False:
                    partNumbersList.append({"PartNumber" : "", "Description": "", "URL": url})
                    indexTracker += 1
                partNumbersList[indexTracker]["Description"] = td
            if partNumbersList[indexTracker]["PartNumber"] != "":
                partNumbersList.append({"PartNumber" : "", "Description": "", "URL": url})
                indexTracker += 1
            return partNumbersList
        return partNumbersList


if __name__ == "__main__":
    db = init_db.init("DevP3Systems", "TestCiscoWebScrapper")
    data_sheet_count = CiscoScraper("TestCiscoWebScrapper", db).start()
    #CiscoScraper(db).get_partnum_descrip_pair("https://www.cisco.com/c/en/us/products/collateral/collaboration-endpoints/spark-room-kit-series/room-kit-eq-ds.html#Orderinginformation")
    print(data_sheet_count)
