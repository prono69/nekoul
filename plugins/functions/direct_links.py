import logging
import asyncio
import aiohttp
from hashlib import sha256
from lxml.etree import HTML
import requests
from requests import (
    Session,
    post,
    get,
    RequestException
)
import random
import os
import re
import time
import subprocess
from datetime import datetime
from cloudscraper import create_scraper
from re import findall
from pathlib import PurePath
from typing import Dict, Optional, Tuple

class DirectDownloadLinkException(Exception):
    pass


############################################
# Helper functions for direct download links
############################################

def yandex_disk(url: str) -> str:
    # Placeholder for Yandex Disk bypass logic
    return url

def mediafire(url: str) -> str:
    # Placeholder for Mediafire bypass logic
    return url

def pixeldrain(url: str) -> str:
    url = url.strip("/ ")
    file_id = url.split("/")[-1]
    if url.split("/")[-2] == "l":
        info_link = f"https://pixeldra.in/api/list/{file_id}"
        dl_link = f"https://pixeldra.in/api/list/{file_id}/zip?download"
    else:
        info_link = f"https://pixeldra.in/api/file/{file_id}/info"
        dl_link = f"https://pixeldra.in/api/file/{file_id}?download"
    with create_scraper() as session:
        try:
            resp = session.get(info_link).json()
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}") from e
        if resp.get("success"):
            return dl_link
        else:
            raise Exception(f"ERROR: Can't download due to {resp.get('message')}.")

def qiwi(url: str) -> str:
    # Using requests and lxml to parse the page
    with requests.Session() as session:
        file_id = url.split("/")[-1]
        try:
            res = session.get(url).text
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}") from e
        tree = HTML(res)
        if (name := tree.xpath('//h1[@class="page_TextHeading__VsM7r"]/text()')):
            ext = name[0].split(".")[-1]
            return f"https://spyderrock.com/{file_id}.{ext}"
        else:
            raise Exception("ERROR: File not found")

def gofile(url: str) -> Tuple[str, Dict[str, str]]:
    """
    Generate a direct download link for a GoFile URL and return the URL along with headers.
    """
    try:
        if "::" in url:
            _password = url.split("::")[-1]
            _password = sha256(_password.encode("utf-8")).hexdigest()
            url = url.split("::")[-2]
        else:
            _password = ""
        _id = url.split("/")[-1]
    except Exception as e:
        raise Exception(f"ERROR: {e.__class__.__name__}")

    def __get_token(session: requests.Session) -> str:
        """
        Fetch the account token from GoFile's API.
        """
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        __url = "https://api.gofile.io/accounts"
        try:
            __res = session.post(__url, headers=headers).json()
            if __res["status"] != "ok":
                raise Exception("ERROR: Failed to get token.")
            return __res["data"]["token"]
        except Exception as e:
            raise e

    def __fetch_links(session: requests.Session, _id: str) -> str:
        """
        Fetch the direct download link for the given GoFile ID.
        """
        _url = f"https://api.gofile.io/contents/{_id}?wt=4fd6sg89d7s6&cache=true"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {token}",
        }
        if _password:
            _url += f"&password={_password}"
        try:
            _json = session.get(_url, headers=headers).json()
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}")
        if _json["status"] in "error-passwordRequired":
            raise Exception("ERROR: Password required.")
        if _json["status"] in "error-passwordWrong":
            raise Exception("ERROR: Wrong password!")
        if _json["status"] in "error-notFound":
            raise Exception("ERROR: File not found on GoFile's server.")
        if _json["status"] in "error-notPublic":
            raise Exception("ERROR: This folder is not public.")

        data = _json["data"]
        contents = data.get("children", {})
        if len(contents) == 1:
            for key, value in contents.items():
                return value.get("link")
        raise Exception("ERROR: Multiple files found, cannot determine direct link.")

    with requests.Session() as session:
        try:
            token = __get_token(session)
        except Exception as e:
            raise Exception(f"ERROR: {e.__class__.__name__}")
        try:
            direct_url = __fetch_links(session, _id)
        except Exception as e:
            raise Exception(f"ERROR: {e}")

    # Prepare headers with the Cookie
    headers = {
        "Cookie": f"accountToken={token}",
        "User-Agent": "Mozilla/5.0",
    }

    return direct_url, headers

def streamtape(url: str) -> str:
    splitted_url = url.split("/")
    _id = splitted_url[4] if len(splitted_url) >= 6 else splitted_url[-1]
    try:
        with requests.Session() as session:
            html = HTML(session.get(url).text)
    except Exception as e:
        raise Exception(f"ERROR: {e.__class__.__name__}") from e
    script = html.xpath("//script[contains(text(),'ideoooolink')]/text()") or html.xpath("//script[contains(text(),'ideoolink')]/text()")
    if not script:
        raise Exception("ERROR: requeries script not found")
    if not (links := findall(r"(&expires\S+)'", script[0])):
        raise Exception("ERROR: Download link not found")
    return f"https://streamtape.com/get_video?id={_id}{links[-1]}"
    
    
def terabox(terabox_url, api_keys):
    url = "https://terabox-downloader-direct-download-link-generator2.p.rapidapi.com/url"
    api_key = random.choice(api_keys.split())
    
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "terabox-downloader-direct-download-link-generator2.p.rapidapi.com"
    }
    querystring = {"url": terabox_url}
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()
        return data[0]["link"] if data and isinstance(data, list) else None
    except Exception as e:
        return f"Error: {str(e)}"
        
        
def cf_bypass(url):
    "DO NOT ABUSE THIS"
    try:
        data = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000
        }
        _json = post("https://cf.jmdkh.eu.org/v1", headers={"Content-Type": "application/json"}, json=data).json()
        if _json['status'] == 'ok':
            return _json['solution']["response"]
    except Exception as e:
        e
    raise DirectDownloadLinkException("ERROR: Con't bypass cloudflare")
 
 
def send_cm_file(url, file_id=None):
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ''
    _passwordNeed = False
    with create_scraper() as session:
        if file_id is None:
            try:
                html = HTML(session.get(url).text)
            except Exception as e:
                raise DirectDownloadLinkException(
                    f'ERROR: {e.__class__.__name__}')
            if html.xpath("//input[@name='password']"):
                _passwordNeed = True
            if not (file_id := html.xpath("//input[@name='id']/@value")):
                raise DirectDownloadLinkException('ERROR: file_id not found')
        try:
            data = {'op': 'download2', 'id': file_id}
            if _password and _passwordNeed:
                data["password"] = _password
            _res = session.post('https://send.cm/', data=data, allow_redirects=False)
            if 'Location' in _res.headers:
                return (_res.headers['Location'], 'Referer: https://send.cm/')
        except Exception as e:
            raise DirectDownloadLinkException(f'ERROR: {e.__class__.__name__}')
        if _passwordNeed:
            raise DirectDownloadLinkException(f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}")
        raise DirectDownloadLinkException("ERROR: Direct link not found")
 
def send_cm(url):
    if '/d/' in url:
        return send_cm_file(url)
    elif '/s/' not in url:
        file_id = url.split("/")[-1]
        return send_cm_file(url, file_id)
    
    splitted_url = url.split("/")
    details = {'contents': [], 'title': '', 'total_size': 0,
               'header': {'Referer': 'https://send.cm/'}}  # Header as a dictionary
    
    if len(splitted_url) == 5:
        url += '/'
        splitted_url = url.split("/")
    
    if len(splitted_url) >= 7:
        details['title'] = splitted_url[5]
    else:
        details['title'] = splitted_url[-1]
    
    session = Session()
 
    def __collectFolders(html):
        folders = []
        folders_urls = html.xpath('//h6/a/@href')
        folders_names = html.xpath('//h6/a/text()')
        for folders_url, folders_name in zip(folders_urls, folders_names):
            folders.append({'folder_link': folders_url.strip(), 'folder_name': folders_name.strip()})
        return folders
 
    def __getFile_link(file_id):
        try:
            _res = session.post(
                'https://send.cm/', data={'op': 'download2', 'id': file_id}, allow_redirects=False)
            if 'Location' in _res.headers:
                return _res.headers['Location']
        except:
            pass
 
    def __getFiles(html):
        files = []
        hrefs = html.xpath('//tr[@class="selectable"]//a/@href')
        file_names = html.xpath('//tr[@class="selectable"]//a/text()')
        sizes = html.xpath('//tr[@class="selectable"]//span/text()')
        for href, file_name, size_text in zip(hrefs, file_names, sizes):
            files.append({'file_id': href.split('/')[-1], 'file_name': file_name.strip(), 'size': text_size_to_bytes(size_text.strip())})
        return files
 
    def __writeContents(html_text, folderPath=''):
        folders = __collectFolders(html_text)
        for folder in folders:
            _html = HTML(cf_bypass(folder['folder_link']))
            __writeContents(_html, path.join(folderPath, folder['folder_name']))
        files = __getFiles(html_text)
        for file in files:
            if not (link := __getFile_link(file['file_id'])):
                continue
            item = {'url': link,
                    'filename': file['filename'], 'path': folderPath}
            details['total_size'] += file['size']
            details['contents'].append(item)
    
    try:
        mainHtml = HTML(cf_bypass(url))
    except DirectDownloadLinkException as e:
        session.close()
        raise e
    except Exception as e:
        session.close()
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__} While getting mainHtml")
    
    try:
        __writeContents(mainHtml, details['title'])
    except DirectDownloadLinkException as e:
        session.close()
        raise e
    except Exception as e:
        session.close()
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__} While writing Contents")
    
    session.close()
    
    if len(details['contents']) == 1:
        # Return as a tuple (url, headers dictionary)
        return details['contents'][0]['url'], details['header']
    
    # If there are multiple contents, raise an exception or handle accordingly
    raise DirectDownloadLinkException("Multiple contents found. This function only supports single-file downloads.")
    
    
def streamtape(url):
    splitted_url = url.split("/")
    _id = (
        splitted_url[4]
        if len(splitted_url) >= 6
        else splitted_url[-1]
    )
    try:
        with Session() as session:
            html = HTML(session.get(url).text)
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    script = html.xpath("//script[contains(text(),'ideoooolink')]/text()") or html.xpath("//script[contains(text(),'ideoolink')]/text()")
    if not script:
        raise DirectDownloadLinkException("ERROR: requeries script not found")
    if not (link := findall(r"(&expires\S+)'", script[0])):
        raise DirectDownloadLinkException("ERROR: Download link not found")
    return f"https://streamtape.com/get_video?id={_id}{link[-1]}"
    
    

def streamtape_name(url):
    try:
        with Session() as s:
            page = HTML(s.get(url).content)
            if page_title := page.xpath('//title/text()'):
                cleaned_title = page_title[0].replace(" at Streamtape.com", "").strip()
                return cleaned_title
    except:
        return None    
