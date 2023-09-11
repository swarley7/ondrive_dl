from msdrive import OneDrive,SharePoint
import msdrive.exceptions
import sys
import argparse
import os
from datetime import datetime
import logging
import requests
import re
import json


from PyInquirer import prompt
from prompt_toolkit.validation import Validator, ValidationError


regex = re.compile(r'||\((.*)\)$')

store_metadata = True

parser = argparse.ArgumentParser(description='Description of your program')
parser.add_argument('-a','--accesstoken', help='')
parser.add_argument('-o','--outputdir', help='Directory to put files')
args = vars(parser.parse_args())

wanip = requests.get("https://ifconfig.me").text.strip()

current_date = datetime.now()
now = current_date.strftime('%Y%m%dT%H_%M')

logging.basicConfig(format=f'[%(asctime)s]_[IP:{wanip}]: %(message)s',     handlers=[
        logging.FileHandler(f"{now}_onedrivedl.log"), # log to file
        logging.StreamHandler() # log stderr
    ]
    , encoding='utf-8', level=logging.INFO)

class NumberValidator(Validator):

    def validate(self, document):
        try:
            int(document.text)
        except ValueError:
            raise ValidationError(message="Please enter a number",
                                  cursor_position=len(document.text))


def menu():
    top_level_menu = [
        {
            'type': 'list',
            'name': 'user_option',
            'message': 'OneDrive Interactive hax Client',
            'choices': ["replace_token","download","upload","list", "exit", "config"]
        }
    ]
    answers = prompt(top_level_menu)
    return answers['user_option']

def download(item_id, drive):
    logging.info("Retrieving item data")
    item_data = get_metadata(item_id, drive)
    current_date = datetime.now()
    now = current_date.strftime('%Y%m%dT%H_%M_%S.%f%z')
    outdir = args['outputdir'] 
    if outdir == None:
        questions = [

            {
                'type': "input",
                "name": "dst",
                "message": "Enter the target path",
            }
        ]
        answer = prompt(questions)
        outdir = answer.get("dst")

    try:
        if not os.path.isdir(outdir):
            os.mkdir(outdir)
    except Exception as e:
        logging.error(f"Problem making dir: {e}")

    logging.info(f"Downloading item: [{item_data['name']}] ([{item_data['id']}]) to [{outdir}/{now}-{item_id}-{sanitise(item_data['name'])}]")

    drive.download_item(item_id=item_id, file_path=(f"{outdir}/{now}-{item_id}-{sanitise(item_data['name'])}"))
    if store_metadata:
        with open(f"{outdir}/{now}-{item_id}-{sanitise(item_data['name'])}_metadata.json", 'w') as f:
            f.write(json.dumps(item_data))

def upload(cwd_items, drive):

    questions = [
        {
            'type': "input",
            "name": "src",
            "message": "Enter the Source Path",
        },
     {
            'type': "input",
            "name": "dst",
            "message": "Enter the file destination filename",
        }        
    ]
    answers = prompt(questions)
    src_file = answers.get("src")
    dest_filename = answers.get("dst")

    logging.info(f"Uploading local:[{src_file}] to OneDrive:[{dest_filename}]")
    try:
        drive.upload_item(item_path=dest_filename, file_path=src_file)
    except Exception as e:
        logging.error(e)
    

def replace_token():
    access_token = [
        {
            'type': 'input',
            'name': 'token',
            'message': 'Enter access token'        
        }
    ]
    answers = prompt(access_token)
    return login(answers.get("token"))

def login(accesstoken):
    logging.info("Attempting login to OneDrive")
    try:
        return OneDrive(accesstoken)
    except Exception as e:
        logging.error(f"Login failed: {e}")

def listdir(cwd, drive):
    print_cwd = cwd
    if cwd == "":
        print_cwd = "<ROOT>"
    logging.info(f"listing onedrive directory contents for [{print_cwd}]")
    list_items = drive.list_items(folder_path=cwd)
    for i in list_items['value']:
        listing_type = ""
        if "file" in i.keys():
            listing_type = "file"
        elif "folder" in i.keys():
            listing_type = "folder"
        logging.info(f"{i['name']} - ({i['id']}) [{listing_type}] [Modified: {i['lastModifiedDateTime']}]")
    # print(list_items)
    
    return list_items

def get_metadata(item_id, drive):
    return drive.get_item_data(item_id=item_id)


def sanitise(filename):
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c=='.']).rstrip()




def navigate_dir(cwd, cwd_items):
    choices = ['up_level','/', 'exit']
    choice_objects = {'up_level' : {"name": "up_level", "id":"" }, "/" : {"name": "/", "id":"" }, "exit": {"name": "exit", "id":"" }}
    for i in cwd_items['value']:
        choices.append(f'{i["name"]} - ({i["id"]})')
        if "file" in i.keys():
            list_type = "file"
        else:
            list_type = "folder"
        choice_objects[f'{i["name"]} - ({i["id"]})'] = {"name": i["name"], "id":i["id"], "list_type": list_type}
    dirlist = [
        {
            'type': 'list',
            'name': 'user_option',
            'message': f'Directory listing of [{cwd}]',
            'choices': choices
        }
    ]
    answers = prompt(dirlist)
    nav_item = answers.get("user_option")
    return choice_objects[nav_item]

def main():
    if not args["accesstoken"]:
        # prompt for token
        drive = replace_token()
    else:
        drive = login(args["accesstoken"])
    cwd = ""
    cwd_items = listdir(cwd, drive)
    while True:
        option = menu()
             
        if option == "replace_token":
            logging.info("Replacing access token.")
            drive = replace_token()
        if option == "exit":
            logging.info("Finished for the day.")
            sys.exit(0)
        if option == "config":
            pass
        if cwd_items == {}:
            try:                
                cwd_items = listdir(cwd, drive)
            except msdrive.exceptions.ItemNotFound as e:
                logging.error(f"Error accessing item [{navigation['name']}]: {e}")
                cwd = ""
                cwd_items = {}
                continue
        navigation = navigate_dir(cwd, cwd_items)
        if navigation["name"] == "exit" or navigation["name"] == "/":
            # flush everything
            cwd = ""
            cwd_items = {}
            continue
        if navigation["name"] == "up_level":
            cwd = os.path.split(cwd)[0]  
            continue          
        if option == "download":
            if navigation["list_type"] == "folder":
                # question = [] maybe handle whole folder download?
                cwd = navigation["name"]
                cwd_items = listdir(cwd, drive)
                break
            download(navigation["id"], drive)
        if option == "upload":
            upload(cwd_items, drive)           
        if option == "list":
            navigation = navigate_dir(cwd, cwd_items)
            cwd = navigation["name"]
            try:                
                cwd_items = listdir(cwd, drive)
            except msdrive.exceptions.ItemNotFound as e:
                logging.error(f"Error accessing item [{navigation['name']}]: {e}")
                cwd = ""
                cwd_items = {}
                continue      
        if option == "chdir":
            pass                 
if __name__ == "__main__":
    main()
# drive.upload_item(item_path="/Documents/new-or-existing-file.csv", file_path="new-or-existing-file.csv")