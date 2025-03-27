import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import time
import json
from datetime import datetime
import re
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from urllib.parse import unquote

from config import USER_AGENT, YHDM_API_BASE_URL, YHDM_PLAYER_BASE_URL
from get_video_url_common import get_video_url


@dataclass
class Suggest:
    id: int
    name: str
    en: str
    pic: str

@dataclass
class SuggestsResponse:
    code: int
    msg: str
    page: int
    pagecount: int
    limit: int
    total: int
    list: List[Suggest]
    url: str

@dataclass
class AnimeShell:
    id: int
    name: str
    image_url: Optional[str]
    status: str

@dataclass
class Anime:
    id: int
    name: str
    image_url: str
    status: str
    latest_episode: int
    tags: List[str]
    type: str
    year: str
    description: str
    stream_ids: set
    last_update: datetime

class YhdmApi:
    """
    樱花动漫-api
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": YHDM_API_BASE_URL
        })

    def get_home_page(self):
        """获取首页内容"""
        try:
            response = requests.get(YHDM_API_BASE_URL, headers=self.session.headers)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 获取所有动漫条目
            items = soup.find_all('li', class_='vodlist_item')
            
            results = []
            for item in items:
                # 获取标题和链接
                title_link = item.find('a', class_='vodlist_thumb')
                if not title_link:
                    continue
                    
                title = title_link.get('title', '')
                link = title_link.get('href', '')
                if link and not link.startswith('http'):
                    link = YHDM_API_BASE_URL + link
                    
                # 获取图片 URL
                image_url = title_link.get('data-original', '')
                
                # 获取年份和类型
                year_span = item.find('em', class_='voddate_year')
                type_span = item.find('em', class_='voddate_type')
                year = year_span.text if year_span else ''
                type_text = type_span.text if type_span else ''
                
                # 获取状态
                status_span = item.find('span', class_='pic_text')
                status = status_span.text if status_span else ''
                
                # 获取描述
                desc_div = item.find('div', class_='vodlist_titbox')
                desc = ''
                if desc_div:
                    desc_p = desc_div.find('p', class_='vodlist_sub')
                    if desc_p:
                        desc = desc_p.text.strip()
                
                results.append({
                    'title': title,
                    'link': link,
                    'image_url': image_url,
                    'year': year,
                    'type': type_text,
                    'status': status,
                    'description': desc
                })
                
            return results
            
        except Exception as e:
            print(f"获取首页内容失败: {str(e)}")
            return []

    def search_anime(self, keyword: str, tag: str = "", actor: str = "", page: int = 1) -> List[AnimeShell]:
        """搜索动漫"""
        params = {
            "wd": keyword,
            "class": tag,
            "actor": actor,
            "page": page
        }
        headers = {
            "Referer": f"{YHDM_API_BASE_URL}/index.php/vod/search/"
        }
        response = self.session.get(f"{YHDM_API_BASE_URL}/index.php/vod/search/", params=params, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for li in soup.select("li.searchlist_item"):
            a = li.select_one(".searchlist_img > a")
            if a:
                results.append(AnimeShell(
                    id=int(a['href'].split('/')[-2]),
                    name=a['title'],
                    image_url=a.get('data-original'),
                    status=li.find('span', class_='pic_text').text if li.find('span', class_='pic_text') else ''
                ))
        return results

    def get_search_suggests(self, keyword: str, limit: int = 10) -> List[str]:
        """获取搜索建议"""
        params = {
            "mid": 1,
            "wd": keyword,
            "limit": limit,
            "timestamp": int(time.time() * 1000)
        }
        headers = {
            "Referer": f"{YHDM_API_BASE_URL}/index.php/vod/search/"
        }
        response = self.session.get(f"{YHDM_API_BASE_URL}/index.php/ajax/suggest", params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # 直接从返回的数据中提取建议列表
        suggests = []
        if isinstance(data.get('list'), list):
            for item in data['list']:
                if isinstance(item, dict) and 'name' in item:
                    suggests.append(item['name'])
        return suggests

    def get_anime_detail(self, anime_id: int) -> Optional[Anime]:
        """获取动漫详情"""
        response = self.session.get(f"{YHDM_API_BASE_URL}/index.php/vod/detail/id/{anime_id}/")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        try:
            # 获取基本信息
            content_thumb = soup.select_one(".content_thumb > a")
            content_detail = soup.select_one(".content_detail h2")
            if not content_thumb or not content_detail:
                return None
                
            image_url = content_thumb.get('data-original')
            name = content_detail.text.strip()
            
            # 获取详细信息
            data_items = soup.select(".content_detail li.data")
            year = data_items[0].select_one("span:contains('年份')").next_sibling.text.strip()
            tags = [tag.text.strip() for tag in data_items[0].select_one("span:contains('类型')").next_siblings]
            status = data_items[1].select_one("span:contains('状态')").next_sibling.text.strip()
            description = soup.select_one(".content .full_text > span").text.strip()
            type = soup.select_one("ul.top_nav > li.active").text.strip()
            
            # 获取播放列表
            play_list = soup.select("div.playlist_full")
            latest_episode = 0
            stream_ids = set()
            
            for div in play_list:
                a = div.select_one("a")
                if not a:
                    continue
                    
                if type != "动漫电影" and not a.text.startswith("第"):
                    continue
                    
                sid = int(a['href'].split('/')[-2])
                stream_ids.add(sid)
                
                if type == "动漫电影":
                    latest_episode = 1
                else:
                    episode_count = len(div.select("a"))
                    latest_episode = max(episode_count, latest_episode)
            
            return Anime(
                id=anime_id,
                name=name,
                image_url=image_url,
                status=status,
                latest_episode=latest_episode,
                tags=tags,
                type=type if type else "未知",
                year=year if year else "未知",
                description=description,
                stream_ids=stream_ids,
                last_update=datetime.now()
            )
        except Exception as e:
            print(f"解析动漫详情失败: {e}")
            return None

    def filter_anime_by(self, 
                       type: int = 1,
                       order_by: str = "time",
                       genre: str = "",
                       year: str = "",
                       letter: str = "",
                       page: int = 1) -> List[AnimeShell]:
        """按条件筛选动漫"""
        params = {
            "id": type,
            "by": order_by,
            "class": genre,
            "year": year,
            "letter": letter,
            "page": page
        }
        headers = {
            "Referer": f"{YHDM_API_BASE_URL}/index.php/vod/show/id/1/"
        }
        response = self.session.get(f"{YHDM_API_BASE_URL}/index.php/vod/show/", params=params, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for li in soup.select(".vodlist_wi > .vodlist_item"):
            a = li.find('a')
            if a:
                results.append(AnimeShell(
                    id=int(a['href'].split('/')[-2]),
                    name=a['title'],
                    image_url=a.get('data-original'),
                    status=a.find('span', class_='pic_text').text if a.find('span', class_='pic_text') else ''
                ))
        return results


def test_api():
    """测试 API 功能"""
    print("=== 测试开始 ===\n")
    
    try:
        api = YhdmApi()
        
        # 1. 测试获取首页数据
        print("1. 获取首页数据:")
        home_page = api.get_home_page()
        print("首页数据获取成功!")
        for item in home_page[:3]:
            print(f"- {item['title']}")
            print(f"  状态: {item['status']}")
            print(f"  图片: {item['image_url']}")
            print(f"  年份: {item['year']}")
            print(f"  类型: {item['type']}")
            print(f"  描述: {item['description'][:100]}...")
            print()
        
        # 2. 搜索测试
        print("\n2. 搜索测试:")
        try:
            keyword = "异世界"
            print(f"搜索关键词: {keyword}")
            
            # 获取搜索建议
            print("\n获取搜索建议...")
            suggests = api.get_search_suggests(keyword)
            print(f"搜索建议数量: {len(suggests)}")
            print("搜索建议:")
            for suggest in suggests[:5]:
                print(f"- {suggest}")
            
            # 搜索动漫
            print("\n搜索动漫...")
            search_results = api.search_anime(keyword)
            print(f"搜索结果: 共 {len(search_results)} 个结果")
            print("第一页结果:")
            for anime in search_results[:5]:
                print(f"- {anime.name}")
            
        except Exception as e:
            print(f"搜索测试失败: {e}")
            import traceback
            print("错误详情:")
            print(traceback.format_exc())
            exit(1)
        
        # 3. 获取动漫详情
        print("\n3. 获取动漫详情:")
        try:
            if search_results:
                first_anime = search_results[0]
                detail = api.get_anime_detail(first_anime.id)
                if detail:
                    print(f"动漫名称: {detail.name}")
                    print(f"状态: {detail.status}")
                    print(f"描述: {detail.description[:100]}...")  # 只显示前100个字符
                    print(f"集数: {detail.latest_episode}")
                    print(f"播放源数量: {len(detail.stream_ids)}")
                    
                    # 获取第一集和第一个播放源用于后续测试
                    if detail.stream_ids:
                        first_stream_id = list(detail.stream_ids)[0]
                        video_url, next_url = get_video_url(detail.id, 1, first_stream_id)
                        if video_url:
                            print(f"\n视频URL: {video_url}")  # 只显示前100个字符
                            if next_url:
                                print(f"下一集URL: {next_url}")
                else:
                    print("获取动漫详情失败")
        except Exception as e:
            print(f"获取动漫详情失败: {e}")
            exit(1)
        
        # 4. 分类筛选测试
        print("\n4. 分类筛选测试:")
        try:
            filtered = api.filter_anime_by(type=1, year="2023")
            print(f"2023年动漫: 共 {len(filtered)} 个结果")
            print("第一页结果:")
            for anime in filtered[:5]:
                print(f"- {anime.name}")
        except Exception as e:
            print(f"分类筛选测试失败: {e}")
            exit(1)
        
        print("\n=== 测试完成 ===")
    except Exception as e:
        print(f"测试失败: {e}")
        exit(1)

if __name__ == "__main__":
    test_api()
