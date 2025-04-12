'''
Acts as the "main" file and ties all the other functionality together.
'''

import io, os, praw, psycopg2, time, urllib.request, prawcore, logging, json
import requests, cv2, traceback, re, sys
import config
import databasehandler
from PIL import Image
from PIL import ImageStat
from imgurpython import ImgurClient
from bs4 import BeautifulSoup
from redgifs import API

USERNAME            = config.USERNAME
PASSWORD            = config.PASSWORD
USERAGENT           = config.USERAGENT
REDDITAPPID         = config.REDDITAPPID
REDDITAPPSECRET     = config.REDDITAPPSECRET

IMGUR_CLIENTID      = config.IMGUR_CLIENTID
IMGUR_CLIENTSECRET  = config.IMGUR_CLIENTSECRET

SUBREDDITLIST       = databasehandler.getArchieveSubredditsList()

reddit = praw.Reddit(client_id=REDDITAPPID,
                     client_secret=REDDITAPPSECRET,
                     password=PASSWORD,
                     user_agent=USERAGENT,
                     username=USERNAME)

API_URL_REDGIFS = 'https://api.redgifs.com/v2/gifs/'

# logging.basicConfig(filename='/home/ubuntu/Desktop/Archive/archive.log', encoding='utf-8', level=logging.INFO)
logging.basicConfig(filename='/home/ubuntu/Desktop/Archive/archive.log', encoding='utf-8', level=logging.INFO, filemode = 'w')

sys.stdout.reconfigure(encoding='utf-8')
os.chdir("/home/ubuntu/Desktop/Archive/")

# logging.basicConfig(filename='archive.log', encoding='utf-8', level=logging.INFO, filemode = 'w')

def convertDateFormat(timestamp):
    return str(time.strftime('%B %d, %Y - %H:%M:%S', time.localtime(timestamp)))

def get_redirect_url(url):
    r = requests.get(url)
    return r.url

def DifferenceHash(theImage):
    """ Hashing function """
    theImage = theImage.convert("L")
    # theImage = theImage.resize((8,8), Image.ANTIALIAS)
    theImage = theImage.resize((8,8), Image.Resampling.LANCZOS)
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



def getMediaData(url, submission, image):
    try:
        #Delete previous leftover media_file if any
        try:
            os.remove('archive_media_file.png')
        except:
            pass
        
        if url is not None:
            #Download file
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_5_8) AppleWebKit/534.50.2 (KHTML, like Gecko) Version/5.0.6 Safari/533.22.3'})
            mediaContent = urllib.request.urlopen(req).read()
            
            #Save it
            f = open('archive_media_file.png', 'wb')
            f.write(mediaContent)
            f.close()
        elif image is not None:
            image.save('archive_media_file.png')
        
        #Prepare Media Object
        img             = Image.open('archive_media_file.png')
        width,height    = img.size
        pixels          = width*height
        size            = os.path.getsize('archive_media_file.png')
        imgHash         = DifferenceHash(img)
        mediaData       = (imgHash, 
                           str(submission.id), 
                           str(submission.subreddit.display_name), 
                           1, 
                           1, 
                           width, 
                           height, 
                           pixels, 
                           size)
        
        #Delete media_file
        try:
            os.remove('archive_media_file.png')
        except:
            pass
        
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t Error in getMediaData \t Error= {0}".format(e))
        return

def getSubmissionData(mediaprocessed, submission):
    try:
        if submission.author == '[deleted]':
            submissionDeleted = True
        else:
            submissionDeleted = False
        
        #Prepare Submission Object
        submissionData   = (str(submission.id),
                            submission.subreddit.display_name,
                            float(submission.created),
                            str(submission.author),
                            str(submission.title),
                            str(submission.url),
                            int(submission.num_comments),
                            int(submission.score),
                            submissionDeleted,
                            mediaprocessed)
        return submissionData
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t Error in getSubmissionData \t Error= {0}".format(e))
        return

def add_DB_Record(submission, mediaData):
    mediaprocessed = False
    if mediaData is not None:
        #Ignore Imgur generic deleted media data
        for media in mediaData:
            if media is not None and media[0] != '9925021303884596990':
                #Add media table record
                mediaprocessed = databasehandler.addMedia(media)
    #Add submission table record
    databasehandler.addSubmission(getSubmissionData(mediaprocessed, submission))



def getVideoMediaData(video_url, submission):
    """ video_url should end with .mp4 """
    try:        
        hash            = []
        mediaData       = []
        mediaDataTemp   = []
        #Delete leftover media_file if any
        try:
            os.remove('archive_media_file.mp4')
        except:
            pass
        
        #Download the video
        req = urllib.request.Request(video_url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_5_8) AppleWebKit/534.50.2 (KHTML, like Gecko) Version/5.0.6 Safari/533.22.3'})
        mediaContent = urllib.request.urlopen(req).read()
        
        #Open it
        f = open('archive_media_file.mp4', 'wb')
        f.write(mediaContent)
        f.close()
        
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
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in getVideoMediaData \t Error= {0}".format(e))
        return

def get_gfycat_embedded_video_url(url):
    try:
        # Cycle through all links
        giant_url_found  = False
        giant_url        = ""
        thumbs_url_found = False
        thumbs_url       = ""
        
        response = requests.get(url)
        data     = response.text
        soup     = BeautifulSoup(data, features="html.parser")
        
        for link in soup.find_all():
            link_src = link.get('src')
            src_url  = str(link_src)
            if ".mp4" in src_url:
                # Looking for giant.gfycat.com
                if "giant." in src_url:
                    giant_url_found  = True
                    giant_url        = src_url
                elif "thumbs." in src_url:
                    thumbs_url_found = True
                    thumbs_url       = src_url
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in get_gfycat_embedded_video_url \t Error= {0}".format(e))
        return
    
    if giant_url_found:
        return giant_url
    elif thumbs_url_found:
        return thumbs_url
    else:
        return

'''
def get_redgifs_embedded_video_url(url):
    try:
        redirect_url = get_redirect_url(url)
        response     = requests.get(redirect_url)
        html         = BeautifulSoup(response.content, features="html.parser")
        links        = str(html.find_all())
        
        #Get the direct video_url
        video_url    = re.search('meta content="https://thumbs2.redgifs.com/?.*?\.mp4', links).group()[14:]
        if video_url is not None:
            return video_url
        else:
            video_url = re.search('meta content="https://thumbs2.redgifs.com/?.*?\.webm', links).group()[14:]
            if video_url is not None:
                video_url = str(video_url.replace(".webm",".mp4"))
                return video_url
            else:
                return
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e))
        return
'''

'''
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
        logging.warning("\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e))
        return
'''

def get_redgifs_embedded_video_url(redgifs_url, submission):
    try:
        #Get RedGifs video ID
        redgifs_ID = re.search("(\/watch\/)\w+", redgifs_url)
        redgifs_ID = redgifs_ID.group()[7:]
        
        hash            = []
        mediaData       = []
        mediaDataTemp   = []
        
        #Delete leftover media_file if any
        try:
            os.remove('archive_media_file.mp4')
        except:
            pass
        
        #Redgifs https://github.com/scrazzz/redgifs
        # Installation cmd: pip install -U redgifs
        api = API()
        api.login()
        
        try:
            api.download((api.get_gif(redgifs_ID).urls.hd), f'archive_media_file.mp4')
        
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
        except:
            return
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in get_redgifs_embedded_video_url \t Error= {0}".format(e))
        return

def getImgurAlbumMediaData(images, submission):
    try:        
        if images is None:
            return
        
        mediaData = []
        
        #Process each image of Album
        for image in images:
            # Turn our link HTTPs
            link      = image.link.replace("http://","https://")
            
            #Prepare MediaData for all images in Ablum
            mediaData.append(getMediaData(link, submission, None))
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in getImgurAlbumMediaData \t Error= {0}".format(e))
        return

def getGifMediaData(url, submission):
    try:
        hash            = []
        mediaData       = []
        mediaDataTemp   = []
        #Delete previous leftover media_file if any
        try:
            os.remove('archive_media_file.gif')
        except:
            pass
        
        #Download file
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_5_8) AppleWebKit/534.50.2 (KHTML, like Gecko) Version/5.0.6 Safari/533.22.3'})
        mediaContent = urllib.request.urlopen(req).read()
        
        #Save it
        f = open('archive_media_file.gif', 'wb')
        f.write(mediaContent)
        f.close()
        
        #Open gif
        im = Image.open("archive_media_file.gif")
        try:
            #Get image from each frame of gif
            im.seek(im.tell()) 
            while 1:
                #Get image from each frame of gif
                #im.seek(im.tell()+1)
                mediaDataTemp.append(getMediaData(None, submission, im))
                
                #Remove duplicate media entries for different key frames
                for media in mediaDataTemp:
                    if media[0] not in hash:
                        hash.append(media[0])
                        mediaData.append(media)
                im.seek(im.tell()+1)
        except EOFError:
            pass # end of gif
        im.close()
        
        #Delete media_file
        try:
            os.remove('archive_media_file.gif')
        except:
            pass
        return mediaData
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in getGifMediaData \t Error= {0}".format(e))
        return

def getRedditGalleryMediaData(submission):
    try:
        mediaData = []
        for item in submission.gallery_data['items']:
            media_id = item['media_id']
            meta = submission.media_metadata[media_id]
            if meta['status'] == 'valid':
                if meta['e'] == 'Image':
                    source = meta['s']
                    url = str(source['u'])
                    
                    #Get mediaData for all gallery images
                    mediaData.append(getMediaData(url, submission, None))
        return mediaData     
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in getRedditGalleryMediaData \t Error= {0}".format(e))
        return



def is_reddit_video(submission):
    try:
        url = submission.url
        if "v.redd.it" in url:
            logging.info("\t Submission is a reddit video.")
            
            video_url = url + '/DASH_360.mp4'
            
            #Get mediaData
            mediaData = getVideoMediaData(video_url, submission)
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        elif url.lower().endswith(".mp4"):
            logging.info("\t Submission is a direct video.")
            
            #Get mediaData
            mediaData = getVideoMediaData(url, submission)
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_reddit_video \t Error= {0}".format(e))
        return False

def is_gfycat_link(submission):
    try:
        url = submission.url
        if "gfycat.com/" in url:
            logging.info("\t Submission is a gfycat link.")
            
            #Get embedded gfycat video | video_url should end with .mp4
            video_url = get_gfycat_embedded_video_url(url)
            
            if video_url is not None:
                #Get mediaData
                mediaData = getVideoMediaData(video_url, submission)
                
                #Add DB records
                add_DB_Record(submission, mediaData)
                return True
            else:
                #Add DB records
                add_DB_Record(submission, None)
                return False
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_gfycat_link \t Error= {0}".format(e))
        return False

def is_redgifs_link(submission):
    try:
        url = submission.url
        if "redgifs.com/" in url:
            logging.info("\t Submission is a redgifs link.")
            
            #Get embedded redgifs video | video_url should end with .mp4
            mediaData = get_redgifs_embedded_video_url(url, submission)
            
            if mediaData is not None:
                #Add DB records
                add_DB_Record(submission, mediaData)
                return True
            else:
                #Add DB records
                add_DB_Record(submission, None)
                return False
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_redgifs_link \t Error= {0}".format(e))
        return False

def is_imgur_album(submission):
    try:
        url = str(submission.url.replace("m.imgur.com","i.imgur.com"))
        if "imgur.com/a/" in  url:
            logging.info("\t Submission is an Imgur Album")
            
            #Get Imgur album ID
            album_id = url.split("imgur.com/a/")[-1]
            client = ImgurClient(IMGUR_CLIENTID, IMGUR_CLIENTSECRET)
            images = client.get_album_images(album_id)
            
            #Get mediaData
            mediaData = getImgurAlbumMediaData(images, submission)
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_imgur_album \t Error= {0}".format(e))
        return False

def is_direct_link_to_gif(submission):
    try:
        url = submission.url
        if url.lower().endswith(".gif"):
            logging.info("\t Submission is a GIF.")                                      
            
            #Get mediaData
            mediaData = getGifMediaData(url, submission)
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        elif url.lower().endswith(".gifv"):
            logging.info("\t Submission is a GIFV.")
            url = str(url.replace(".gifv",".mp4"))
            
            #Get mediaData
            mediaData = getVideoMediaData(url, submission)
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_direct_link_to_gif \t Error= {0}".format(e))
        return False

def is_reddit_gallery(submission):
    try:
        if "reddit.com/gallery" in submission.url:
            logging.info("\t Submission is a gallery.")
            
            #Get mediaData
            mediaData = getRedditGalleryMediaData(submission)
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_reddit_gallery \t Error= {0}".format(e))
        return False

def is_direct_link_to_content(submission):
    try:
        mediaData = []
        url = str(submission.url.replace("m.imgur.com","i.imgur.com"))
        if (url.lower().endswith(".jpg")            or 
            url.lower().endswith(".jpg?1")          or 
            url.lower().endswith(".png")            or 
            url.lower().endswith(".png?1")          or 
            url.lower().endswith(".jpeg")           or
            url.lower().endswith(".jpeg?1")         or
            url.lower().endswith(".webp")           or
            url.lower().endswith(".webp?1")         or
            url.lower().endswith(".jpg_large")      or
            url.lower().endswith(".jpg_large?1")    or
            url.lower().endswith(".svg")            or 
            url.lower().endswith(".svg?1")          or 
            "reddituploads.com" in url      or 
            "reutersmedia.net" in url       or 
            "500px.org" in url              or 
            "redditmedia.com" in url        or
            "preview.redd.it" in url):
            
            #Get mediaData
            mediaData.append(getMediaData(url, submission, None))
            
            #Add DB records
            add_DB_Record(submission, mediaData)
            return True
        else:
            return False
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in is_direct_link_to_content \t Error= {0}".format(e))
        return False

def indexSubmission(submission):
    try:
        #Skip text only posts
        if submission.is_self:
            s = re.findall(r'(https?://[^\s]+)', submission.selftext)
            if s:
                submission.url = s[0]
            else:
                return
        
        #Skip if already indexed
        if databasehandler.submissionExists(submission.id):
            return
        
        logging.info("\t Processing: \t https://reddit.com{0}".format(submission.permalink))
        
        #Start Indexing Image
        if is_direct_link_to_content(submission):
            pass
        elif is_reddit_gallery(submission):
            pass
        elif is_direct_link_to_gif(submission):
            pass
        elif is_imgur_album(submission):
            pass
        elif is_redgifs_link(submission):
            pass
        elif is_gfycat_link(submission):
            pass
        elif is_reddit_video(submission):
            pass
    except Exception as e:
        traceback.print_exc()
        logging.warning("\t  Error in indexSubmission \t Error= {0}".format(e))

def start():
    """ The main function """
    
    # This opens a constant stream of submissions. It will loop until there's a
    # major error (usually this means the Reddit access token needs refreshing)

    subreddits = reddit.subreddit(SUBREDDITLIST)
    
    #for submission in subreddits.new(limit=None):
       #if submission:
            #indexSubmission(submission)
    
    for submission in subreddits.stream.submissions(pause_after=0):
        if submission:
           indexSubmission(submission)

if __name__ == '__main__':
    # ------------------------------------#
    # Here's the stuff that actually gets run
    
    # Loop the submission stream until the Reddit access token expires.
    # Then get a new access token and start the stream again.
    time.sleep(900)
    while 1:
        try:
            start()
        except Exception as e:
            logging.warning("\t  Error in __main__ \t Error= {0}".format(e))
            pass
