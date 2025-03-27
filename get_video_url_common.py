import requests
import re
import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from bs4 import BeautifulSoup
import urllib.parse

from config import USER_AGENT, YHDM_API_BASE_URL, YHDM_PLAYER_BASE_URL


def get_play_page(anime_id, episode, stream_id):
    """
    模拟调用 getPlayPage 接口，获取播放页内容
    """
    url = f"{YHDM_API_BASE_URL}/index.php/vod/play/id/{anime_id}/sid/{stream_id}/nid/{episode}/"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": YHDM_API_BASE_URL
    }
    response = requests.get(url, headers=headers)
    return response

def get_player_page(encrypted_url, referrer):
    """
    模拟调用 getPlayerPage 接口，获取加密配置信息
    """
    url = f"{YHDM_PLAYER_BASE_URL}/player/ec.php?code=qw&if=1"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referrer
    }
    params = {"url": encrypted_url}
    response = requests.get(url, headers=headers, params=params)
    return response

def parse_encrypted_video_url(html_content):
    """
    从HTML中解析出加密的视频URL和下一集URL
    
    直接翻译自原始Kotlin代码：
    fun parseEncryptedVideoUrl(document: Document): Pair<String, String?>? =
        document.selectFirst(".player_video script")!!.html()
            .let { code ->
                Regex(\"\"\"url"\\s*:\\s*"([^"]*)".*"url_next"\\s*:\\s*"([^"]*)"\"\"\")
                    .find(code)?.groupValues
                    ?.map { URLDecoder.decode(it, "UTF-8") }
                    ?.let { urls ->
                        if (urls[1].isEmpty()) null
                        else urls[1] to (urls[2].takeIf { it.isNotEmpty() })
                    }
            }
    
    Returns:
        成功时返回(url, next_url)元组，其中next_url可能为None
        失败时返回None
    """
    try:
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 查找.player_video下的script标签
        script_tag = soup.select_one(".player_video script")
        if script_tag is None:
            print("无法找到.player_video script标签")
            return None
        
        # 获取script标签的内容
        code = script_tag.string
        if not code:
            print("script标签内容为空")
            return None
        
        # 使用正则表达式查找url和url_next
        match = re.search(r'url"\s*:\s*"([^"]*)".*?"url_next"\s*:\s*"([^"]*)"', code, re.DOTALL)
        if not match:
            print("无法匹配url和url_next")
            return None
        
        # 获取匹配组
        url_encoded = match.group(1)
        next_url_encoded = match.group(2)
        
        # URL解码
        url = urllib.parse.unquote(url_encoded)
        next_url = urllib.parse.unquote(next_url_encoded)
        
        # 检查url是否为空
        if url == "":
            print("解析到的url为空")
            return None
        
        # 如果next_url为空，则设为None
        if next_url == "":
            next_url = None
        
        return (url, next_url)
    except Exception as e:
        print(f"解析加密视频URL时出错: {e}")
        return None

def decrypt_url(encrypted_url):
    """
    解密视频 URL
    """
    try:
        # 构造请求的 Referer
        referrer = f"{YHDM_PLAYER_BASE_URL}/player/index.php?code=qw&if=1&url={encrypted_url}"
        response = get_player_page(encrypted_url, referrer)
        html_text = response.text

        # 提取加密配置信息中的 url 字段
        match_url = re.search(r'"url"\s*:\s*("([^"]*)")', html_text)
        if not match_url:
            return None
        # 利用 json.loads 将双引号包裹的字符串解析为普通字符串
        config_url = json.loads(match_url.group(1))

        # 提取 uid 字段
        match_uid = re.search(r'"uid"\s*:\s*("([^"]*)")', html_text)
        if not match_uid:
            return None
        config_uid = json.loads(match_uid.group(1))

        # 根据原始逻辑构造 key 和 iv
        key_str = f"2890{config_uid}tB959C"
        key = key_str.encode("utf-8")
        iv = "2F131BE91247866E".encode("utf-8")

        # 使用 AES/CBC/PKCS5Padding 解密
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_data = base64.b64decode(config_url)
        decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
        return decrypted_data.decode("utf-8")
    except Exception as e:
        print(f"解密失败: {e}")
        return None

def get_video_url(anime_id = 24103, episode = 1, stream_id = 3):
    """
    根据动漫对象和集数等信息获取视频 URL
    参数:
        anime_id: 动画id
        episode: 集数（nid）
        stream_id: 播放流标识（sid）
    返回:
        成功时返回 (decrypted_url, decrypted_next_url) 元组，
        若解密失败则返回 None
    """
    response = get_play_page(anime_id, episode, stream_id)
    if response.status_code != 200:
        print(f"获取播放页失败，状态码: {response.status_code}")
        return None

    # 解析播放页获取加密 URL（返回一个元组: (url, next_url)）
    encrypted_urls = parse_encrypted_video_url(response.text)
    if not encrypted_urls:
        print("解析加密URL失败")
        return None
    
    url, next_url = encrypted_urls
    print(f"获取到加密URL: {url}")
    if next_url:
        print(f"获取到下一集加密URL: {next_url}")
    else:
        print("没有下一集URL")

    decrypted_url = decrypt_url(url)
    if not decrypted_url:
        print("解密当前URL失败")
        return None
    
    decrypted_next_url = None
    if next_url:
        decrypted_next_url = decrypt_url(next_url)
        if "http" not in decrypted_next_url:
            decrypted_next_url = None
        if not decrypted_next_url:
            print("=========>>>>没有下一集")
    
    return decrypted_url, decrypted_next_url


if __name__ == "__main__":
    
    result = get_video_url(anime_id=16762, episode=1, stream_id=1)
    
    if result:
        decrypted_url, decrypted_next_url = result
        print("解密后的视频 URL:", decrypted_url)
        print("解密后的视频 Next URL:", decrypted_next_url)
    else:
        print("获取或解密视频 URL 失败。")
