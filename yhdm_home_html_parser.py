import requests
from bs4 import BeautifulSoup
import json
import re


# 参考 FireShot.png的页面结构解析的结构化之后的首页json数据
class YhdmParser:
    def __init__(self):
        self.base_url = "https://www.yhdm6.top"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def get_page_content(self):
        try:
            response = requests.get(self.base_url, headers=self.headers)
            response.encoding = 'utf-8'
            # 保存网页内容到本地文件
            with open('page.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            return response.text
        except Exception as e:
            print(f"Error fetching page: {e}")
            return None

    def _extract_id_from_url(self, url):
        # 从URL中提取ID
        if not url:
            return None
        # 处理相对路径
        if url.startswith('/'):
            url = self.base_url + url
        # 尝试从URL中提取ID
        match = re.search(r'/(\d+)(?:\.html|/?$)', url)
        return match.group(1) if match else None

    def parse_weekly_schedule(self, soup):
        weekly_schedule = []
        # 查找番剧表部分
        schedule_section = None
        for section in soup.find_all('div', class_='pannel'):
            title = section.find('h2', class_='title')
            if title and "番剧表" in title.text.strip():
                schedule_section = section
                break

        if not schedule_section:
            return weekly_schedule

        # 获取所有 ul 标签
        uls = schedule_section.find_all('ul', class_='vodlist')
        if not uls:
            return weekly_schedule

        # 遍历每个 ul 标签
        for ul in uls:
            # 获取所有动漫项
            all_items = ul.find_all('li', class_='vodlist_item')
            
            # 创建一个列表来存储这一天的动漫
            anime_list = []
            
            for item in all_items:
                # 获取动漫信息
                anime = self._parse_anime_item(item)
                if not anime:
                    continue
                
                # 获取更新信息
                update_text = item.find('span', class_='pic_text text_right')
                if update_text:
                    anime['update_info'] = update_text.text.strip()
                    anime_list.append(anime)
            
            # 如果这一天有动漫，添加到 weekly_schedule
            if anime_list:
                weekly_schedule.append({
                    "anime_list": anime_list
                })
        
        return weekly_schedule

    def parse_categories(self, soup):
        categories = []
        category_sections = soup.find_all('div', class_='pannel')
        
        for section in category_sections:
            title = section.find('h2', class_='title')
            if not title:
                continue
                
            category_name = title.text.strip()
            # 跳过番剧表，因为已经单独处理
            if "番剧表" in category_name:
                continue
            # 只处理包含特定关键词的分类
            if not any(keyword in category_name for keyword in ['动漫', '番剧', '排行榜']):
                continue

            # 获取category_id
            category_id = None
            more_link = section.find('a', class_='text_muted pull_left')
            if more_link:
                href = more_link.get('href', '')
                if href:
                    # 从URL中提取分类ID
                    match = re.search(r'/type/id/(\d+)/?', href)
                    if match:
                        category_id = match.group(1)

            # 处理动漫列表
            anime_list = []
            vodlist = section.find('ul', class_='vodlist')
            if vodlist:
                for item in vodlist.find_all('li', class_='vodlist_item'):
                    anime = self._parse_anime_item(item)
                    if anime:
                        anime_list.append(anime)
            
            if anime_list:  # 只有在有动漫列表时才添加
                categories.append({
                    "name": category_name,
                    "category_id": category_id,
                    "anime_list": anime_list
                })
            
        return categories


    def parse_recent_updates(self, soup):
        recent_updates = []
        recent_items = soup.select('.vodlist_item')[:12]
        for item in recent_items:
            anime = self._parse_anime_item(item)
            if anime:
                recent_updates.append(anime)
        return recent_updates

    def parse_rankings(self, soup):
        rankings = []
        rank_sections = soup.find_all('div', class_='list_info')
        
        def clean_title(title):
            # 清理标题中的排名和点击数
            # 移除开头的数字和空格
            title = re.sub(r'^\d+\s+', '', title)
            # 移除剩余的数字和空格
            title = re.sub(r'\d+\s*', '', title)
            # 移除前导和尾随空格
            title = title.strip()
            # 移除多余的空格
            title = re.sub(r'\s+', ' ', title)
            # 移除前导空格
            title = title.lstrip()
            # 移除尾随空格
            title = title.rstrip()
            # 移除所有空格
            title = title.replace(' ', '')
            # 移除特殊字符
            title = re.sub(r'[^\w\u4e00-\u9fff]', '', title)
            # 移除前导空格
            title = title.lstrip()
            return title
        
        def extract_heat(item):
            # 尝试从不同结构中提取热度信息
            heat = 0
            
            # 尝试从 text_muted pull_right 类中提取
            heat_elem = item.find('span', class_='text_muted pull_right')
            if heat_elem:
                heat_text = heat_elem.text.strip()
                # 提取数字
                heat_match = re.search(r'(\d+)', heat_text)
                if heat_match:
                    return int(heat_match.group(1))
            
            # 尝试从 text_muted pull_right renqi 类中提取
            heat_elem = item.find('span', class_='text_muted pull_right renqi')
            if heat_elem:
                heat_text = heat_elem.text.strip()
                # 提取数字
                heat_match = re.search(r'(\d+)', heat_text)
                if heat_match:
                    return int(heat_match.group(1))
            
            return heat
        
        for section in rank_sections:
            # 获取排行榜名称
            title_elem = section.find('h3', class_='title')
            if not title_elem:
                continue
                
            rank_name = title_elem.text.strip()
            rank_items = []
            items = section.find_all('li')
            
            for item in items:
                if 'ranklist_item' in item.get('class', []):
                    # 处理带图片的排行项
                    title_elem = item.find('h4', class_='title')
                    if title_elem:
                        title = title_elem.text.strip()
                        url = item.find('a').get('href', '')
                        info = item.find('p', class_='vodlist_sub')
                        info_text = info.text.strip() if info else ''
                        info_text = info_text.replace(" "," ")
                        
                        # 获取热度信息
                        heat = extract_heat(item)
                        
                        # 获取缩略图
                        thumbnail = ''
                        thumb_elem = item.find('div', class_='ranklist_thumb lazyload')
                        if thumb_elem:
                            thumbnail = thumb_elem.get('data-original', '')
                            if not thumbnail:
                                # 尝试从 style 属性中提取背景图片 URL
                                style = thumb_elem.get('style', '')
                                bg_match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                                if bg_match:
                                    thumbnail = bg_match.group(1)
                        
                        rank_items.append({
                            "rank": len(rank_items) + 1,
                            "title": title,
                            "id": self._extract_id_from_url(url),
                            "info": info_text,
                            "heat": heat,
                            "thumbnail": thumbnail
                        })
                else:
                    # 处理普通排行项
                    link = item.find('a')
                    if link:
                        title = clean_title(link.text.strip())
                        url = link.get('href', '')
                        
                        # 获取热度信息
                        heat = extract_heat(item)
                        
                        rank_items.append({
                            "rank": len(rank_items) + 1,
                            "title": title,
                            "id": self._extract_id_from_url(url),
                            "heat": heat
                        })
            
            if rank_items:
                rankings.append({
                    "name": rank_name,
                    "items": rank_items
                })
        
        return rankings

    def _parse_anime_item(self, item):
        try:
            title_elem = item.find('a', class_='vodlist_thumb')
            if not title_elem:
                return None
                
            title = title_elem.get('title', '').strip()
            url = title_elem.get('href', '')
            
            thumb_url = title_elem.get('data-original', '')
            if not thumb_url:
                thumb_url = title_elem.get('src', '')
            
            info = item.find('p', class_='vodlist_sub')
            info_text = info.text.strip() if info else ''
            info_text = info_text.replace(" "," ")
            
            # 解析年份和类型
            year = ''
            anime_type = ''
            status = ''
            
            # 获取状态信息
            status_elem = item.find('span', class_='pic_text')
            if status_elem:
                status = status_elem.text.strip()
            
            # 从vodlist_top中获取年份和类型
            vodlist_top = item.find('span', class_='vodlist_top')
            if vodlist_top:
                year_elem = vodlist_top.find('em', class_='voddate_year')
                type_elem = vodlist_top.find('em', class_='voddate_type')
                
                if year_elem:
                    year = year_elem.text.strip()
                if type_elem:
                    anime_type = type_elem.text.strip()
            
            return {
                "title": title,
                "id": self._extract_id_from_url(url),
                "thumbnail": thumb_url,
                "year": year,
                "type": anime_type,
                "status": status,
                "info": info_text
            }
        except Exception as e:
            print(f"Error parsing anime item: {e}")
            return None

    def generate_json(self):
        # 首先获取并保存网页内容
        html_content = self.get_page_content()
        if not html_content:
            return None
            
        # 使用保存的HTML文件进行解析
        with open('page.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        data = {
            "weekly_schedule": self.parse_weekly_schedule(soup),
            "categories": self.parse_categories(soup),
            "recent_updates": self.parse_recent_updates(soup),
            "rankings": self.parse_rankings(soup)
        }
        
        return json.dumps(data, ensure_ascii=False, indent=2)

def main():
    parser = YhdmParser()
    json_data = parser.generate_json()
    
    if json_data:
        with open('anime_data.json', 'w', encoding='utf-8') as f:
            f.write(json_data)
        print("Successfully generated anime_data.json")
    else:
        print("Failed to generate JSON data")

if __name__ == "__main__":
    main() 