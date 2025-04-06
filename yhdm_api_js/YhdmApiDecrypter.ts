import CryptoJS from 'crypto-js';
import * as HtmlSoup from 'react-native-html-soup';
import { USER_AGENT, YHDM_API_BASE_URL, YHDM_PLAYER_BASE_URL } from './confg';


export default class YhdmApiDecrypter {

  // Helper to fetch HTML content
  private static async fetchHtml(url: string, headers: Record<string, string>): Promise<string> {
    console.log(`Fetching HTML from: ${url} with headers: ${JSON.stringify(headers)}`);
    const response = await fetch(url, { headers, method: "GET" },);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status} for URL: ${url}`);
    }
    const text = await response.text();
    // console.log(`Received HTML (first 500 chars): ${text.substring(0, 500)}`);
    return text;
  }

  // Equivalent to Python's get_play_page
  private static async _getPlayPageHtml(animeId: number, episode: number, streamId: number): Promise<string> {
    const url = `${YHDM_API_BASE_URL}/index.php/vod/play/id/${animeId}/sid/${streamId}/nid/${episode}/`;
    const headers = {
      'User-Agent': USER_AGENT,
      'Referer': url,
    };
    return this.fetchHtml(url, headers);
  }

  // Equivalent to Python's parse_encrypted_video_url
  private static _parseEncryptedVideoUrl(htmlContent: string): { url: string | null; nextUrl: string | null } {
    try {
      const scriptElement = HtmlSoup.selectFirst(htmlContent, ".player_video script");
      if (!scriptElement || !scriptElement.html) {
        console.error("Could not find .player_video script tag or its content.");
        return { url: null, nextUrl: null };
      }
      const code = scriptElement.html;
      // Use 's' flag for DOTALL equivalent if needed, though JS regex '.' usually matches newlines in common scenarios.
      // Ensure the regex correctly captures the groups.
      const match = code.match(/url"\s*:\s*"([^"]*)".*?"url_next"\s*:\s*"([^"]*)"/s);

      if (!match || match.length < 3) {
        console.error("Could not match url and url_next in script tag.");
        return { url: null, nextUrl: null };
      }
      const urlEncoded = match[1];
      const nextUrlEncoded = match[2];

      const url = decodeURIComponent(urlEncoded as string);
      let nextUrl = decodeURIComponent(nextUrlEncoded as string);

      if (!url) {
        console.error("Parsed encrypted URL is empty.");
        return { url: null, nextUrl: null };
      }

      if (!nextUrl) {
        nextUrl = null as any; // Explicitly set to null if empty
      }
      console.log(`Parsed Encrypted URL: ${url}, Next URL: ${nextUrl}`);
      return { url, nextUrl };

    } catch (error) {
      console.error('Error parsing encrypted video URL:', error);
      return { url: null, nextUrl: null };
    }
  }

  // Equivalent to Python's get_player_page
  private static async _getPlayerConfigScript(decodedEncryptedUrl: string): Promise<string> {
    const url = `${YHDM_PLAYER_BASE_URL}/player/ec.php?code=qw&if=1&url=${encodeURIComponent(decodedEncryptedUrl)}`;
    // Referer needs to be constructed exactly as in Python
    const referrer = `${YHDM_PLAYER_BASE_URL}/player/index.php?code=qw&if=1&url=${encodeURIComponent(decodedEncryptedUrl)}`;
    const headers = {
      'User-Agent': USER_AGENT,
      'Referer': referrer,
    };
    // Note: Python requests sends params in URL, fetch needs URLSearchParams or manual construction
    // The URL already includes the param, so no extra body/params needed for GET.
    return this.fetchHtml(url, headers);
  }


  // Updated decryptUrl based on Python's decrypt_url
  static async decryptUrl(decodedEncryptedUrl: string): Promise<string | null> {
    try {
      console.log(`Attempting to decrypt URL: ${decodedEncryptedUrl}`);
      const configScript = await this._getPlayerConfigScript(decodedEncryptedUrl);

      // Extract config_url (Base64 encoded data)
      const urlMatch = configScript.match(/"url"\s*:\s*("([^"]*)")/);

      if (!urlMatch || !urlMatch[1]) {
        console.error('Failed to extract config URL from config script.');
        return null;
      }
      // Use JSON.parse to handle potential string escaping like Python's json.loads
      const configUrlBase64 = JSON.parse(urlMatch[1]);

      // Extract config_uid
      const uidMatch = configScript.match(/"uid"\s*:\s*("([^"]*)")/);
      if (!uidMatch || !uidMatch[1]) {
        console.error('Failed to extract config UID from config script.');
        return null;
      }
      const configUid = JSON.parse(uidMatch[1]);

      console.log(`Extracted config UID: ${configUid}`);

      // Construct key and iv
      const keyStr = `2890${configUid}tB959C`;
      const key = CryptoJS.enc.Utf8.parse(keyStr);
      const iv = CryptoJS.enc.Utf8.parse('2F131BE91247866E');
      console.log(`Using Key: ${keyStr}, IV: 2F131BE91247866E`);

      // Decrypt using AES CBC
      // Input to decrypt is the Base64 decoded data (WordArray)
      const encryptedDataWordArray = CryptoJS.enc.Base64.parse(configUrlBase64);

      const decrypted = CryptoJS.AES.decrypt(
        // @ts-ignore - CryptoJS type definitions might be slightly off for source object
        { ciphertext: encryptedDataWordArray },
        key,
        {
          iv: iv,
          mode: CryptoJS.mode.CBC,
          padding: CryptoJS.pad.Pkcs7, // Corresponds to PKCS5Padding for AES block size
        }
      );

      const decryptedText = decrypted.toString(CryptoJS.enc.Utf8);
      console.log(`Successfully Decrypted URL: ${decryptedText}`);
      return decryptedText;

    } catch (error) {
      console.error('Decryption failed:', error);
      // Log the specific URL that failed if possible
      console.error(`Failed URL was: ${decodedEncryptedUrl}`);
      return null;
    }
  }

  /**
   * 获取视频播放url m3u8格式 (Refactored based on Python logic)
   * @param animeId 动漫id
   * @param episode 分集id (nid)
   * @param streamId 线路id (sid)
   * @returns
   */
  static async getVideoUrl(animeId: number, episode: number, streamId: number): Promise<{ url: string | null; nextUrl: string | null }> {
    try {
      // 1. Get Play Page HTML
      const playPageHtml = await this._getPlayPageHtml(animeId, episode, streamId);

      // 2. Parse Encrypted URLs
      const parsedUrls = this._parseEncryptedVideoUrl(playPageHtml);
      debugger
      if (!parsedUrls || !parsedUrls.url) {
        console.error('Failed to parse encrypted URLs from play page.');
        return { url: null, nextUrl: null };
      }

      // 3. Decrypt Main URL
      const decryptedUrl = await this.decryptUrl(parsedUrls.url);
      if (!decryptedUrl) {
        console.error('Failed to decrypt main video URL.');
        // Even if main fails, try next? Or return fail? Python returns None overall.
        return { url: null, nextUrl: null };
      }

      // 4. Decrypt Next URL (if exists)
      let decryptedNextUrl: string | null = null;
      if (parsedUrls.nextUrl) {
        console.log("Attempting to decrypt next URL...");
        decryptedNextUrl = await this.decryptUrl(parsedUrls.nextUrl);
        // Validate next URL (basic check)
        if (decryptedNextUrl && !decryptedNextUrl.toLowerCase().startsWith('http')) {
          console.warn(`Decrypted next URL does not seem valid: ${decryptedNextUrl}`);
          decryptedNextUrl = null;
        }
        if (!decryptedNextUrl) {
          console.log("Decryption of next URL failed or result was invalid.");
        }
      } else {
        console.log("No next URL found to decrypt.");
      }

      console.log(`Final Result - URL: ${decryptedUrl}, Next URL: ${decryptedNextUrl}`);
      return { url: decryptedUrl, nextUrl: decryptedNextUrl };

    } catch (error) {
      console.error('Error in getVideoUrl process:', error);
      return { url: null, nextUrl: null };
    }
  }
}
