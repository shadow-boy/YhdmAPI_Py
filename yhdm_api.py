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
class Episode:
    id: int  # 分集ID（数字）
    title: str  # 分集标题（显示文本）

@dataclass
class StreamLine:
    id: int  # 播放线路ID
    episodes: List[Episode]  # 该线路的分集列表

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
    stream_lines: List[StreamLine]  # 改用stream_lines替代stream_ids
    last_update: datetime

    def get_stream_ids(self) -> set:
        """获取所有播放线路ID的集合"""
        return {line.id for line in self.stream_lines}

    def get_episodes(self, stream_id: int) -> Optional[List[Episode]]:
        """获取指定播放线路的分集列表"""
        for line in self.stream_lines:
            if line.id == stream_id:
                return line.episodes
        return None

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

    def get_homepage(self):
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
                    
                # 从链接中提取动漫ID
                anime_id = 0
                if link:
                    try:
                        anime_id = int(link.split('/')[-2])
                    except (ValueError, IndexError):
                        pass
                    
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
                    'id': anime_id,
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

    def get_search_suggestions(self, keyword: str, limit: int = 10) -> List[str]:
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
            latest_episode = None
            stream_lines = []
            seen_stream_ids = set()  # 用于跟踪已经添加的线路ID
            
            # 调试信息
            print(f"\n解析动漫 {anime_id} 的播放列表:")
            
            # 获取所有分集列表
            episode_lists = soup.select("ul.content_playlist")
            print(f"找到 {len(episode_lists)} 个分集列表")
            
            for i, episode_list in enumerate(episode_lists):
                print(f"\n处理第 {i+1} 个分集列表:")
                
                # 获取该列表中的所有分集链接
                episode_links = episode_list.select("a")
                if not episode_links:
                    print("未找到分集链接，跳过此列表")
                    continue
                
                # 从第一个分集链接的href中提取线路ID
                first_link = episode_links[0]
                href = first_link.get('href', '')
                match = re.search(r'/sid/(\d+)/', href)
                if not match:
                    print(f"无法从链接中提取线路ID: {href}")
                    continue
                
                stream_id = int(match.group(1))
                
                # 检查是否已经添加过这个线路ID
                if stream_id in seen_stream_ids:
                    print(f"线路ID {stream_id} 已存在，跳过")
                    continue
                
                seen_stream_ids.add(stream_id)
                print(f"从链接提取到线路ID: {stream_id}")
                
                # 生成分集列表
                episodes = []
                episode_id = 1
                for link in episode_links:
                    episode_title = link.text.strip()
                    if episode_title:  # 只要标题不为空就添加
                        episodes.append(Episode(id=episode_id, title=episode_title))
                        episode_id += 1
                
                # 计算实际集数（只计算以"第"开头的链接）
                regular_episodes = [ep for ep in episodes if ep.title.startswith("第")]
                special_episodes = [ep for ep in episodes if not ep.title.startswith("第")]
                
                # 更新最新集数（只考虑常规集数）
                if type != "动漫电影":
                    latest_episode = max(len(regular_episodes), latest_episode or 0)
                
                # 添加播放线路信息
                stream_lines.append(StreamLine(id=stream_id, episodes=episodes))
                print(f"线路 {stream_id} 添加了 {len(episodes)} 个分集 (常规: {len(regular_episodes)}, 特别篇: {len(special_episodes)})")
            
            print(f"最终获取到的播放线路数量: {len(stream_lines)}")
            for line in stream_lines:
                regular_count = len([ep for ep in line.episodes if ep.title.startswith("第")])
                special_count = len([ep for ep in line.episodes if not ep.title.startswith("第")])
                print(f"线路 {line.id}: {len(line.episodes)} 个分集 (常规: {regular_count}, 特别篇: {special_count})")
            
            return Anime(
                id=anime_id,
                name=name,
                image_url=image_url,
                status=status,
                latest_episode=latest_episode or 1 if type == "动漫电影" else latest_episode or 0,
                tags=tags,
                type=type if type else "未知",
                year=year if year else "未知",
                description=description,
                stream_lines=stream_lines,
                last_update=datetime.now()
            )
        except Exception as e:
            print(f"解析动漫详情失败: {e}")
            return None

    def filter_anime(self, 
                    type: int = 1,
                    order_by: str = "time",
                    genre: str = "",
                    year: str = "",
                    letter: str = "",
                    page: int = 1) -> List[AnimeShell]:
        """按条件筛选动漫
        
        Args:
            type (int, optional): 动漫类型. 1=新番连载, 2=完结动漫, 3=动漫电影, 4=剧场OVA. 默认为1.
            order_by (str, optional): 排序方式. time=时间排序, hits=点击排序, score=评分排序. 默认为"time".
            genre (str, optional): 动漫类型标签. 如"热血","战斗","奇幻"等. 默认为空字符串.
            year (str, optional): 年份筛选. 如"2023","2022"等. 默认为空字符串.
            letter (str, optional): 首字母筛选. 如"A","B"等. 默认为空字符串.
            page (int, optional): 页码. 默认为1.
            
        Returns:
            List[AnimeShell]: 返回动漫列表,每个元素包含id,name,image_url和status信息
        """
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
    try:
        print("\n=== 测试开始 ===\n")
        
        # 初始化API
        api = YhdmApi()
        
        # 测试获取首页数据
        print("\n获取首页数据测试:")
        home_data = api.get_homepage()
        print(f"获取到 {len(home_data)} 个动漫")
        for anime in home_data[:3]:  # 只显示前3个
            print(f"\n动漫ID: {anime['id']}")
            print(f"标题: {anime['title']}")
            print(f"状态: {anime['status']}")
            print(f"图片: {anime['image_url']}")
            print(f"描述: {anime['description']}")
        
        # 测试搜索建议
        keyword = "异世界"
        print(f"\n搜索建议测试 (关键词: {keyword}):")
        suggestions = api.get_search_suggestions(keyword)
        print(f"获取到 {len(suggestions)} 个搜索建议")
        for suggestion in suggestions:
            print(f"- {suggestion}")
        
        # 测试搜索动漫
        print(f"\n搜索动漫测试 (关键词: {keyword}):")
        search_results = api.search_anime(keyword)
        print(f"获取到 {len(search_results)} 个搜索结果")
        
        # 获取第一个搜索结果的ID用于详情测试
        test_anime_id = None
        if search_results:
            first_result = search_results[0]
            test_anime_id = first_result.id
            print("\n第一个搜索结果:")
            print(f"动漫ID: {first_result.id}")
            print(f"标题: {first_result.name}")
            print(f"状态: {first_result.status}")
            print(f"图片: {first_result.image_url}")
            print(f"描述: {first_result.status}")
        
        # 测试过滤动漫
        print("\n过滤动漫测试 (2023年):")
        filter_results = api.filter_anime(year="2023")
        print(f"获取到 {len(filter_results)} 个结果")
        for anime in filter_results[:3]:  # 只显示前3个
            print(f"\n动漫ID: {anime.id}")
            print(f"标题: {anime.name}")
            print(f"状态: {anime.status}")
            print(f"图片: {anime.image_url}")
            print(f"描述: {anime.status}")
        
        # 使用搜索结果的第一个动漫ID测试获取详情
        test_anime_id = 22214
        if test_anime_id:
            print(f"\n获取动漫详情测试 (ID: {test_anime_id}):")
            anime_detail = api.get_anime_detail(test_anime_id)
            print(f"动漫名称: {anime_detail.name}")
            print(f"状态: {anime_detail.status}")
            print(f"描述: {anime_detail.description}")
            print(f"集数: {anime_detail.latest_episode}")
            print(f"播放线路数量: {len(anime_detail.stream_lines)}")
            
            # 显示每个播放线路的分集列表
            for line in anime_detail.stream_lines:
                print(f"\n播放线路 {line.id} 的分集列表:")
                for episode in line.episodes[:5]:  # 只显示前5集
                    print(f"  - ID: {episode.id}, 标题: {episode.title}")
                print(f"  ... 共 {len(line.episodes)} 集")
            
            # 测试获取视频URL
            if anime_detail.stream_lines and anime_detail.stream_lines[0].episodes:
                first_line = anime_detail.stream_lines[0]
                first_episode = first_line.episodes[0]
                video_url = get_video_url(anime_detail.id, 1, first_line.id)
                print(f"\n视频URL: {video_url}")
                
                # 测试获取下一集URL
                if len(first_line.episodes) > 1:
                    next_episode = first_line.episodes[1]
                    next_url = get_video_url(anime_detail.id, 1, next_episode.id)
                    print(f"下一集URL: {next_url}")
        
        print("\n=== 测试完成 ===\n")
        
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api()
