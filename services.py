import urllib.request
import urllib.parse
import urllib.error
import re
import json
from google import genai

class GeminiClient:
    @staticmethod
    def generate_flashcard(word, api_key, prompt, model_name='gemini-3.1-flash-lite'):
        client = genai.Client(api_key=api_key)
        full_prompt = f"{prompt}\n\nWord to define: {word}"
        
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)

class TTSProvider:
    @staticmethod
    def _fetch_html(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        return urllib.request.urlopen(req, timeout=5).read().decode('utf-8')

    @staticmethod
    def get_audio_url(word, service):
        formatted_word = word.lower().replace(" ", "-")
        quoted_word = urllib.parse.quote(word)
        quoted_formatted = urllib.parse.quote(formatted_word)
        
        try:
            if service.startswith("Google"):
                match = re.search(r'\((.*?)\)', service)
                if match:
                    return f"http://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={quoted_word}&tl={match.group(1)}"
                    
            elif service.startswith("Cambridge"):
                url = f"https://dictionary.cambridge.org/dictionary/english/{quoted_formatted}"
                html = TTSProvider._fetch_html(url)
                pattern = r'(/media/english/uk_pron/[^"\'\s]+\.mp3)' if "UK" in service else r'(/media/english/us_pron/[^"\'\s]+\.mp3)'
                match = re.search(pattern, html)
                
                if match:
                    path = match.group(1)
                    return f"https://dictionary.cambridge.org{path}" if path.startswith('/') else path
                    
            elif service.startswith("Oxford"):
                urls_to_try = [
                    f"https://www.oxfordlearnersdictionaries.com/definition/english/{quoted_formatted}",
                    f"https://www.oxfordlearnersdictionaries.com/definition/english/{quoted_formatted}_1"
                ]
                for url in urls_to_try:
                    try:
                        html = TTSProvider._fetch_html(url)
                        pattern = r'data-src-mp3="([^"]*uk_pron[^"]*\.mp3)"' if "UK" in service else r'data-src-mp3="([^"]*us_pron[^"]*\.mp3)"'
                        match = re.search(pattern, html)
                        if match:
                            return match.group(1)
                    except urllib.error.HTTPError as e:
                        if e.code != 404: raise e
        except Exception as e:
            print(f"TTS Parsing Error ({service}): {e}")
            
        return None

class ImageProvider:
    PROVIDERS = {
        "Google Images": "https://www.google.com/search?tbm=isch&q={}",
        "IStock": "https://www.istockphoto.com/search/2/image?phrase={}",
        "Unsplash": "https://unsplash.com/s/photos/{}",
        "Shutterstock": "https://www.shutterstock.com/search/{}",
        "Pexels": "https://www.pexels.com/search/{}/",
        "GettyImages": "https://www.gettyimages.com/photos/{}",
        "Adobe Stock": "https://stock.adobe.com/search?k={}",
        "Adobe Stock (No AI)": "https://stock.adobe.com/search?k={}&filters%5Bgentech%5D=exclude",
        "Alamy": "https://www.alamy.com/search.html?q={}"
    }

    @staticmethod
    def get_image_url(query, provider):
        if not provider or provider == "None" or provider not in ImageProvider.PROVIDERS:
            return None
        return ImageProvider.PROVIDERS[provider].format(urllib.parse.quote(query))