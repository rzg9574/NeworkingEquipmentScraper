Core Files and Their Roles:
    Each scraper targets a specific vendors website to get the part numbers, dates and description
    Files: arista_scraper.py, cisco_scraper.py, hp_scraper.py, ruckus_scraper.py

Each Scraper follows this general workflow:
    Initialize the scraper with a database connection and collection name(you can change the collection or database its sorted in by adding the params in the init function in the scraper_controllerpy file)
    Fetch HTML content using requests, BeautifulSoup, or Selenium (for dynamic content)
    search for the part numbers and product descriptions
    Store the extracted data in MongoDB


    Database Initialization (init_db.py)
    Handles MongoDB connection and initialization
    Supports clearing specific collections for a clean slate before a scraping session
    Uses credentials stored in the .env

    Scraper Controller (scraper_controller.py)
    Manages all scrapers centrally
    You can:
    Run all scrapers at the same time using threads
    Run a specific scraper based on a ScraperCode
    Includes an interface for testing scrapers against known partnumbers in the BRANDS collection 

    Scraper Tester (scraper_test.py)
    Validates the scrapers' output by comparing scraped part numbers against a known dataset
    Generates reports in CSV format:
    MatchedFoundPn: Part numbers found in both scraped data and known dataset
    NewUnknownPn: Part numbers found by the scraper but not in the known dataset
    NotFoundKnownPn: Part numbers in the known dataset but not scraped​

    Enums and Configurations (ScraperCode.py)
    Mapping between scraper codes and their respective vendors:
    A: Arista
    R: Ruckus
    C: Cisco
    H: HP Enterprise (HPE)​


Things to Know: 
    For pages with dynamically loaded content (HP's QuickSpecs pages), Selenium is used to render JavaScript and extract data

    Issues during scraping(bad links or missing data) are logged into text files for debugging in the IssueOutputs folder only hp and ciso scrappers do this beacuse arista and ruckes part numbers are stored in pdf so the pdf link is provided in the info that the scrapers parse along with the partnumbers and decsriptions 

    Ruckus and Arista parse PDFs for part numbers using PyPDF2

    While Running Ruckus and Arista will create these temp pdf files these are just the files that they are currentlly parseing once the scrapers are done runnig you can delete them 

    Make sure there is a folder called exports in the root dir while running the scrapers tester 


Add a New Scraper:
    Create a new scraper class similar to the existing vendor scrapers
    Implement the necessary methods it might be good to make if abstart class if nessary (start, get_soup, postData)
    Register the scraper in scraper_controller.py and assign a unique ScraperCode
    Modify the MongoDB document structure if new data attributes are added

