import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
from urllib.parse import urlparse, urljoin
from html import unescape
from html.parser import HTMLParser
import re
import json
from google import genai

class GeminiJSONError(ValueError):
    """Gemini returned a response that could not be decoded as a JSON object."""


class GeminiClient:
    @staticmethod
    def _parse_json_object(text):
        if not isinstance(text, str) or not text.strip():
            raise GeminiJSONError("Gemini returned an empty response instead of a JSON object.")

        candidate = text.strip()
        # Be tolerant of code fences in case a model or endpoint ignores JSON mode.
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate, count=1, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*```$", "", candidate, count=1).strip()

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            preview = candidate[:300].replace("\n", "\\n")
            if len(candidate) > 300:
                preview += "..."
            raise GeminiJSONError(
                f"Gemini response is not valid JSON ({exc.msg}, line {exc.lineno}, "
                f"column {exc.colno}). Response starts with: {preview}"
            ) from exc

        if not isinstance(data, dict):
            raise GeminiJSONError(
                f"Gemini returned JSON type {type(data).__name__}; expected a JSON object."
            )
        return data

    @staticmethod
    def generate_flashcard(word, api_key, prompt, model_name='gemini-3.8-flash'):
        client = genai.Client(api_key=api_key)
        full_prompt = (
            f"{prompt}\n\nWord to define: {word}\n\n"
            "Output requirements: return exactly one valid JSON object. Use double quotes "
            "for all property names and string values. Do not include Markdown fences, "
            "comments, or any text before or after the JSON object. Preserve the requested fields."
        )

        # A schema with unrestricted properties preserves user-customizable Anki fields
        # while asking Gemini's constrained decoder to produce syntactically valid JSON.
        chat = client.chats.create(
            model=model_name,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        )
        response = chat.send_message(full_prompt)
        try:
            return GeminiClient._parse_json_object(response.text)
        except GeminiJSONError as first_error:
            # Retry once with the same key: a formatting failure is not an API-key failure.
            repair_prompt = (
                "Your previous reply could not be parsed as a JSON object. Regenerate the "
                "same answer for the original word and instructions. Return only one valid "
                "JSON object with double-quoted keys and valid escaped string values. "
                "Do not use Markdown or add any explanation."
            )
            try:
                repaired = chat.send_message(repair_prompt)
                return GeminiClient._parse_json_object(repaired.text)
            except GeminiJSONError as second_error:
                raise GeminiJSONError(
                    "Gemini still returned invalid JSON after one repair attempt. "
                    f"First response: {first_error}. Repair response: {second_error}"
                ) from second_error


class _CambridgePageParser(HTMLParser):
    """Extract the page title and pronunciation buttons from Cambridge HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.h1_parts = []
        self._capture_title = False
        self._capture_h1 = False
        self.audios = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "title":
            self._capture_title = True
        elif tag.lower() == "h1":
            self._capture_h1 = True

        # Cambridge currently exposes pronunciation clips through data-src-mp3.
        # Read that attribute from each individual audio button instead of taking
        # the first mp3 anywhere on the page (which may be the site's word of day).
        audio_url = attrs.get("data-src-mp3")
        if not audio_url and tag.lower() in {"audio", "source"}:
            audio_url = attrs.get("src")
        if audio_url and re.search(r"/media/english/(?:uk|us)_pron/[^\"'\s<>]+?\.mp3(?:[?#][^\"'\s<>]*)?$", audio_url, re.I):
            self.audios.append({
                "url": unescape(audio_url),
                "title": unescape(attrs.get("title", "")),
            })

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._capture_title = False
        elif tag.lower() == "h1":
            self._capture_h1 = False

    def handle_data(self, data):
        if self._capture_title:
            self.title_parts.append(data)
        if self._capture_h1:
            self.h1_parts.append(data)

    @property
    def title(self):
        return " ".join(self.title_parts).strip()

    @property
    def h1(self):
        return " ".join(self.h1_parts).strip()


class TTSProvider:
    # Reuse cookies between dictionary-page parsing and MP3 download.
    _cookie_jar = http.cookiejar.CookieJar()
    _opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(_cookie_jar)
    )
    # Retain the exact dictionary page that provided each audio URL.
    _audio_referers = {}
    last_download_error = None

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    @staticmethod
    def _headers_for_url(url, audio=False, referer=None):
        """Build headers for the site that actually hosts the requested URL."""
        host = (urlparse(url).hostname or "").lower()
        headers = {
            "User-Agent": TTSProvider.USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }

        if host == "oxfordlearnersdictionaries.com" or host.endswith(
            ".oxfordlearnersdictionaries.com"
        ):
            headers["Referer"] = "https://www.oxfordlearnersdictionaries.com/"
        elif host == "dictionary.cambridge.org" or host.endswith(
            ".dictionary.cambridge.org"
        ):
            headers["Referer"] = "https://dictionary.cambridge.org/"
        elif host == "translate.google.com" or host.endswith(".google.com"):
            headers["Referer"] = "https://translate.google.com/"

        if referer:
            headers["Referer"] = referer

        if audio:
            headers["Accept"] = "audio/mpeg,audio/*;q=0.9,*/*;q=0.8"
            headers["Sec-Fetch-Dest"] = "audio"
            headers["Sec-Fetch-Mode"] = "no-cors"
            headers["Sec-Fetch-Site"] = "same-origin"
            if host.endswith("oxfordlearnersdictionaries.com"):
                headers["Origin"] = "https://www.oxfordlearnersdictionaries.com"
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

        return headers

    @staticmethod
    def _fetch_html(url):
        req = urllib.request.Request(
            url,
            headers=TTSProvider._headers_for_url(url),
        )
        with TTSProvider._opener.open(req, timeout=10) as response:
            # Use the response's declared charset when present, with UTF-8 fallback.
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    @staticmethod
    def _normalize_cambridge_term(value):
        """Normalize a word/phrase so hyphens and spaces compare consistently."""
        value = unescape(str(value or "")).casefold()
        value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
        return " ".join(value.split())

    @staticmethod
    def _cambridge_page_matches_word(title, heading, word):
        """Reject redirects/soft-404s and pages for an unrelated word."""
        expected = TTSProvider._normalize_cambridge_term(word)
        for value in (title, heading):
            value = unescape(str(value or "")).strip()
            if not value:
                continue
            # Titles commonly look like "FROZEN | Pronunciation in English";
            # dedicated pages may instead say "English pronunciation of frozen".
            value = re.split(r"\s*[|–—]\s*", value, maxsplit=1)[0].strip()
            value = re.sub(
                r"^(?:english\s+)?pronunciation\s+of\s+", "", value,
                flags=re.IGNORECASE,
            )
            if TTSProvider._normalize_cambridge_term(value) == expected:
                return True
        return False

    @staticmethod
    def _cambridge_audio_matches_word(audio_title, word):
        """Return True only when a button label identifies the requested term."""
        value = unescape(str(audio_title or "")).strip()
        if not value:
            return False
        value = re.sub(
            r"^(?:play\s+)?(?:the\s+)?(?:english\s+)?pronunciation\s+of\s+",
            "", value, flags=re.IGNORECASE,
        )
        value = re.sub(r"^(?:listen\s+to\s+)?(?:the\s+)?audio\s+for\s+", "", value, flags=re.IGNORECASE)
        return TTSProvider._normalize_cambridge_term(value) == TTSProvider._normalize_cambridge_term(word)

    @staticmethod
    def get_audio_url(word, service):
        normalized_word = " ".join(str(word).strip().lower().split())
        formatted_word = re.sub(r"\s+", "-", normalized_word)
        quoted_word = urllib.parse.quote(str(word))
        quoted_formatted = urllib.parse.quote(formatted_word, safe="")

        try:
            if service.startswith("Google"):
                match = re.search(r"\((.*?)\)", service)
                if match:
                    language = urllib.parse.quote(match.group(1))
                    return (
                        "https://translate.google.com/translate_tts"
                        f"?ie=UTF-8&client=tw-ob&q={quoted_word}&tl={language}"
                    )

            elif service.startswith("Cambridge"):
                region = "uk" if "UK" in service.upper() else "us"
                        # The dedicated pronunciation page is preferable to the full entry:
                # dictionary pages can contain several headwords and site-wide audio
                # (including the Word of the Day, often "frozen").
                page_urls = [
                    f"https://dictionary.cambridge.org/pronunciation/english/{quoted_formatted}",
                    f"https://dictionary.cambridge.org/dictionary/english/{quoted_formatted}",
                ]

                for page_index, page_url in enumerate(page_urls):
                    try:
                        page_html = TTSProvider._fetch_html(page_url)
                    except urllib.error.HTTPError as e:
                        if e.code == 404:
                            continue
                        # A dictionary entry may still be available when the dedicated
                        # pronunciation endpoint is blocked or unavailable.
                        if page_index == 0:
                            print(f"Cambridge pronunciation page unavailable ({e}); trying dictionary entry.")
                            continue
                        raise

                    parser = _CambridgePageParser()
                    parser.feed(page_html)
                    parser.close()
                    page_matches_word = TTSProvider._cambridge_page_matches_word(
                        parser.title, parser.h1, word
                    )

                    region_audios = []
                    for audio in parser.audios:
                        match = re.search(r"/media/english/(uk|us)_pron/", audio["url"], re.I)
                        if not match or match.group(1).lower() != region:
                            continue
                        region_audios.append(audio)

                    # Highest confidence: the audio button explicitly names the
                    # requested word. This prevents selecting unrelated clips even
                    # if Cambridge includes several pronunciations on one page.
                    for audio in region_audios:
                        if TTSProvider._cambridge_audio_matches_word(audio["title"], word):
                            audio_url = urljoin(page_url, audio["url"])
                            TTSProvider._audio_referers[audio_url] = page_url
                            return audio_url

                    # On a verified dedicated pronunciation page, the first audio
                    # button for that region is the primary pronunciation. Accept
                    # only untitled buttons here; never substitute an explicitly
                    # labelled clip for another word.
                    is_pronunciation_page = "/pronunciation/english/" in page_url
                    if is_pronunciation_page and page_matches_word:
                        for audio in region_audios:
                            if not audio["title"].strip():
                                audio_url = urljoin(page_url, audio["url"])
                                TTSProvider._audio_referers[audio_url] = page_url
                                return audio_url

                    # Legacy dictionary pages are only used if both the page and
                    # the individual audio button can be tied to the requested term.
                    # No generic "first matching mp3" fallback, by design.

                print(f"Cambridge has no verified {region.upper()} pronunciation audio for: {word!r}")
                return None

            elif service.startswith("Oxford"):
                base = "https://www.oxfordlearnersdictionaries.com"
                page_urls = [
                    f"{base}/definition/english/{quoted_formatted}",
                    f"{base}/definition/english/{quoted_formatted}_1",
                ]
                pattern = (
                    r'data-src-mp3="([^"\']*uk_pron[^"\']*?\.mp3)"'
                    if "UK" in service
                    else r'data-src-mp3="([^"\']*us_pron[^"\']*?\.mp3)"'
                )
                for page_url in page_urls:
                    try:
                        page_html = TTSProvider._fetch_html(page_url)
                        match = re.search(pattern, page_html)
                        if match:
                            # Oxford may provide an absolute URL, a root-relative path,
                            # or HTML-escaped query parameters.
                            audio_url = urljoin(page_url, unescape(match.group(1)))
                            TTSProvider._audio_referers[audio_url] = page_url
                            return audio_url
                    except urllib.error.HTTPError as e:
                        if e.code != 404:
                            raise
        except Exception as e:
            print(f"TTS Parsing Error ({service}): {e}")

        return None

    @staticmethod
    def download_audio(audio_url, save_path, referer=None):
        """Download audio while reusing dictionary cookies and the source-page Referer.

        `referer` is optional to preserve compatibility with existing callers. When
        omitted, use the exact Oxford/Cambridge page captured by get_audio_url(); if
        this process did not capture it, infer an Oxford word page from its MP3 path.
        """
        TTSProvider.last_download_error = None
        parsed = urlparse(audio_url)
        host = (parsed.hostname or "").lower()
        saved_referer = TTSProvider._audio_referers.get(audio_url)
        referer = referer or saved_referer
        inferred_referer = False

        if not referer and host.endswith("oxfordlearnersdictionaries.com"):
            inferred_referer = True
            parts = [part for part in parsed.path.split("/") if part]
            # Example: media/english/us_pron/b/bed/bed__us_2.mp3 -> /definition/english/bed
            try:
                pron_index = parts.index("us_pron") if "us_pron" in parts else parts.index("uk_pron")
                if len(parts) > pron_index + 2:
                    word_slug = parts[pron_index + 2]
                    referer = f"https://www.oxfordlearnersdictionaries.com/definition/english/{word_slug}"
            except (ValueError, IndexError):
                pass

        # If the method was called with a pasted MP3 URL (rather than after
        # get_audio_url()), visit the inferred dictionary entry first to receive
        # any cookies that the site expects for media requests.
        if inferred_referer and referer:
            try:
                warmup = urllib.request.Request(
                    referer,
                    headers=TTSProvider._headers_for_url(referer),
                )
                with TTSProvider._opener.open(warmup, timeout=10) as page_response:
                    page_response.read(1024)
            except Exception:
                # Still attempt the MP3 request; some entries are inaccessible
                # while their directly-linked media remains available.
                pass

        req = urllib.request.Request(
            audio_url,
            headers=TTSProvider._headers_for_url(audio_url, audio=True, referer=referer),
        )

        try:
            with TTSProvider._opener.open(req, timeout=15) as response:
                data = response.read()
                content_type = (response.headers.get("Content-Type") or "").lower()
                if not data:
                    TTSProvider.last_download_error = f"Empty response from {host}"
                    print(f"Audio download failed: {TTSProvider.last_download_error}")
                    return False
                if "text/html" in content_type:
                    TTSProvider.last_download_error = f"Expected audio, got {content_type} from {host}"
                    print(f"Audio download failed: {TTSProvider.last_download_error}")
                    return False
                with open(save_path, "wb") as out_file:
                    out_file.write(data)
            return True
        except urllib.error.HTTPError as e:
            TTSProvider.last_download_error = (
                f"HTTP {e.code} {e.reason} from {host}; "
                f"Referer={referer or '(not set)'}"
            )
            print(f"Audio download failed: {TTSProvider.last_download_error}")
        except urllib.error.URLError as e:
            TTSProvider.last_download_error = f"Network error: {e.reason}"
            print(f"Audio download failed: {TTSProvider.last_download_error}")
        except Exception as e:
            TTSProvider.last_download_error = f"Unexpected error: {e}"
            print(f"Audio download failed: {TTSProvider.last_download_error}")
        return False

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
