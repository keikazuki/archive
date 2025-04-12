'''
DatabaseHandler.py
Handles all connections to the database. The database runs on PostgreSQL and is connected to via psycopg2.
'''

import psycopg2
import traceback

DBNAME      = ''
DBUSER      = ''
DBPASSWORD  = ''
DBHOST      = ''
DBPORT      = ''

try:
    import config

    DBNAME = config.DBNAME
    DBUSER = config.DBUSER
    DBPASSWORD = config.DBPASSWORD
    DBHOST = config.DBHOST
    DBPORT = config.DBPORT
except ImportError:
    pass
    
try:
    conn = psycopg2.connect(
    user=DBUSER,
    password=DBPASSWORD,
    host=DBHOST,
    port=DBPORT,
    dbname=DBNAME
    )
    conn.autocommit = True
    cur = conn.cursor()
except (Exception) as e:
    print('DB Connection Failed. Error = {0}'.format(e), flush = True)

'''
    Code for create tables
'''

def submissionExists(submissionid):
    """
    Returns true if the submission exists inside table.
    """
    query = "SELECT * FROM submissions WHERE id =\'{0}\';".format(submissionid)
    
    try:
        cur.execute(query)
        if (cur.fetchone()) is None:
            return False
        else:
            return True
    except Exception:
        traceback.print_exc()
        return True
        
def getArchieveSubredditsList():
    """
    List of subreddits to index in background (reads posts and index images/gifs/videos) Will not comment for these subreddits
    """
    query = "SELECT subreddit FROM indexsubreddits;"
    
    try:
        sublist = []
        cur.execute(query)
        subredditslist = cur.fetchall()
        for item in subredditslist:
            sublist.append(str(item).strip("(),"))
        return '+'.join(sublist).replace("'", "")
    except Exception:
        traceback.print_exc()
        return
    
def getRepostCheckerList():
    """
    List of subreddits to index in background (reads posts and index images/gifs/videos) Will comment for these subreddits
    """
    query = "SELECT subreddit FROM checksubreddits;"
    
    try:
        sublist = []
        cur.execute(query)
        subredditslist = cur.fetchall()
        for item in subredditslist:
            sublist.append(str(item).strip("(),"))
        return '+'.join(sublist).replace("'", "")
    except Exception:
        traceback.print_exc()
        return

def addSubmission(submissionData):
    """
    Adds a submission record into Submissions Table.
    """
    query = "INSERT INTO submissions(id, subreddit, timestamp, author, title, url, comments, score, deleted, processed) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
    
    try:
        cur.execute(query, submissionData)
    except Exception:
        traceback.print_exc()
        cur.execute('ROLLBACK')

def addMedia(mediaData):
    """
    Adds a media record into Media Table.
    """
    query = "INSERT INTO media(hash, submission_id, subreddit, frame_number, frame_count, frame_width, frame_height, total_pixels, file_size) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s);"

    try:
        cur.execute(query, mediaData)
        return True
    except Exception:
        traceback.print_exc()
        cur.execute('ROLLBACK')
        return False

def getAllMedia():
    """
    Returns hash, submission_id, subreddit of all records of media table.
    """
    query = "SELECT hash, submission_id, subreddit FROM media WHERE frame_count=1 and hash <> '9925021303884596990' and subreddit <> 'ssaavvaaggeekkuunn';"

    try:
        cur.execute(query)
        return cur.fetchall()
    except Exception:
        traceback.print_exc()
        return

def getSubmission(submissionid):
    """
    Returns id, subreddit of all records.
    """
    query = "SELECT id, subreddit, timestamp, author, title FROM submissions WHERE id =\'{0}\';".format(submissionid)
    
    try:
        cur.execute(query)
        return cur.fetchone()
    except Exception:
        traceback.print_exc()
        return

def commentExists(commentid):
    """
    Returns true if the comment exists inside mentions table.
    """
    query = "SELECT * FROM mentions WHERE commentid = \'{0}\';".format(commentid)
    
    try:
        cur.execute(query)
        if (cur.fetchone()) is None:
            return False
        else:
            return True
    except Exception:
        traceback.print_exc()
        return True

def addComment(commentid, submission_id, type, requester, subreddit):
    """
    Add a record in mentions table.
    """
    query = "INSERT INTO mentions(commentid, submission_id, type, requester, subreddit) VALUES(\'{0}\', \'{1}\', \'{2}\', \'{3}\', \'{4}\');".format(commentid, submission_id, type, requester, subreddit)

    try:
        cur.execute(query)
    except Exception:
        traceback.print_exc()
        cur.execute('ROLLBACK')
