'''
DatabaseHandler.py
Handles all connections to the database. The database runs on PostgreSQL and is connected to via psycopg2.
'''

import psycopg2
import traceback
import logging
import time

logger = logging.getLogger("archive")

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
    logger.warning('DB Connection Failed. Error = {0}'.format(e))

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
        exists = (cur.fetchone()) is not None
        logger.debug(f"\t [DB] Submission {submissionid} exists: {exists}")
        return exists
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to check submission {submissionid}: {e}")
        return True
        
def getArchieveSubredditsList():
    """
    List of subreddits to index in background (reads posts and index images/gifs/videos) Will not comment for these subreddits
    """
    start_time = time.time()
    query = "SELECT subreddit FROM indexsubreddits;"
    
    try:
        sublist = []
        cur.execute(query)
        subredditslist = cur.fetchall()
        for item in subredditslist:
            sublist.append(str(item).strip("(),"))
        subreddit_list = '+'.join(sublist).replace("'", "")
        elapsed = time.time() - start_time
        logger.info(
            f"\t [DB] Loaded {len(sublist)} archive subreddit(s) in {elapsed:.3f}s"
        )
        return subreddit_list
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load archive subreddits: {e}")
        return
    
def getRepostCheckerList():
    """
    List of subreddits to index in background (reads posts and index images/gifs/videos) Will comment for these subreddits
    """
    start_time = time.time()
    query = "SELECT subreddit FROM checksubreddits;"
    
    try:
        sublist = []
        cur.execute(query)
        subredditslist = cur.fetchall()
        for item in subredditslist:
            sublist.append(str(item).strip("(),"))
        subreddit_list = '+'.join(sublist).replace("'", "")
        elapsed = time.time() - start_time
        logger.info(
            f"\t [DB] Loaded {len(sublist)} repostchecker subreddit(s) in {elapsed:.3f}s"
        )
        return subreddit_list
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load repostchecker subreddits: {e}")
        return

def addSubmission(submissionData):
    """
    Adds a submission record into Submissions Table.
    """
    query = "INSERT INTO submissions(id, subreddit, timestamp, author, title, url, comments, score, deleted, processed) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
    submission_id = submissionData[0] if submissionData else "unknown"
    subreddit = submissionData[1] if submissionData and len(submissionData) > 1 else "unknown"
    
    try:
        cur.execute(query, submissionData)
        logger.debug(f"\t [DB] Added submission {submission_id} ({subreddit})")
    except Exception as e:
        traceback.print_exc()
        cur.execute('ROLLBACK')
        logger.warning(f"\t [DB] Failed to add submission {submission_id}: {e}")

def addMedia(mediaData):
    """
    Adds a media record into Media Table.
    """
    query = "INSERT INTO media(hash, submission_id, subreddit, frame_number, frame_count, frame_width, frame_height, total_pixels, file_size) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s);"
    submission_id = mediaData[1] if mediaData and len(mediaData) > 1 else "unknown"

    try:
        cur.execute(query, mediaData)
        logger.debug(f"\t [DB] Added media hash for submission {submission_id}")
        return True
    except Exception as e:
        traceback.print_exc()
        cur.execute('ROLLBACK')
        logger.warning(f"\t [DB] Failed to add media for submission {submission_id}: {e}")
        return False

def getAllMedia():
    """
    Returns hash, submission_id, subreddit of all records of media table.
    """
    query = "SELECT hash, submission_id, subreddit FROM media WHERE frame_count=1 and hash <> '9925021303884596990' and subreddit <> 'ssaavvaaggeekkuunn';"

    try:
        cur.execute(query)
        rows = cur.fetchall()
        logger.debug(f"\t [DB] Loaded {len(rows)} media row(s)")
        return rows
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load media rows: {e}")
        return

def getSubmission(submissionid):
    """
    Returns id, subreddit of all records.
    """
    query = "SELECT id, subreddit, timestamp, author, title FROM submissions WHERE id =\'{0}\';".format(submissionid)
    
    try:
        cur.execute(query)
        submission = cur.fetchone()
        logger.debug(f"\t [DB] Loaded submission {submissionid}: {submission is not None}")
        return submission
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load submission {submissionid}: {e}")
        return

def commentExists(commentid):
    """
    Returns true if the comment exists inside mentions table.
    """
    query = "SELECT * FROM mentions WHERE commentid = \'{0}\';".format(commentid)
    
    try:
        cur.execute(query)
        exists = (cur.fetchone()) is not None
        logger.debug(f"\t [DB] Comment {commentid} exists: {exists}")
        return exists
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to check comment {commentid}: {e}")
        return True

def addComment(commentid, submission_id, type, requester, subreddit):
    """
    Add a record in mentions table.
    """
    query = "INSERT INTO mentions(commentid, submission_id, type, requester, subreddit) VALUES(\'{0}\', \'{1}\', \'{2}\', \'{3}\', \'{4}\');".format(commentid, submission_id, type, requester, subreddit)

    try:
        cur.execute(query)
        logger.debug(f"\t [DB] Added comment {commentid} for submission {submission_id}")
    except Exception as e:
        traceback.print_exc()
        cur.execute('ROLLBACK')
        logger.warning(f"\t [DB] Failed to add comment {commentid}: {e}")
