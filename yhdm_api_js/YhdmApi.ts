import * as HtmlSoup from 'react-native-html-soup';
import CryptoJS from 'crypto-js'; // 引入 crypto-js 库
import { USER_AGENT, YHDM_API_BASE_URL, YHDM_PLAYER_BASE_URL } from './confg';
import YhdmApiDecrypter from './YhdmApiDecrypter';


// --- 从 yhdm_api.py 转换的类型定义 ---
export interface Suggest {
    id: number;
    name: string;
    en: string;
    pic: string;
}

export interface SuggestsResponse {
    code: number;
    msg: string;
    page: number;
    pagecount: number;
    limit: number;
    total: number;
    list: Suggest[];
    url: string;
}

export interface AnimeShell {
    id: number;
    name: string;
    image_url?: string | null;
    status: string;
}

export interface Episode {
    id: number; // 分集ID（数字）
    title: string; // 分集标题（显示文本）
}

export interface StreamLine {
    id: number; // 播放线路ID
    episodes: Episode[]; // 该线路的分集列表
}

export interface Anime {
    id: number;
    name: string;
    image_url: string;
    status: string;
    latest_episode: number; // 注意：原始 Python 代码中此字段未直接解析，需要确认来源
    tags: string[];
    type: string;
    year: string;
    description: string;
    stream_lines: StreamLine[];
    last_update: string; // 使用字符串表示日期时间
}





// --- YhdmApi 类 (yhdm_api.py 的转换) ---
export default class YhdmApi {
    private baseUrl: string;
    private playerBaseUrl: string;

    constructor() {
        this.baseUrl = YHDM_API_BASE_URL;
        this.playerBaseUrl = YHDM_PLAYER_BASE_URL;
    }

    private async _getSoup(url: string, params?: Record<string, string | number>, referer?: string): Promise<string> {
        const fullUrl = new URL(url, this.baseUrl).toString();
        const urlWithParams = new URL(fullUrl);
        if (params) {
            Object.keys(params).forEach(key => urlWithParams.searchParams.append(key, String(params[key])));
        }

        console.log(`Fetching: ${urlWithParams.toString()}`);
        const response = await fetch(urlWithParams.toString(), {
            headers: {
                'User-Agent': USER_AGENT,
                'Referer': referer || this.baseUrl,
            },
            method: "GET",
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.text();
    }



    async getSearchSuggestions(keyword: string): Promise<Suggest[]> {
        const url = `${this.baseUrl}/index.php/ajax/suggest`;
        const params = { mid: 1, wd: keyword, limit: 10 };
        console.log(`Fetching suggestions: ${url} with params: ${JSON.stringify(params)}`);

        try {
            const response = await fetch(url + '?' + new URLSearchParams(params as any).toString(), {
                headers: {
                    'User-Agent': USER_AGENT,
                    'Referer': this.baseUrl,
                    'X-Requested-With': 'XMLHttpRequest', // YHMD API 可能需要这个头
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data: SuggestsResponse = await response.json();

            if (data.code !== 1) {
                console.warn(`API returned non-success code: ${data.code}, msg: ${data.msg}`);
                return [];
            }
            return data.list || [];
        } catch (error) {
            console.error('Error fetching search suggestions:', error);
            return [];
        }
    }

    async searchAnime(keyword: string, tag: string = "", actor: string = "", page: number = 1): Promise<AnimeShell[]> {
        const url = `${this.baseUrl}/index.php/vod/search/`;
        const params = { wd: keyword, class: tag, actor: actor, page: page };
        console.log(`Fetching search results: ${url} with params: ${JSON.stringify(params)}`);
        let referer = `${this.baseUrl}/index.php/vod/search/`
        let body = params ? new URLSearchParams(params as any).toString() : ""
        try {
            const response = await fetch(url + "?" + body, {
                headers: {
                    'User-Agent': USER_AGENT,
                    'Referer': referer
                },
                referrer: referer, // 确保 referrer 被正确设置
                method: 'GET'
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const html = await response.text();

            const results: AnimeShell[] = [];

            const items = HtmlSoup.select(html, 'li.searchlist_item'); // 确保选择器与 Python 版本一致

            items.forEach(item => {
                const link = HtmlSoup.selectFirst(item.outerHtml, '.searchlist_img > a');
                if (!link) return;

                const title = link.attributes?.title?.trim() || '';
                const href = link.attributes?.href || '';
                const imageUrl = link.attributes?.['data-original'] || '';
                const statusElem = HtmlSoup.selectFirst(item.outerHtml, 'span.pic_text');
                const status = statusElem?.text?.trim() || '';

                const idMatch = href.match(/\/id\/(\d+)\/?/);
                const id = idMatch ? parseInt(idMatch[1] as string) : null;

                if (id && title) {
                    results.push({
                        id,
                        name: title,
                        image_url: imageUrl.startsWith('//') ? 'https:' + imageUrl : imageUrl,
                        status,
                    });
                }
            });

            return results;
        } catch (error) {
            console.error('Error fetching search results:', error);
            return [];
        }
    }

    async getAnimeDetails(animeId: number): Promise<Anime | null> {
        const url = `${this.baseUrl}/index.php/vod/detail/id/${animeId}/`;
        const html = await this._getSoup(url, undefined, this.baseUrl);
        console.log(`Fetching anime details: ${url}`);

        try {
            // 获取基本信息
            const contentThumb = HtmlSoup.selectFirst(html, ".content_thumb > a");
            const contentDetailH2 = HtmlSoup.selectFirst(html, ".content_detail h2");

            if (!contentThumb || !contentDetailH2) {
                console.error(`Failed to find basic info elements for ID ${animeId}`);
                return null;
            }

            let imageUrl = contentThumb.attributes['data-original'] || '';
            if (imageUrl.startsWith('//')) imageUrl = 'https:' + imageUrl;
            const name = contentDetailH2.text.trim();

            // 获取详细信息 - 严格参照 Python 逻辑
            let year = '';
            let tags: string[] = [];
            let status = '';
            let type = '';

            // 选择第一个 li.data (包含年份和类型)
            const firstDataLi = HtmlSoup.selectFirst(html, ".content_detail li.data");

            if (firstDataLi) {
                const firstLiHtml = firstDataLi.outerHtml;
                const firstLiText = firstDataLi.text.trim();

                // 提取年份
                let yearMatch = firstLiText.match(/年份[:：]?\s*(\d{4})/);
                year = yearMatch ? yearMatch[1] as string : '';

                // 提取类型标签 (从第一个 li.data 中)
                const allAnchorsInFirstLi = HtmlSoup.select(firstLiHtml, 'a');
                tags = allAnchorsInFirstLi
                    .filter(a => {
                        const href = a.attributes.href;
                        // 过滤条件：包含 '/vod/show/' 且文本不是纯数字年份
                        return href?.includes('/index.php/vod/search/class')
                    })
                    .map(a => a.text.trim());

                // 模拟 next_sibling: 选择所有 li.data，然后取第二个
                const allDataItems = HtmlSoup.select(html, ".content_detail li.data");
                if (allDataItems.length > 1) {
                    const secondDataLi = allDataItems[1]; // 获取第二个 li.data
                    if (secondDataLi) {
                        // 直接在第二个 li.data 的 HTML 中查找 span.data_style
                        const statusSpan = HtmlSoup.selectFirst(secondDataLi.outerHtml, 'span.data_style');
                        if (statusSpan) {
                            status = statusSpan.text.trim();
                        } else {
                            // 如果 span.data_style 不存在，尝试回退到之前的文本提取逻辑
                            const secondLiText = secondDataLi.text.trim();
                            const statusPrefix = "状态：";
                            const statusIndex = secondLiText.indexOf(statusPrefix);
                            if (statusIndex !== -1) {
                                status = secondLiText.substring(statusIndex + statusPrefix.length).trim();
                                const nextLabelIndex = status.search(/[\u4e00-\u9fa5]+[:：]/);
                                if (nextLabelIndex > 0) {
                                    status = status.substring(0, nextLabelIndex).trim();
                                }
                                status = status.replace(/&nbsp;/g, ' ').trim();
                            } else {
                                console.warn(`Could not find '状态：' prefix in second li.data for ID ${animeId}`);
                            }
                        }
                    } else {
                        console.warn(`Could not access the second 'li.data' element for status for ID ${animeId}`);
                    }
                } else {
                    console.warn(`Could not find the second 'li.data' element for status for ID ${animeId}`);
                }
            } else {
                console.warn(`Could not find the first 'li.data' element for year/tags for ID ${animeId}`);
            }


            const descriptionElem = HtmlSoup.selectFirst(html, ".content .full_text > span");
            const description = descriptionElem?.text?.trim() ?? '';

            const typeElem = HtmlSoup.selectFirst(html, "ul.top_nav > li.active");
            type = typeElem?.text?.trim() ?? '未知';

            // 获取播放列表 (参照 Python 逻辑) - 这部分逻辑保持不变
            let latestEpisode = 0;
            const streamLines: StreamLine[] = [];
            const seenStreamIds = new Set<number>();

            const episodeLists = HtmlSoup.select(html, "ul.content_playlist");

            episodeLists.forEach((episodeList) => {
                const episodeLinks = HtmlSoup.select(episodeList.outerHtml, "a");
                if (episodeLinks.length === 0) return;
                // @ts-ignore
                const firstLinkHref = episodeLinks[0].attributes.href;
                if (!firstLinkHref) return;

                const streamIdMatch = firstLinkHref.match(/\/sid\/(\d+)\//);
                if (!streamIdMatch?.[1]) return;

                const streamId = parseInt(streamIdMatch[1], 10);
                if (isNaN(streamId) || seenStreamIds.has(streamId)) return;

                seenStreamIds.add(streamId);

                const episodes: Episode[] = [];
                let regularEpisodeCount = 0;
                episodeLinks.forEach((link, index) => {
                    const title = link.text?.trim();
                    if (title) {
                        episodes.push({ id: index + 1, title });
                        if (title.startsWith("第")) {
                            regularEpisodeCount++;
                        }
                    }
                });

                if (episodes.length > 0) {
                    streamLines.push({ id: streamId, episodes });
                    if (type !== "动漫电影") {
                        latestEpisode = Math.max(latestEpisode, regularEpisodeCount);
                    }
                }
            });
            // @ts-ignore
            if (type === "动漫电影" && streamLines.length > 0 && streamLines[0]?.episodes?.length > 0) {
                latestEpisode = 1;
            }

            return {
                id: animeId,
                name,
                image_url: imageUrl,
                status,
                latest_episode: latestEpisode,
                tags,
                type,
                year,
                description,
                stream_lines: streamLines,
                last_update: new Date().toISOString(),
            };

        } catch (error) {
            console.error(`Error parsing anime details for ID ${animeId}:`, error);
            return null;
        }
    }

    async filterAnime(
        type: number = 1, // 类型ID，例如 1=日漫, 2=国漫
        orderBy: string = "time", //排序 time, score, hits
        genre: string = "", // 类型，如 热血, 冒险 (对应 class)
        year: string = "", // 年份，如 2023
        letter: string = "", // 首字母
        page: number = 1
    ): Promise<AnimeShell[]> {
        // 构建分类页面的 URL，将参数放入路径中
        // 基础路径: /index.php/vod/show/id/{type}
        let urlPath = `/index.php/vod/show/id/${type}`;

        // 添加筛选参数到路径，注意顺序可能重要，参照网站实际结构
        // 假设顺序是: class -> year -> letter -> order -> page
        // 注意：网站实际使用的参数名可能是 area, lang 等，这里根据 Python 注释使用 class
        if (genre) {
            urlPath += `/class/${encodeURIComponent(genre)}`;
        }
        if (year) {
            urlPath += `/year/${encodeURIComponent(year)}`;
        }
        if (letter) {
            urlPath += `/letter/${encodeURIComponent(letter)}`;
        }
        if (orderBy) { // orderBy 通常是必须的或有默认值
            urlPath += `/order/${encodeURIComponent(orderBy)}`;
        }
        // 最后添加分页
        urlPath += `/page/${page}.html`;

        const fullUrl = `${this.baseUrl}${urlPath}`;
        // Referer 通常是基础分类页
        const referer = `${this.baseUrl}/index.php/vod/show/id/${type}/`;

        console.log(`Fetching filter results from URL: ${fullUrl}`);
        // 使用 _getSoup，它不附加任何查询参数
        const html = await this._getSoup(fullUrl, undefined, referer);
        const results: AnimeShell[] = [];

        try {
            const items = HtmlSoup.select(html, '.vodlist_wi > .vodlist_item'); // 选择器基于 Python 代码
            items.forEach(item => {
                const itemHtml = item.outerHtml;
                const link = HtmlSoup.selectFirst(itemHtml, 'a.vodlist_thumb'); // 使用 .vodlist_thumb 获取链接和标题
                if (link) {
                    const href = link.attributes.href;
                    const title = link.attributes.title?.trim();
                    // 确保从相对路径或绝对路径正确拼接 image URL
                    let imageUrl = link.attributes['data-original'] || link.attributes.src;
                    if (imageUrl && imageUrl.startsWith('//')) {
                        imageUrl = 'https:' + imageUrl;
                    } else if (imageUrl && !imageUrl.startsWith('http')) {
                        // Handle relative URLs if necessary, assuming they are relative to baseUrl
                        // imageUrl = new URL(imageUrl, this.baseUrl).toString();
                        // Or simply prepend baseUrl if that's the case
                        // imageUrl = this.baseUrl + imageUrl;
                        // For now, assume absolute or protocol-relative URLs are provided
                    }

                    const statusElem = HtmlSoup.getText(itemHtml, 'span.pic_text'); // 获取状态文本
                    const status = statusElem ? statusElem.trim() : '';

                    // ID 提取逻辑可能需要根据 href 格式调整，之前是 /id/xxx/，现在可能是 /xxx.html
                    const idMatch = href?.match(/\/(\d+)\.html/); // 假设 ID 在 .html 前
                    const id = idMatch ? parseInt(idMatch[1] as any, 10) : this.extractIdFromUrl(href as string); // Fallback to previous method if needed


                    if (id && title) {
                        results.push({
                            id: id,
                            name: title,
                            image_url: imageUrl || null, // Ensure null if empty
                            status: status,
                        });
                    } else {
                        console.warn("Could not parse item:", { href, title, id });
                    }
                }
            });
        } catch (error) {
            console.error("Error parsing filter results:", error);
        }
        return results;
    }

    // --- 首页解析方法 (来自 App.tsx 的 YhdmParser) ---
    private extractIdFromUrl(url: string | null): number | null {
        if (!url) return null;
        if (url.startsWith('/')) {
            url = this.baseUrl + url;
        }
        const match = url.match(/\/(\d+)(?:\.html|\/?)$/);
        // @ts-ignore
        return match ? parseInt(match[1], 10) : null;
    }

    private parseAnimeItem(html: string): AnimeShell | null {
        try {
            const titleElem = HtmlSoup.selectFirst(html, 'a.vodlist_thumb');
            if (!titleElem) return null;

            const title = titleElem.attributes.title?.trim() || '';
            const url = titleElem.attributes.href || '';
            let thumbUrl = titleElem.attributes['data-original'] || '';
            if (!thumbUrl) {
                thumbUrl = titleElem.attributes.src || '';
            }
            if (thumbUrl.startsWith('//')) {
                thumbUrl = 'https:' + thumbUrl;
            }

            const statusElem = HtmlSoup.getText(html, 'span.pic_text');
            const status = statusElem ? statusElem.trim() : '';

            const id = this.extractIdFromUrl(url);

            if (id === null) return null;

            return {
                id,
                name: title,
                image_url: thumbUrl,
                status,
            };
        } catch (error) {
            console.error('Error parsing anime item:', error);
            return null;
        }
    }

    async getHomepage(): Promise<{ recentUpdates: AnimeShell[] }> {
        const html = await this._getSoup(this.baseUrl);
        const recentUpdates: AnimeShell[] = [];

        try {
            // 获取最近更新的项目 (选择器可能需要根据实际HTML调整)
            const recentItems = HtmlSoup.select(html, '.vodlist.vodlist_wi li.vodlist_item');

            recentItems.forEach((item) => {
                const anime = this.parseAnimeItem(item.outerHtml);
                if (anime) {
                    recentUpdates.push(anime);
                }
            });
        } catch (error) {
            console.error('Error parsing recent updates:', error);
        }

        // 可以添加其他首页部分的解析逻辑，如 parseWeeklySchedule, parseCategories, parseRankings
        return { recentUpdates };
    }




}