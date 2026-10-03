"""
DisplaySamsung 在线更新检测模块
通过 GitHub Releases API 异步检测版本更新与获取更新说明
"""

import logging
import urllib.request
import json
from packaging import version
from config import APP_VERSION

logger = logging.getLogger("DisplaySamsung.Updater")

GITHUB_REPO = "hequanwei/DisplaySamsung"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_updates():
    """
    检查是否有新版本更新
    返回字典结构：
    {
        "success": bool,
        "has_update": bool,
        "current_version": str,
        "latest_version": str,
        "release_notes": str,
        "html_url": str,
        "download_url": str,
        "message": str
    }
    """
    result = {
        "success": False,
        "has_update": False,
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "release_notes": "",
        "html_url": f"https://github.com/{GITHUB_REPO}/releases",
        "download_url": "",
        "message": ""
    }

    try:
        req = urllib.request.Request(
            RELEASES_API_URL,
            headers={
                "User-Agent": "DisplaySamsung-App",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").lstrip("v")
                result["latest_version"] = tag_name or APP_VERSION
                result["release_notes"] = data.get("body", "暂无更新说明")
                result["html_url"] = data.get("html_url", result["html_url"])

                # 寻找 dmg 下载资源
                assets = data.get("assets", [])
                for asset in assets:
                    name = asset.get("name", "")
                    if name.endswith(".dmg"):
                        result["download_url"] = asset.get("browser_download_url", "")
                        break
                if not result["download_url"] and assets:
                    result["download_url"] = assets[0].get("browser_download_url", "")

                result["success"] = True

                # 比较版本号
                try:
                    if version.parse(result["latest_version"]) > version.parse(APP_VERSION):
                        result["has_update"] = True
                        result["message"] = f"发现新版本 v{result['latest_version']}，建议立即更新以获得更佳体验！"
                    else:
                        result["has_update"] = False
                        result["message"] = f"当前已是最新版本 (v{APP_VERSION})，无需更新。"
                except Exception:
                    if result["latest_version"] != APP_VERSION:
                        result["has_update"] = True
                        result["message"] = f"发现新版本 v{result['latest_version']}！"
                    else:
                        result["has_update"] = False
                        result["message"] = f"当前已是最新版本 (v{APP_VERSION})。"
            else:
                result["message"] = f"检查更新服务返回状态码 {response.status}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            result["success"] = True
            result["has_update"] = False
            result["message"] = f"当前版本已是最新 (v{APP_VERSION})，暂无远端发布。"
        else:
            result["message"] = f"GitHub API 请求受限或错误 (HTTP {e.code})"
    except Exception as e:
        logger.warning(f"检查更新异常: {e}")
        result["message"] = f"检查更新超时或网络不可用: {str(e)}"

    return result
