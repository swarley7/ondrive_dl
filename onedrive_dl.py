import sys
import argparse
import os
import logging
import json
import re
import requests
from datetime import datetime, timedelta

from dateutil.parser import parse as date_parse

# Third-party libs
from msdrive import OneDrive, SharePoint
import msdrive.exceptions
from PyInquirer import prompt
from prompt_toolkit.validation import Validator, ValidationError

store_metadata = True

parser = argparse.ArgumentParser(description='OneDrive Interactive Client')
parser.add_argument('-a','--accesstoken', help='Access token')
parser.add_argument('-o','--outputdir', help='Directory to put files')
args = vars(parser.parse_args())

wanip = requests.get("https://ifconfig.me").text.strip()
current_date = datetime.now()
now = current_date.strftime('%Y%m%dT%H_%M')

logging.basicConfig(
    format=f'[%(asctime)s]_[IP:{wanip}]: %(message)s',
    handlers=[
        logging.FileHandler(f"{now}_onedrivedl.log"),  # log to file
        logging.StreamHandler()                        # log stderr
    ],
    encoding='utf-8',
    level=logging.INFO
)

def ask(questions):
    """
    Wrapper around PyInquirer's prompt() to disable mouse support and
    avoid crashes if the user aborts/cancels. Returns the answers dict
    or None if canceled.
    """
    try:
        answers = prompt(questions, mouse_support=False)
        return answers
    except KeyboardInterrupt:
        return None

def sanitise(filename):
    """
    Strip out characters that might be problematic on the local filesystem.
    """
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c=='.']).rstrip()

def get_metadata(item_id, drive):
    """
    Fetch item metadata from OneDrive by item ID.
    """
    return drive.get_item_data(item_id=item_id)

def download(item_id, drive, outdir=None):
    """
    Download a single file by item_id.
    If 'outdir' is None, we check args["outputdir"], and if still None,
    prompt the user for a directory.
    """
    logging.info("Retrieving item data...")
    item_data = get_metadata(item_id, drive)
    current_date = datetime.now()
    now_str = current_date.strftime('%Y%m%dT%H_%M_%S.%f%z')

    if not outdir:
        outdir = args["outputdir"]

    if not outdir:
        questions = [{
            'type': "input",
            "name": "dst",
            'message': "Enter the local directory path to save into:",
        }]
        answer = ask(questions)
        if not answer or "dst" not in answer:
            logging.warning("Download canceled by user.")
            return
        outdir = answer.get("dst")

    try:
        if not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        logging.error(f"Problem making dir: {e}")
        return

    base_name = sanitise(item_data['name'])
    local_filename = f"{now_str}-{item_id}-{base_name}"
    full_path = os.path.join(outdir, local_filename)

    logging.info(f"Downloading item: [{item_data['name']}] "
                 f"([{item_data['id']}]) to [{full_path}]")

    drive.download_item(item_id=item_id, file_path=full_path)

    if store_metadata:
        meta_path = f"{full_path}_metadata.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(item_data, indent=2))

### OLD ID-BASED RECURSION (Not used in the menu, but kept for reference) ###
def download_entire_folder(item_id, drive, outdir=None):
    """
    Recursively download an entire folder (and subfolders) by item_id (ID-based).
    If outdir is None, we prompt (or use args["outputdir"]).

    This can fail if your item_id is a 'special folder' that doesn't actually hold
    the real contents. The new approach is path-based (below).
    """
    folder_data = get_metadata(item_id, drive)
    folder_name = sanitise(folder_data['name'])

    if not outdir:
        outdir = args["outputdir"]

    if not outdir:
        questions = [{
            'type': "input",
            "name": "dst",
            "message": "Enter the local directory path to save this folder into:",
        }]
        answer = ask(questions)
        if not answer or "dst" not in answer:
            logging.warning("Download folder canceled by user.")
            return
        outdir = answer.get("dst")

    local_folder_path = os.path.join(outdir, folder_name)
    try:
        os.makedirs(local_folder_path, exist_ok=True)
    except Exception as e:
        logging.error(f"Problem creating folder '{local_folder_path}': {e}")
        return

    logging.info(f"Downloading folder: [{folder_name}] (ID: {item_id}) to [{local_folder_path}]")

    if store_metadata:
        meta_path = os.path.join(local_folder_path, f"{folder_name}_metadata.json")
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(folder_data, f, indent=2)

    try:
        children = drive.list_items(parent_id=item_id)
    except msdrive.exceptions.ItemNotFound:
        logging.error(f"Folder not found or cannot be listed: {item_id}")
        return

    for child in children.get('value', []):
        child_id = child['id']
        child_name = child['name']
        parent_ref = child.get('parentReference', {}).get('id', '')
        if parent_ref != item_id:
            logging.warning(
                f"Skipping '{child_name}' (ID: {child_id}) because its parent "
                f"doesn't match the current folder: {parent_ref} != {item_id}"
            )
            continue

        if 'folder' in child:
            download_entire_folder(child_id, drive, local_folder_path)
        elif 'file' in child:
            download(child_id, drive, outdir=local_folder_path)
        else:
            logging.warning(f"Unknown item type for {child_name} (ID: {child_id}). Skipping.")

def download_entire_folder_by_path(folder_path, drive, outdir=None, visited=None):
    """
    Recursively downloads everything in a OneDrive folder by path, e.g. "Desktop".
    This matches your path-based approach used by 'listdir(cwd, drive)'.
    We avoid ID mismatches by simply building subpaths.

    Args:
      folder_path: The current OneDrive path (e.g. "", "Desktop", "Desktop/SubFolder")
      drive: The OneDrive instance
      outdir: Where to store local files/folders
      visited: A set of folder paths we've processed (avoid cycles).

    Usage:
      download_entire_folder_by_path(cwd, drive)
    """
    if visited is None:
        visited = set()

    # If we've visited this path already, skip
    if folder_path in visited:
        logging.warning(f"Skipping folder path '{folder_path}' (already visited).")
        return
    visited.add(folder_path)

    # Decide local folder name from the tail of folder_path
    if folder_path:
        folder_name = os.path.basename(folder_path.rstrip("/"))
    else:
        folder_name = "ROOT"
    folder_name = sanitise(folder_name)

    # If no outdir, check args or prompt
    if not outdir:
        outdir = args.get("outputdir")
    if not outdir:
        questions = [{
            'type': "input",
            "name": "dst",
            "message": f"Enter local directory path to save this folder '{folder_path}' into:",
        }]
        answer = ask(questions)
        if not answer or "dst" not in answer:
            logging.warning("Download folder (by path) canceled by user.")
            return
        outdir = answer["dst"]

    local_folder_path = os.path.join(outdir, folder_name)
    os.makedirs(local_folder_path, exist_ok=True)

    logging.info(f"Downloading folder path: [{folder_path}] => [{local_folder_path}]")

    # List items by folder_path
    try:
        children = drive.list_items(folder_path=folder_path)
    except msdrive.exceptions.ItemNotFound:
        logging.error(f"Folder path not found: {folder_path}")
        return

    for child in children.get('value', []):
        child_name = child['name']

        if 'folder' in child:
            # Build subpath: "Desktop/SubFolder" or "ROOT/SubFolder" if you want that approach
            # If folder_path == "", subpath is just child_name
            # else "folder_path/child_name"
            if folder_path:
                sub_path = f"{folder_path}/{child_name}"
            else:
                sub_path = child_name
            download_entire_folder_by_path(sub_path, drive, outdir=local_folder_path, visited=visited)

        elif 'file' in child:
            # Download a single file by ID
            download(child['id'], drive, outdir=local_folder_path)
        else:
            logging.warning(f"Unknown item type '{child_name}' => skipping.")

def upload(drive):
    """
    Upload a local file to OneDrive.
    """
    questions = [
        {
            'type': "input",
            "name": "src",
            "message": "Enter the local source file path:",
        },
        {
            'type': "input",
            "name": "dst",
            "message": "Enter the OneDrive destination path/filename:",
        }
    ]
    answers = ask(questions)
    if not answers or "src" not in answers or "dst" not in answers:
        logging.warning("Upload canceled by user.")
        return

    src_file = answers.get("src")
    dest_filename = answers.get("dst")

    logging.info(f"Uploading local:[{src_file}] to OneDrive:[{dest_filename}]")
    try:
        drive.upload_item(item_path=dest_filename, file_path=src_file)
    except Exception as e:
        logging.error(f"Upload failed: {e}")

def replace_token():
    """
    Prompt for a new access token
    """
    access_token = [
        {
            'type': 'input',
            'name': 'token',
            'message': 'Enter access token:'
        }
    ]
    answers = ask(access_token)
    if not answers or "token" not in answers:
        logging.warning("Replace token canceled by user.")
        return None
    return login(answers.get("token"))

def login(accesstoken):
    """
    Instantiate the OneDrive object with the given token
    """
    logging.info("Attempting login to OneDrive...")
    try:
        drive_obj = OneDrive(accesstoken)
        logging.info("Login successful.")
        return drive_obj
    except Exception as e:
        logging.error(f"Login failed: {e}")
        return None

def listdir(cwd, drive):
    """
    List items in the current OneDrive folder path (string-based approach).
    Return the raw response from drive.list_items(folder_path=cwd)
    """
    display_path = cwd if cwd else "<ROOT>"
    logging.info(f"Listing OneDrive directory contents for [{display_path}]")

    items = drive.list_items(folder_path=cwd)  # path-based

    # compare each item's lastModifiedDateTime to now-3months
    three_months_ago = datetime.now() - timedelta(days=90)

    for i in items['value']:
        if "file" in i:
            listing_type = "file"
        elif "folder" in i:
            listing_type = "folder"
        else:
            listing_type = "?"

        modified_str = i.get('lastModifiedDateTime','?')
        is_recent = False
        if modified_str and modified_str != '?':
            try:
                modified_dt = date_parse(modified_str)
                if modified_dt > three_months_ago:
                    is_recent = True
            except Exception:
                pass

        listing_line = (f"{i['name']} - ({i['id']}) [{listing_type}] "
                        f"[Modified: {modified_str}]")

        if is_recent:
            listing_line = f"\033[93m{listing_line}\033[0m"

        logging.info(listing_line)

    return items

def navigate_dir(cwd, cwd_items):
    """
    Interactive navigation among the items in the current path-based listing.
    Returns a dict:
      {"name": <name>, "id": <id>, "list_type": "file"|"folder"}
    Or one of the special navigations: up_level, /, exit
    """
    choices = ['up_level', '/', 'exit']
    choice_objects = {
        'up_level': {"name": "up_level", "id": "", "list_type": None},
        '/':        {"name": "/",        "id": "", "list_type": None},
        'exit':     {"name": "exit",     "id": "", "list_type": None}
    }

    for i in cwd_items['value']:
        if "file" in i:
            list_type = "file"
        else:
            list_type = "folder"
        display_name = f'{i["name"]} - ({i["id"]})'
        choice_objects[display_name] = {
            "name": i["name"],
            "id": i["id"],
            "list_type": list_type
        }
        choices.append(display_name)

    dirlist = [
        {
            'type': 'list',
            'name': 'user_option',
            'message': f'Directory listing of [{cwd if cwd else "<ROOT>"}]',
            'choices': choices
        }
    ]
    answers = ask(dirlist)
    if not answers or "user_option" not in answers:
        logging.info("Directory navigation canceled by user.")
        return None
    nav_key = answers.get("user_option")
    return choice_objects[nav_key]

def main():
    if not args["accesstoken"]:
        drive = replace_token()
    else:
        drive = login(args["accesstoken"])

    if not drive:
        logging.error("Could not establish a OneDrive session. Exiting.")
        sys.exit(1)

    # keep track of the current OneDrive path (string), e.g. "", "Desktop", "Desktop/Subfolder"
    cwd = ""
    cwd_items = {}

    while True:
        top_level_menu = [
            {
                'type': 'list',
                'name': 'user_option',
                'message': 'OneDrive Interactive Client',
                'choices': [
                    "replace_token",
                    "chdir",
                    "list",
                    "download",
                    "download_folder",
                    "upload",
                    "config",
                    "exit"
                ]
            }
        ]
        answers = ask(top_level_menu)
        if not answers or "user_option" not in answers:
            logging.info("Cancelled by user at main menu or no valid selection.")
            continue

        option = answers["user_option"]

        if option == "replace_token":
            logging.info("Replacing access token.")
            new_drive = replace_token()
            if new_drive:
                drive = new_drive
            else:
                logging.error("Replace token failed or canceled.")
            continue

        elif option == "chdir":
            try:
                cwd_items = listdir(cwd, drive)
            except msdrive.exceptions.ItemNotFound:
                logging.error(f"Invalid folder path [{cwd}]. Resetting to root.")
                cwd = ""
                cwd_items = {}
                continue

            nav = navigate_dir(cwd, cwd_items)
            if not nav:
                continue
            if nav["name"] == "exit":
                continue
            elif nav["name"] == "/":
                cwd = ""
                cwd_items = {}
            elif nav["name"] == "up_level":
                # Chop off the last subfolder
                if cwd:
                    cwd = os.path.dirname(cwd.strip('/'))
                    if cwd == '.' or cwd == '/':
                        cwd = ""
                cwd_items = {}
            else:
                if nav["list_type"] == "folder":
                    subfolder = nav["name"].strip('/')
                    if cwd:
                        cwd = f"{cwd}/{subfolder}"
                    else:
                        cwd = subfolder
                    cwd_items = {}
                else:
                    logging.info("You selected a file. No directory change done.")

        elif option == "list":
            try:
                cwd_items = listdir(cwd, drive)
            except msdrive.exceptions.ItemNotFound:
                logging.error(f"Invalid folder path [{cwd}]. Resetting to root.")
                cwd = ""
                cwd_items = {}
                continue

        elif option == "download":
            # Let user pick a file to download
            if not cwd_items:
                try:
                    cwd_items = listdir(cwd, drive)
                except msdrive.exceptions.ItemNotFound:
                    logging.error(f"Invalid folder path [{cwd}]. Resetting to root.")
                    cwd = ""
                    cwd_items = {}
                    continue

            nav = navigate_dir(cwd, cwd_items)
            if not nav:
                continue
            if nav["name"] in ("exit", "/"):
                if nav["name"] == "/":
                    cwd = ""
                    cwd_items = {}
                continue
            elif nav["name"] == "up_level":
                if cwd:
                    cwd = os.path.dirname(cwd.strip('/'))
                    if cwd == '.' or cwd == '/':
                        cwd = ""
                cwd_items = {}
                continue
            else:
                if nav["list_type"] == "folder":
                    # If user wants to download a folder but picks "download" item, we can just warn
                    subfolder = nav["name"].strip('/')
                    if cwd:
                        cwd = f"{cwd}/{subfolder}"
                    else:
                        cwd = subfolder
                    cwd_items = {}
                    logging.info(f"Changed directory into folder: {cwd}")
                    continue
                # If it's a file, download by ID
                download(nav["id"], drive)

        elif option == "download_folder":
            # We do path-based recursion for the current 'cwd'
            # If there's nothing in cwd_items, we list again first
            if not cwd_items:
                try:
                    cwd_items = listdir(cwd, drive)
                except msdrive.exceptions.ItemNotFound:
                    logging.error(f"Invalid folder path [{cwd}]. Resetting to root.")
                    cwd = ""
                    cwd_items = {}
                    continue

            nav = navigate_dir(cwd, cwd_items)
            if not nav:
                continue
            if nav["name"] in ("exit", "/"):
                if nav["name"] == "/":
                    cwd = ""
                    cwd_items = {}
                continue
            elif nav["name"] == "up_level":
                if cwd:
                    cwd = os.path.dirname(cwd.strip('/'))
                    if cwd == '.' or cwd == '/':
                        cwd = ""
                cwd_items = {}
                continue
            else:
                if nav["list_type"] == "folder":
                    subfolder = nav["name"].strip('/')
                    if cwd:
                        folder_path = f"{cwd}/{subfolder}"
                    else:
                        folder_path = subfolder

                    download_entire_folder_by_path(folder_path, drive)
                else:
                    logging.info("You selected a file. 'download_folder' expects a folder. No action taken.")

        elif option == "upload":
            upload(drive)

        elif option == "config":
            logging.info("No config steps implemented yet. Add your code here.")

        elif option == "exit":
            logging.info("Exiting. Have a nice day!")
            sys.exit(0)

if __name__ == "__main__":
    main()