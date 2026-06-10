"""
Acts as the "main" file and ties all the other functionality together.
"""

import io, os, praw, psycopg2, time, urllib.request, urllib.parse, urllib.error, prawcore, logging, json
import requests, cv2, traceback, re, sys
import config
from html import unescape
from PIL import Image
from PIL import ImageSequence
from PIL import ImageStat
from imgurpython import ImgurClient
from bs4 import BeautifulSoup
from redgifs import API
from redgifs.errors import RedGifsError
from prawcore.exceptions import TooManyRequests

USERNAME = config.USERNAME
PASSWORD = config.PASSWORD
USERAGENT = config.USERAGENT
REDDITAPPID = config.REDDITAPPID
REDDITAPPSECRET = config.REDDITAPPSECRET

IMGUR_CLIENTID = config.IMGUR_CLIENTID
IMGUR_CLIENTSECRET = config.IMGUR_CLIENTSECRET

API_URL_REDGIFS = "https://api.redgifs.com/v2/gifs/"
MEDIA_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_5_8) AppleWebKit/534.50.2 (KHTML, like Gecko) Version/5.0.6 Safari/533.22.3"
MEDIA_REQUEST_TIMEOUT = 45
VIDEO_REQUEST_TIMEOUT = 180
REDGIFS_VIDEO_URL_FIELDS = ("sd", "hd")
IGNORED_MEDIA_HASH = "9925021303884596990"
IGNORED_MEDIA_HASHES = {
    IGNORED_MEDIA_HASH,  # Imgur generic deleted media image.
    "18446744073709551615",  # Uniform/flat frame from black/white/fade media.
}
LOW_INFORMATION_SAMPLE_SIZE = (16, 16)
LOW_INFORMATION_RANGE_THRESHOLD = 4
LOW_INFORMATION_STDDEV_THRESHOLD = 2.0
IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".jpg_large",
    ".svg",
    ".avif",
    ".bmp",
    ".tif",
    ".tiff",
)
GIF_EXTENSION = ".gif"
GIFV_EXTENSION = ".gifv"
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".m4v")
TRAILING_URL_CHARS = ".,;:!?)>]}'\""
GENERIC_PAGE_REQUEST_TIMEOUT = (10, 30)
MAX_SELFPOST_URLS = 10
GENERIC_VIDEO_META_KEYS = (
    "og:video:secure_url",
    "og:video:url",
    "og:video",
    "twitter:player:stream",
)
GENERIC_IMAGE_META_KEYS = (
    "og:image:secure_url",
    "og:image:url",
    "og:image",
    "twitter:image",
    "twitter:image:src",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(BASE_DIR, "archive.log")
logging.basicConfig(
    filename=log_path,
    encoding="utf-8",
    level=logging.INFO,
    filemode="w",  # 'a' to append, 'w' to overwrite each time
    format="%(asctime)s %(message)s",
    datefmt="%y-%m-%d %H:%M",
)
logger = logging.getLogger("archive")
redgifs_api = None

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(BASE_DIR)

# Import after logging setup so database connection failures land in archive.log.
import databasehandler

SUBREDDITLIST = databasehandler.getArchieveSubredditsList()

reddit = praw.Reddit(
    client_id=REDDITAPPID,
    client_secret=REDDITAPPSECRET,
    password=PASSWORD,
    user_agent=USERAGENT,
    username=USERNAME,
)


class SubmissionUrlOverride:
    def __init__(self, submission, url, attrs=None):
        self._submission = submission
        self.url = url
        self._attrs = attrs or {}

    def __getattr__(self, name):
        if name in self._attrs:
            return self._attrs[name]
        return getattr(self._submission, name)


def convertDateFormat(timestamp):
    return str(time.strftime("%B %d, %Y - %H:%M:%S", time.localtime(timestamp)))


def get_redirect_url(url):
    r = requests.get(url, timeout=(10, 30))
    r.raise_for_status()
    return r.url


def clean_media_url(url):
    if not url:
        return ""
    return unescape(str(url)).replace("&amp;", "&").strip().rstrip(TRAILING_URL_CHARS)


def url_path(url):
    return urllib.parse.urlparse(clean_media_url(url)).path.lower()


def is_image_url(url):
    return url_path(url).endswith(IMAGE_EXTENSIONS)


def is_gif_url(url):
    return url_path(url).endswith(GIF_EXTENSION)


def is_video_url(url):
    return url_path(url).endswith(VIDEO_EXTENSIONS)


def add_unique_url(urls, url, base_url=None):
    url = clean_media_url(url)
    if not url:
        return
    if base_url:
        url = urllib.parse.urljoin(base_url, url)
    if url not in urls:
        urls.append(url)


def clean_redgifs_id(redgifs_id):
    if not redgifs_id:
        return
    redgifs_id = re.sub(r"\W+", "", str(redgifs_id))
    redgifs_id = re.sub(r"https?$", "", redgifs_id, flags=re.IGNORECASE)
    return redgifs_id or None


def get_reddit_video_urls(submission):
    urls = []

    media = getattr(submission, "media", None)
    if isinstance(media, dict):
        nested_media = media.get("secure_media") or {}
        reddit_video = media.get("reddit_video") or nested_media.get("reddit_video")
        if reddit_video:
            add_unique_url(urls, reddit_video.get("fallback_url"))

    secure_media = getattr(submission, "secure_media", None)
    if isinstance(secure_media, dict):
        reddit_video = secure_media.get("reddit_video")
        if reddit_video:
            add_unique_url(urls, reddit_video.get("fallback_url"))

    preview = getattr(submission, "preview", None)
    if isinstance(preview, dict):
        reddit_video_preview = preview.get("reddit_video_preview") or {}
        add_unique_url(urls, reddit_video_preview.get("fallback_url"))

    url = clean_media_url(getattr(submission, "url", None))
    if "v.redd.it" in url:
        if is_video_url(url):
            add_unique_url(urls, url)
        else:
            base_url = url.split("?", 1)[0].rstrip("/")
            for video_name in (
                "DASH_1080.mp4",
                "DASH_720.mp4",
                "DASH_480.mp4",
                "DASH_360.mp4",
            ):
                add_unique_url(urls, f"{base_url}/{video_name}")

    return urls


def get_reddit_video_url(submission):
    urls = get_reddit_video_urls(submission)
    if urls:
        return urls[0]
    return clean_media_url(submission.url) + "/DASH_360.mp4"


def DifferenceHash(theImage):
    """Hashing function"""
    theImage = theImage.convert("L")
    # theImage = theImage.resize((8,8), Image.ANTIALIAS)
    theImage = theImage.resize((8, 8), Image.Resampling.LANCZOS)
    previousPixel = theImage.getpixel((0, 7))
    differenceHash = 0

    for row in range(0, 8, 2):

        for col in range(8):
            differenceHash <<= 1
            pixel = theImage.getpixel((col, row))
            differenceHash |= 1 * (pixel >= previousPixel)
            previousPixel = pixel

        row += 1

        for col in range(7, -1, -1):
            differenceHash <<= 1
            pixel = theImage.getpixel((col, row))
            differenceHash |= 1 * (pixel >= previousPixel)
            previousPixel = pixel

    return differenceHash


def is_low_information_image(theImage):
    sample = theImage.convert("L").resize(
        LOW_INFORMATION_SAMPLE_SIZE, Image.Resampling.BILINEAR
    )
    min_pixel, max_pixel = sample.getextrema()
    if max_pixel - min_pixel <= LOW_INFORMATION_RANGE_THRESHOLD:
        return True

    stat = ImageStat.Stat(sample)
    return stat.stddev[0] <= LOW_INFORMATION_STDDEV_THRESHOLD


def _media_request(url):
    return urllib.request.Request(url, headers={"User-Agent": MEDIA_USER_AGENT})


def _image_to_media_data(img, submission, size):
    img.load()
    width, height = img.size
    pixels = width * height
    if is_low_information_image(img):
        return None

    imgHash = DifferenceHash(img)
    if str(imgHash) in IGNORED_MEDIA_HASHES:
        return None

    return (
        imgHash,
        str(submission.id),
        str(submission.subreddit.display_name),
        1,
        1,
        width,
        height,
        pixels,
        size,
    )


def _download_url_to_file(url, file_path, timeout=VIDEO_REQUEST_TIMEOUT):
    start_time = time.time()
    req = _media_request(url)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        with open(file_path, "wb") as f:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    elapsed = time.time() - start_time
    size = os.path.getsize(file_path)
    logger.info(f"\t [Download] Saved {size} bytes in {elapsed:.2f}s")


def _extract_video_media_data(video_path, submission):
    hash_seen = set()
    mediaData = []
    cap = cv2.VideoCapture(video_path)
    fps = round(cap.get(cv2.CAP_PROP_FPS))
    hop = max(round(fps / 1), 1)
    curr_frame = 0
    frame_count = 0

    try:
        while 1:
            ret, frame = cap.read()
            if not ret:
                break
            if curr_frame % hop == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                im = Image.fromarray(frame_rgb)
                media = getMediaData(None, submission, im)
                frame_count += 1
                if media is not None and media[0] not in hash_seen:
                    hash_seen.add(media[0])
                    mediaData.append(media)
            curr_frame += 1
    finally:
        cap.release()

    logger.info(f"\t [Video] Extracted {frame_count} frames")
    return mediaData


def getMediaData(url, submission, image):
    try:
        start_time = time.time()

        if url is not None:
            req = _media_request(url)
            with urllib.request.urlopen(req, timeout=MEDIA_REQUEST_TIMEOUT) as response:
                mediaContent = response.read()
            size = len(mediaContent)
            img = Image.open(io.BytesIO(mediaContent))
        elif image is not None:
            img = image.copy()
            size = 0
        else:
            return

        mediaData = _image_to_media_data(img, submission, size)
        if mediaData is None:
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Media] Skipped low-information/ignored image in {elapsed:.2f}s (Size: {size} bytes)"
            )
            return

        width = mediaData[5]
        height = mediaData[6]

        elapsed = time.time() - start_time
        logger.info(
            f"\t [Media] Processed image in {elapsed:.2f}s (Size: {size} bytes, Dims: {width}x{height})"
        )
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t Error in getMediaData \t Error= {0}".format(e))
        return


def getMediaDataFromURL(url, submission, media_type=None):
    url = clean_media_url(url)
    if not url:
        return []

    if media_type == "video" or is_video_url(url):
        mediaData = getVideoMediaData(url, submission)
        return mediaData or []

    if media_type == "gif" or is_gif_url(url):
        mediaData = getGifMediaData(url, submission)
        return mediaData or []

    media = getMediaData(url, submission, None)
    return [media] if media is not None else []


def getSubmissionData(mediaprocessed, submission):
    try:
        submissionDeleted = submission.author is None
        author = "[deleted]" if submissionDeleted else str(submission.author)

        # Prepare Submission Object
        submissionData = (
            str(submission.id),
            submission.subreddit.display_name,
            float(submission.created),
            author,
            str(submission.title),
            str(submission.url),
            int(submission.num_comments),
            int(submission.score),
            submissionDeleted,
            mediaprocessed,
        )
        return submissionData
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t Error in getSubmissionData \t Error= {0}".format(e))
        return


def add_DB_Record(submission, mediaData):
    start_time = time.time()
    mediaRows = []
    if mediaData is not None:
        # Ignore known generic and low-information media hashes.
        for media in mediaData:
            if media is not None and str(media[0]) not in IGNORED_MEDIA_HASHES:
                mediaRows.append(media)

    submissionData = getSubmissionData(len(mediaRows) > 0, submission)
    mediaprocessed = databasehandler.addSubmissionAndMedia(submissionData, mediaRows)
    elapsed = time.time() - start_time
    logger.info(
        f"\t [DB] Records added in {elapsed:.2f}s (Media rows: {len(mediaRows)}, Processed: {mediaprocessed})"
    )


def getVideoMediaData(video_url, submission):
    """video_url should end with .mp4"""
    try:
        start_time = time.time()
        logger.info(f"\t [Video] Starting video download from: {video_url[:60]}...")
        # Delete leftover media_file if any
        try:
            os.remove("archive_media_file.mp4")
        except:
            pass

        # Download the video
        _download_url_to_file(video_url, "archive_media_file.mp4")

        # Start Video processing
        # Index 1 second of Video (1FPS)
        download_time = time.time() - start_time
        logger.info(
            f"\t [Video] Downloaded in {download_time:.2f}s, processing frames..."
        )
        mediaData = _extract_video_media_data("archive_media_file.mp4", submission)

        # Delete media_file
        try:
            os.remove("archive_media_file.mp4")
        except:
            pass

        total_time = time.time() - start_time
        logger.info(
            f"\t [Video] Completed in {total_time:.2f}s (Unique hashes: {len(mediaData)})"
        )
        return mediaData
    except urllib.error.HTTPError as e:
        logger.warning(
            "\t [Video] Download failed with HTTP {0} in getVideoMediaData for {1}".format(
                e.code, video_url[:120]
            )
        )
        return
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning(
            "\t [Video] Download failed in getVideoMediaData for {0}: {1}".format(
                video_url[:120], e
            )
        )
        return
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in getVideoMediaData \t Error= {0}".format(e))
        return


def get_gfycat_embedded_video_url(url):
    try:
        # Cycle through all links
        giant_url_found = False
        giant_url = ""
        thumbs_url_found = False
        thumbs_url = ""

        response = requests.get(url, timeout=(10, 30))
        response.raise_for_status()
        data = response.text
        soup = BeautifulSoup(data, features="html.parser")

        for link in soup.find_all():
            link_src = link.get("src")
            src_url = str(link_src)
            if ".mp4" in src_url:
                # Looking for giant.gfycat.com
                if "giant." in src_url:
                    giant_url_found = True
                    giant_url = src_url
                elif "thumbs." in src_url:
                    thumbs_url_found = True
                    thumbs_url = src_url
    except Exception as e:
        traceback.print_exc()
        logger.warning(
            "\t  Error in get_gfycat_embedded_video_url \t Error= {0}".format(e)
        )
        return

    if giant_url_found:
        return giant_url
    elif thumbs_url_found:
        return thumbs_url
    else:
        return


def get_redgifs_id(redgifs_url):
    parsed_url = urllib.parse.urlparse(redgifs_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    for prefix in ("watch", "ifr"):
        if prefix in path_parts:
            index = path_parts.index(prefix)
            if len(path_parts) > index + 1:
                return clean_redgifs_id(path_parts[index + 1])

    if path_parts:
        return clean_redgifs_id(path_parts[-1])

    return


"""
def get_redgifs_embedded_video_url(url):
    try:
        redirect_url = get_redirect_url(url)
        response     = requests.get(redirect_url)
        html         = BeautifulSoup(response.content, features="html.parser")
        links        = str(html.find_all())

        #Get the direct video_url
        video_url    = re.search('meta content="https://thumbs2.redgifs.com/?.*?\\.mp4', links).group()[14:]
        if video_url is not None:
            return video_url
        else:
            video_url = re.search('meta content="https://thumbs2.redgifs.com/?.*?\\.webm', links).group()[14:]
            if video_url is not None:
                video_url = str(video_url.replace(".webm",".mp4"))
                return video_url
            else:
                return
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e))
        return
"""

"""
def get_redgifs_embedded_video_url(redgifs_url, submission):
    try:
        #Get RedGifs video ID
        redgifs_ID = redgifs_url.split('/watch/', 1)
        redgifs_ID = redgifs_ID[1]

        hash            = []
        mediaData       = []
        mediaDataTemp   = []

        #Delete leftover media_file if any
        try:
            os.remove('archive_media_file.mp4')
        except:
            pass

        #Start a session
        session = requests.Session()

        #Get RedGifs Video Meta
        request = session.get(API_URL_REDGIFS + redgifs_ID)

        if request is not None:
            #Get the video url
            rawData = request.json()
            hd_video_url = rawData['gif']['urls']['hd']
            hd_video_url = str(hd_video_url.replace(".webm",".mp4"))

            #Download the video
            with session.get(hd_video_url, stream=True) as r:
                with open("archive_media_file.mp4", 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # If you have chunk encoded response uncomment if and set chunk_size parameter to None.
                        #if chunk:
                        f.write(chunk)

            #Start Video processing
            #Index 1 second of Video (1FPS)
            KPS         = 1 #Target KeyFrames Per Second
            cap         = cv2.VideoCapture("archive_media_file.mp4")
            fps         = round(cap.get(cv2.CAP_PROP_FPS))
            hop         = round(fps / KPS)
            curr_frame  = 0

            try:
                while 1:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if curr_frame % hop == 0:
                        #Save Video Frame
                        cv2.imwrite("archive_media_file.png", frame)
                        im = Image.open("archive_media_file.png")

                        #Prepare MediaData for frames (1 frame per second)
                        mediaDataTemp.append(getMediaData(None, submission, im))
                    curr_frame += 1
            except Exception as e:
                traceback.print_exc()
                return
            cap.release()

            #Remove duplicate media entries for different key frames
            for media in mediaDataTemp:
                if media[0] not in hash:
                    hash.append(media[0])
                    mediaData.append(media)

            #Delete media_file
            try:
                os.remove('archive_media_file.mp4')
            except:
                pass

            return mediaData
        else:
            return
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e))
        return
"""


def get_redgifs_embedded_video_url(redgifs_url, submission):
    global redgifs_api
    try:
        # Get RedGifs video ID
        redgifs_ID = get_redgifs_id(redgifs_url)
        if redgifs_ID is None:
            logger.warning(
                f"\t [Redgifs] Unable to parse Redgifs ID from: {redgifs_url}"
            )
            return

        start_time = time.time()

        # Delete leftover media_file if any
        try:
            os.remove("archive_media_file.mp4")
        except:
            pass

        # Redgifs https://github.com/scrazzz/redgifs
        # Installation cmd: pip install -U redgifs
        if redgifs_api is None:
            redgifs_api = API()
            redgifs_api.login()

        try:
            gif = redgifs_api.get_gif(redgifs_ID)
            video_url = None
            for url_field in REDGIFS_VIDEO_URL_FIELDS:
                video_url = getattr(gif.urls, url_field, None)
                if video_url:
                    break

            if video_url is None:
                logger.warning(
                    f"\t [Redgifs] No downloadable URL found for ID: {redgifs_ID}"
                )
                return

            logger.info(
                f"\t [Redgifs] Downloading {url_field} video for ID: {redgifs_ID}"
            )
            _download_url_to_file(video_url, "archive_media_file.mp4")

            # Start Video processing
            # Index 1 second of Video (1FPS)
            mediaData = _extract_video_media_data("archive_media_file.mp4", submission)

            # Delete media_file
            try:
                os.remove("archive_media_file.mp4")
            except:
                pass
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Redgifs] Completed in {elapsed:.2f}s (Unique hashes: {len(mediaData)})"
            )
            return mediaData
        except RedGifsError as e:
            logger.warning(f"\t [Redgifs] Failed processing ID {redgifs_ID}: {e}")
            return
        except Exception as e:
            logger.warning(f"\t [Redgifs] Failed processing ID {redgifs_ID}: {e}")
            return
    except RedGifsError as e:
        logger.warning(
            "\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e)
        )
        return
    except Exception as e:
        traceback.print_exc()
        logger.warning(
            "\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e)
        )
        return


def getImgurAlbumMediaData(images, submission):
    try:
        if images is None:
            return

        mediaData = []

        # Process each image of Album
        for image in images:
            # Turn our link HTTPs
            link = image.link.replace("http://", "https://")

            # Prepare MediaData for all images in Ablum
            mediaData.append(getMediaData(link, submission, None))
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in getImgurAlbumMediaData \t Error= {0}".format(e))
        return


def getGifMediaData(url, submission):
    try:
        start_time = time.time()
        logger.info(f"\t [GIF] Starting GIF download from: {url[:60]}...")
        hash_seen = set()
        mediaData = []

        # Download file
        req = _media_request(url)
        with urllib.request.urlopen(req, timeout=VIDEO_REQUEST_TIMEOUT) as response:
            mediaContent = response.read()

        # Open gif
        im = Image.open(io.BytesIO(mediaContent))
        frame_count = 0
        for frame in ImageSequence.Iterator(im):
            media = getMediaData(None, submission, frame.copy())
            frame_count += 1
            if media is not None and media[0] not in hash_seen:
                hash_seen.add(media[0])
                mediaData.append(media)
        im.close()

        total_time = time.time() - start_time
        logger.info(
            f"\t [GIF] Completed in {total_time:.2f}s (Frames: {frame_count}, Unique: {len(mediaData)})"
        )
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in getGifMediaData \t Error= {0}".format(e))
        return


def getRedditGalleryMediaData(submission):
    try:
        mediaData = []
        seen_urls = []
        gallery_data = getattr(submission, "gallery_data", None)
        media_metadata = getattr(submission, "media_metadata", None)

        if not gallery_data or not media_metadata:
            logger.info("\t [Gallery] Metadata missing, skipping gallery media")
            return mediaData

        for item in gallery_data.get("items", []):
            media_id = item.get("media_id")
            meta = media_metadata.get(media_id)
            if meta is None:
                continue
            if meta.get("status") == "valid":
                source = meta.get("s", {})
                media_urls = []
                for source_key, media_type in (
                    ("mp4", "video"),
                    ("gif", "gif"),
                    ("u", "image"),
                ):
                    url = clean_media_url(source.get(source_key))
                    if url:
                        media_urls.append((url, media_type))

                if not media_urls:
                    previews = meta.get("p", [])
                    if previews:
                        url = clean_media_url(previews[-1].get("u"))
                        if url:
                            media_urls.append((url, "image"))

                for url, media_type in media_urls:
                    if url in seen_urls:
                        continue
                    seen_urls.append(url)
                    mediaData.extend(getMediaDataFromURL(url, submission, media_type))
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in getRedditGalleryMediaData \t Error= {0}".format(e))
        return


def getRedditPreviewMediaData(submission):
    try:
        mediaData = []
        seen_urls = []
        preview = getattr(submission, "preview", None)

        if not isinstance(preview, dict):
            return mediaData

        reddit_video_preview = preview.get("reddit_video_preview") or {}
        add_unique_url(seen_urls, reddit_video_preview.get("fallback_url"))
        if seen_urls:
            mediaData.extend(getMediaDataFromURL(seen_urls[-1], submission, "video"))

        for image in preview.get("images", []):
            variants = image.get("variants", {})
            candidates = []

            for variant_name, media_type in (
                ("mp4", "video"),
                ("gif", "gif"),
            ):
                source = variants.get(variant_name, {}).get("source", {})
                url = clean_media_url(source.get("url"))
                if url:
                    candidates.append((url, media_type))

            source = image.get("source", {})
            url = clean_media_url(source.get("url"))
            if url:
                candidates.append((url, "image"))

            for url, media_type in candidates:
                if url in seen_urls:
                    continue
                seen_urls.append(url)
                mediaData.extend(getMediaDataFromURL(url, submission, media_type))

        return mediaData
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in getRedditPreviewMediaData \t Error= {0}".format(e))
        return


def get_generic_page_media_url(url, include_html_meta=False):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": MEDIA_USER_AGENT},
            timeout=GENERIC_PAGE_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()

        if content_type.startswith("image/"):
            return response.url, "image"
        if content_type.startswith("video/"):
            return response.url, "video"
        if not include_html_meta or "html" not in content_type:
            return None, None

        soup = BeautifulSoup(response.text, features="html.parser")
        for keys, media_type in (
            (GENERIC_VIDEO_META_KEYS, "video"),
            (GENERIC_IMAGE_META_KEYS, "image"),
        ):
            for key in keys:
                tag = soup.find("meta", attrs={"property": key}) or soup.find(
                    "meta", attrs={"name": key}
                )
                if tag and tag.get("content"):
                    media_url = clean_media_url(
                        urllib.parse.urljoin(response.url, tag.get("content"))
                    )
                    if media_type == "video" and not is_video_url(media_url):
                        continue
                    return media_url, media_type

        return None, None
    except Exception as e:
        logger.debug(f"\t [Generic] Failed to inspect page media for {url}: {e}")
        return None, None


def is_reddit_video(submission):
    try:
        url = submission.url
        if "v.redd.it" in url:
            start_time = time.time()
            logger.info("\t [Type] Reddit Video detected")

            # Get mediaData
            mediaData = None
            for video_url in get_reddit_video_urls(submission):
                mediaData = getVideoMediaData(video_url, submission)
                if mediaData:
                    break
                logger.info(
                    f"\t [Video] No media extracted from {video_url[:60]}, trying next candidate"
                )

            if not mediaData:
                logger.info("\t [Video] No usable Reddit video media found")
                return False

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Time] is_reddit_video (v.redd.it) completed in {elapsed:.2f}s"
            )
            return True
        elif is_video_url(url):
            start_time = time.time()
            logger.info("\t [Type] Direct video link detected")

            # Get mediaData
            mediaData = getVideoMediaData(url, submission)
            if not mediaData:
                logger.info("\t [Video] No usable direct video media found")
                return False

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Time] is_reddit_video (direct) completed in {elapsed:.2f}s"
            )
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_reddit_video \t Error= {0}".format(e))
        return False


def is_gfycat_link(submission):
    try:
        url = submission.url
        if "gfycat.com/" in url:
            start_time = time.time()
            logger.info("\t [Type] Gfycat link detected")

            # Get embedded gfycat video | video_url should end with .mp4
            video_url = get_gfycat_embedded_video_url(url)

            if video_url is not None:
                logger.info("\t [Gfycat] Video URL extracted, processing...")
                # Get mediaData
                mediaData = getVideoMediaData(video_url, submission)

                # Add DB records
                add_DB_Record(submission, mediaData)
                elapsed = time.time() - start_time
                logger.info(f"\t [Time] is_gfycat_link completed in {elapsed:.2f}s")
                return True
            else:
                # Add DB records
                add_DB_Record(submission, None)
                elapsed = time.time() - start_time
                logger.info(
                    f"\t [Time] is_gfycat_link completed without media in {elapsed:.2f}s"
                )
                return False
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_gfycat_link \t Error= {0}".format(e))
        return False


def is_redgifs_link(submission):
    try:
        url = submission.url
        if "redgifs.com/" in url:
            start_time = time.time()
            logger.info("\t [Type] Redgifs link detected")

            # Get embedded redgifs video | video_url should end with .mp4
            logger.info("\t [Redgifs] Extracting video...")
            mediaData = get_redgifs_embedded_video_url(url, submission)

            if mediaData is not None:
                # Add DB records
                add_DB_Record(submission, mediaData)
                elapsed = time.time() - start_time
                logger.info(f"\t [Time] is_redgifs_link completed in {elapsed:.2f}s")
                return True
            else:
                # Add DB records
                add_DB_Record(submission, None)
                elapsed = time.time() - start_time
                logger.info(
                    f"\t [Time] is_redgifs_link completed without media in {elapsed:.2f}s"
                )
                return False
        else:
            return False
    except RedGifsError as e:
        logger.warning("\t  Error in is_redgifs_link \t Error= {0}".format(e))
        return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_redgifs_link \t Error= {0}".format(e))
        return False


def is_imgur_album(submission):
    try:
        url = str(submission.url.replace("m.imgur.com", "i.imgur.com"))
        if "imgur.com/a/" in url:
            start_time = time.time()
            logger.info("\t [Type] Imgur Album detected")

            # Get Imgur album ID
            album_id = url.split("imgur.com/a/")[-1]
            client = ImgurClient(IMGUR_CLIENTID, IMGUR_CLIENTSECRET)
            images = client.get_album_images(album_id)

            # Get mediaData
            mediaData = getImgurAlbumMediaData(images, submission)

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(f"\t [Time] is_imgur_album completed in {elapsed:.2f}s")
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_imgur_album \t Error= {0}".format(e))
        return False


def is_direct_link_to_gif(submission):
    try:
        url = submission.url
        path = urllib.parse.urlparse(url).path.lower()
        if path.endswith(GIF_EXTENSION):
            start_time = time.time()
            logger.info("\t [Type] GIF file detected")

            # Get mediaData
            mediaData = getGifMediaData(url, submission)

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Time] is_direct_link_to_gif (.gif) completed in {elapsed:.2f}s"
            )
            return True
        elif path.endswith(GIFV_EXTENSION):
            start_time = time.time()
            logger.info("\t [Type] GIFV file detected")
            url = re.sub(r"\.gifv(?=($|[?#]))", ".mp4", url, flags=re.IGNORECASE)

            # Get mediaData
            mediaData = getVideoMediaData(url, submission)

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Time] is_direct_link_to_gif (.gifv) completed in {elapsed:.2f}s"
            )
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_direct_link_to_gif \t Error= {0}".format(e))
        return False


def is_reddit_gallery(submission):
    try:
        if "reddit.com/gallery" in submission.url:
            start_time = time.time()
            logger.info("\t [Type] Reddit Gallery detected")

            # Get mediaData
            mediaData = getRedditGalleryMediaData(submission)
            if not mediaData:
                logger.info("\t [Gallery] No usable media found")
                return False

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(f"\t [Time] is_reddit_gallery completed in {elapsed:.2f}s")
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_reddit_gallery \t Error= {0}".format(e))
        return False


def is_direct_link_to_content(submission):
    try:
        mediaData = []
        url = str(submission.url.replace("m.imgur.com", "i.imgur.com"))
        path = urllib.parse.urlparse(url).path.lower()
        if (
            path.endswith(IMAGE_EXTENSIONS)
            or "reddituploads.com" in url
            or "reutersmedia.net" in url
            or "500px.org" in url
            or "redditmedia.com" in url
            or "preview.redd.it" in url
        ):
            start_time = time.time()
            logger.info("\t [Type] Direct image link detected")

            # Get mediaData
            mediaData.append(getMediaData(url, submission, None))

            # Add DB records
            add_DB_Record(submission, mediaData)
            elapsed = time.time() - start_time
            logger.info(
                f"\t [Time] is_direct_link_to_content completed in {elapsed:.2f}s"
            )
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_direct_link_to_content \t Error= {0}".format(e))
        return False


def is_reddit_preview(submission):
    try:
        preview = getattr(submission, "preview", None)
        if not preview:
            return False

        start_time = time.time()
        logger.info("\t [Type] Reddit preview media detected")

        mediaData = getRedditPreviewMediaData(submission)
        if not mediaData:
            return False

        add_DB_Record(submission, mediaData)
        elapsed = time.time() - start_time
        logger.info(f"\t [Time] is_reddit_preview completed in {elapsed:.2f}s")
        return True
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_reddit_preview \t Error= {0}".format(e))
        return False


def is_generic_page_media(submission):
    try:
        url = clean_media_url(submission.url)
        if not url.startswith(("http://", "https://")):
            return False

        media_url, media_type = get_generic_page_media_url(url)
        if not media_url:
            return False

        start_time = time.time()
        logger.info(f"\t [Type] Generic page media detected: {media_type}")

        mediaData = getMediaDataFromURL(media_url, submission, media_type)
        if not mediaData:
            return False

        add_DB_Record(submission, mediaData)
        elapsed = time.time() - start_time
        logger.info(f"\t [Time] is_generic_page_media completed in {elapsed:.2f}s")
        return True
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in is_generic_page_media \t Error= {0}".format(e))
        return False


def processSubmissionMedia(submission):
    if is_direct_link_to_content(submission):
        return True
    elif is_reddit_gallery(submission):
        return True
    elif is_direct_link_to_gif(submission):
        return True
    elif is_imgur_album(submission):
        return True
    elif is_redgifs_link(submission):
        return True
    elif is_gfycat_link(submission):
        return True
    elif is_reddit_video(submission):
        return True
    elif is_reddit_preview(submission):
        return True
    elif is_generic_page_media(submission):
        return True
    return False


def getSubmissionMediaCandidates(submission):
    candidates = []
    seen_urls = []

    def add_candidate(url, attrs=None):
        url = clean_media_url(url)
        if not url or url in seen_urls:
            return
        seen_urls.append(url)
        candidates.append(SubmissionUrlOverride(submission, url, attrs))

    if submission.is_self:
        for url in re.findall(r"(https?://[^\s]+)", submission.selftext or ""):
            add_candidate(url)
            if len(candidates) >= MAX_SELFPOST_URLS:
                break
    else:
        add_candidate(getattr(submission, "url_overridden_by_dest", None))
        add_candidate(getattr(submission, "url", None))

    for parent in getattr(submission, "crosspost_parent_list", []) or []:
        if not isinstance(parent, dict):
            continue

        parent_attrs = {
            key: parent.get(key)
            for key in (
                "gallery_data",
                "media",
                "media_metadata",
                "preview",
                "secure_media",
            )
            if key in parent
        }
        add_candidate(
            parent.get("url_overridden_by_dest") or parent.get("url"),
            parent_attrs,
        )

    if not candidates and (
        getattr(submission, "preview", None)
        or getattr(submission, "gallery_data", None)
        or getattr(submission, "media", None)
        or getattr(submission, "secure_media", None)
    ):
        candidates.append(submission)

    return candidates


def indexSubmission(submission):
    try:
        submission_start = time.time()

        # Skip if already indexed
        if databasehandler.submissionExists(submission.id):
            logger.info(f"\t [Index] Submission already exists, skipping")
            return

        logger.info(f"\t [Index] Start: https://reddit.com{submission.permalink}")

        processed = False
        process_all_candidates = submission.is_self
        for submission_to_index in getSubmissionMediaCandidates(submission):
            candidate_processed = processSubmissionMedia(submission_to_index)
            processed = processed or candidate_processed
            if candidate_processed and not process_all_candidates:
                break

        if not processed:
            logger.info("\t [Index] No supported media found")

        total_elapsed = time.time() - submission_start
        logger.info(f"\t [Index] Complete in {total_elapsed:.2f}s")
    except databasehandler.ArchiveDatabaseError as e:
        logger.warning(
            "\t  Database unavailable in indexSubmission \t Error= {0}".format(e)
        )
        raise
    except Exception as e:
        traceback.print_exc()
        logger.warning("\t  Error in indexSubmission \t Error= {0}".format(e))


def start():
    """The main function"""
    global SUBREDDITLIST

    # This opens a constant stream of submissions. It will loop until there's a
    # major error (usually this means the Reddit access token needs refreshing)

    if not SUBREDDITLIST:
        SUBREDDITLIST = databasehandler.getArchieveSubredditsList()
    if not SUBREDDITLIST:
        raise databasehandler.ArchiveDatabaseError("No archive subreddits loaded")

    subreddits = reddit.subreddit(SUBREDDITLIST)
    logger.info(f"\t [Stream] Starting submission stream...")

    # for submission in subreddits.new(limit=None):
    # if submission:
    # indexSubmission(submission)

    for submission in subreddits.stream.submissions(pause_after=0):
        if submission is None:
            time.sleep(5)
            continue
        indexSubmission(submission)


if __name__ == "__main__":
    # ------------------------------------#
    # Here's the stuff that actually gets run

    # Loop the submission stream until the Reddit access token expires.
    # Then get a new access token and start the stream again.
    logger.info("=" * 70)
    logger.info("ARCHIVE STARTED")
    logger.info("=" * 70)
    logger.info(f"\t [Start] Monitoring subreddits: {str(SUBREDDITLIST)[:100]}...")

    while 1:
        try:
            # Inside the retry loop so a transient Reddit/network failure at
            # boot cannot crash the service before streaming starts.
            logger.info(f"\t [Start] Connected to Reddit as u/{reddit.user.me()}")
            start()
        except TooManyRequests as e:
            headers = e.response.headers if e.response is not None else {}
            retry_after = None

            if "retry-after" in headers:
                retry_after = float(headers["retry-after"])
            elif "x-ratelimit-reset" in headers:
                retry_after = float(headers["x-ratelimit-reset"]) + 1
            else:
                retry_after = 60

            logger.warning(f"\t [RateLimit] Sleeping for {retry_after} seconds")
            time.sleep(retry_after)
        except RedGifsError as e:
            logger.warning("\t  Error in __main__ \t Error= {0}".format(e))
            time.sleep(60)
        except Exception as e:
            traceback.print_exc()
            logger.warning("\t  Error in __main__ \t Error= {0}".format(e))
            time.sleep(60)
