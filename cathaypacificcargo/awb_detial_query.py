import asyncio
import os
import sys
import traceback
from pyppeteer import browser, launch
import signal
import kill_chrome
import pathlib
import time
from datetime import datetime
import common
import awb_interesting_generator
from bs4 import BeautifulSoup
import multiprocessing

# lscpu | egrep 'Model name|Socket|Thread|NUMA|CPU\(s\)'
MAX_TASK_COUNT = multiprocessing.cpu_count() 

async def getTextFromFrame(page, selector, timeout=30000):
    try:
        ##time.sleep(2)
        await page.waitForSelector(selector, { "timeout": timeout })
        element = await page.querySelector(selector)
        text = await page.evaluate('(element) => element.textContent', element)
        return text
    except:
        return ""

def printError(e):
    error_class = e.__class__.__name__ #取得錯誤類型
    detail = e.args[0] #取得詳細內容
    cl, exc, tb = sys.exc_info() #取得Call Stack
    lastCallStack = traceback.extract_tb(tb)[-1] #取得Call Stack的最後一筆資料
    fileName = lastCallStack[0] #取得發生的檔案名稱
    lineNum = lastCallStack[1] #取得發生的行號
    funcName = lastCallStack[2] #取得發生的函數名稱
    errMsg = "File \"{}\", line {}, in {}: [{}] {}".format(fileName, lineNum, funcName, error_class, detail)
    logger.error(errMsg)

def printMsg(number, msg):
    logger.info(f"[{number}] {msg}")

async def launch_browser():
    if os.name == 'nt':
            chromium_path = "C:/Users/Jimmy Wu/AppData/Local/pyppeteer/pyppeteer/local-chromium/588429/chrome-win32/chrome.exe"
    else:
        chromium_path = "/usr/bin/chromium-browser"
    headless = True # True: 沒有瀏覽器
    options = {
        "args": [
            #'--disable-gpu',
            #'--disable-dev-shm-usage',
            ##'--disable-setuid-sandbox',
            #'--no-first-run',
            #'--no-zygote',
            #'--deterministic-fetch',
            #'--disable-features=IsolateOrigins',
            #'--disable-site-isolation-trials',
            '--no-sandbox',
            f'--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36"'
        ],
        "headless": headless,
        "executablePath" :  chromium_path,
    }
    return await launch(options) #'executablePath': exepath,, 'slowMo': 30

async def load_html_by_number(number):

    try:
        url = f"https://www.cathaypacificcargo.com/ManageYourShipment/TrackYourShipment/tabid/108/SingleAWBNo/{number}/language/en-US/Default.aspx"
        browser = await launch_browser()
        printMsg(number, "launch browser")
        page = await browser.newPage()
        printMsg(number, "new pagge")

        #await page.setUserAgent(userAgent)
        await page.setExtraHTTPHeaders({
                'authority' :'www.cathaypacificcargo.com',
                'path': '/en-us/manageyourshipment/trackyourshipment.aspx',
                'upgrade-insecure-requests': '1',
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'accept-encoding': 'gzip, deflate, br',
                'accept-language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,ko;q=0.5'
            })

        printMsg(number, f"go to {url}")
        #await page.setViewport({'width': 0, 'height': 0})
        await page.goto(url, 
            { 
                "waitUntil" : "load",
                "timeout": 0 
            })                               
        
        return await page.content()
    except Exception as e:
        printError(e)
    finally:
        await browser.close()
        printMsg(number, "close browser")

async def queryTask(number, taskId):
    t = time.process_time()
    printMsg(number, f"Task{taskId} start.")

    try:  
       
        html_doc = await load_html_by_number(number)
        soup = BeautifulSoup(html_doc, 'lxml')
        
        origin = soup.select_one("#FreightStatus-Origin").text
        logger.info(f"origin={origin}")
        destination = soup.select_one("#FreightStatus-Destination").text
        logger.info(f"destination={destination}")

        status = ""
        flight = ""
        if origin and destination: 
            tag = soup.select_one("#Latest_Status-Content > div > div:nth-child(2)")
            if tag :
                status = tag.text
                logger.info(f"status={status}")

            tag = soup.select_one("#Latest_Status-Content > div > div:nth-child(5)")
            if tag:
                flight = tag.text
                logger.info(f"flight={flight}")
            printMsg(number, f"{origin} -> {destination} , {status} {flight}")

        async with locker:
            with open(interesting_detial_result_path, "a") as f: 
                f.write(f"{number},{origin},{destination},{status},{flight}\n")
    except Exception as e:
        printError(e)
    finally:
        printMsg(number, "close page")
        elapsed_time = time.process_time() - t
        printMsg(number, f"Task{taskId} done. (use {elapsed_time} s)")

async def run_batch_task(loop, batch_numbers):
    task_list =[]
    i = 0
    for number in batch_numbers:
        t = loop.create_task(queryTask(number, i))
        task_list.append(t)
        i+=1
    
    await asyncio.wait(task_list)


def signal_handler(signum, frame):
    print('signal_handler: caught signal ' + str(signum))
    if signum == signal.SIGINT.value:
        print('SIGINT')
        loop.close()
        kill_chrome.main()
        sys.exit(1)

if __name__ == '__main__': 

    global interesting_detial_result_path
    global interesting_awb_path
    global locker
    global loop
    global logger

    worker_folder = pathlib.Path(__file__).parent.resolve()
    data_folder = os.path.join(worker_folder, 'data')

    logger = common.init_logger(worker_folder, "awb_detial_query")
    #awb_interesting_generator.main()
    # logger.info(f"chromium_path={chromium_path}")
    logger.info(f"worker_folder={worker_folder}" )
    logger.info(f"data_folder={worker_folder}" )
    logger.info(f"log_folder={worker_folder}" )


    already_query_numbers = []
    interesting_detial_result_path =  os.path.join(data_folder, "interesting_detial_result.csv")
    with open(interesting_detial_result_path, "r") as f: 
       for row in f:
           number = row.split(",")[0] 
           if number not in already_query_numbers:
                already_query_numbers.append(number)
    logger.info(f"interesting_detial_result.csv have { len(already_query_numbers) } lines.")

    interesting_awb_numbers = []
    interesting_awb_path =  os.path.join(data_folder, "interesting_awb_list.txt")
    with open(interesting_awb_path, 'r') as f:
       for row in f:
           number = row.strip()
           if number not in interesting_awb_numbers:
                interesting_awb_numbers.append(number)
    logger.info(f"interesting_awb_list.txt have { len(interesting_awb_numbers) } lines.")
    interesting_awb_numbers.reverse()

    signal.signal(signal.SIGINT, signal_handler)
    #print(signal.SIGINT)

    batch_numbers= []
    locker = asyncio.Lock()
    #loop = asyncio.new_event_loop()
    #asyncio.set_event_loop(loop)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for number in interesting_awb_numbers:
        number = number.replace("\n", "")
        if not number :
            continue

        if number in already_query_numbers:
            logger.info(f"AWB {number} already get detial.")
            continue
        
        batch_numbers.append(number)
        #print(f"number={number}")
        
        if len(batch_numbers) == MAX_TASK_COUNT:
            ssss = ",".join(batch_numbers)
            logger.info(f"=====> batch task start")
            loop.run_until_complete(run_batch_task(loop, batch_numbers))
            logger.info(f"=====> batch task all done")
            batch_numbers.clear()
    
    loop.close()         
    #logger.info("kill alll chrome")
    #kill_chrome.main() 
#asyncio.get_event_loop().run_until_complete(main())

