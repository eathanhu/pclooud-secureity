import os
import requests
import base64
import xml.etree.ElementTree as ET
from config import PCLOUD_EMAIL, PCLOUD_PASSWORD, FOLDER_NAME

WEBDAV_BASE = "https://webdav.pcloud.com"


def _webdav_headers():
    creds = base64.b64encode(
        f"{PCLOUD_EMAIL}:{PCLOUD_PASSWORD}".encode()
    ).decode()
    return {"Authorization": f"Basic {creds}"}


def list_folder(path=""):
    remote_path = f"/{FOLDER_NAME}{path}"
    url = f"{WEBDAV_BASE}{remote_path}"

    if not url.endswith("/"):
        url += "/"

    try:
        r = requests.request(
            "PROPFIND", url,
            headers={**_webdav_headers(), "Depth": "1"},
        )

        if r.status_code not in [200, 207]:
            return {"folders": [], "files": [], "error": f"HTTP {r.status_code}"}

        root = ET.fromstring(r.content)
        ns = {"d": "DAV:"}

        folders = []
        files = []

        for resp in root.findall("d:response", ns):
            href = resp.find("d:href", ns).text

            if href.rstrip("/") == url.rstrip("/"):
                continue

            name = href.rstrip("/").split("/")[-1]

            propstat = resp.find("d:propstat", ns)
            prop = propstat.find("d:prop", ns)

            res_type = prop.find("d:resourcetype", ns)
            is_dir = res_type.find("d:collection", ns) is not None

            if is_dir:
                folders.append({"name": name, "type": "folder"})
            else:
                content_len = prop.find("d:getcontentlength", ns)
                size = int(content_len.text) if content_len is not None and content_len.text else 0
                files.append({"name": name, "type": "file", "size": size})

        return {"folders": folders, "files": files}

    except Exception as e:
        return {"folders": [], "files": [], "error": str(e)}


def get_download_link(file_path):
    remote_path = f"/{FOLDER_NAME}{file_path}"
    safe_path = remote_path.replace(" ", "%20")
    return f"{WEBDAV_BASE}{safe_path}"


def humanbytes(size):
    if not size:
        return "0 B"
    power = 1024
    n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)} {units[n]}"
